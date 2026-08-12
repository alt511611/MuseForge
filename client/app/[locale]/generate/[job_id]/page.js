"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "../../../../components/LocaleLink";
import {
  Film, Pen, Layout, Image as ImageIcon, Video, Music,
  CheckCircle2, XCircle, Loader2, ArrowLeft, Sparkles,
  Ban, FlaskConical, RefreshCw, AudioLines, Palette, Subtitles,
} from "lucide-react";
import LoadingAnimation from "../../../../components/LoadingAnimation";
import VideoResult from "../../../../components/VideoResult";
import { getStageMessage, getInspirationMessage } from "../../../../utils/pipelineMessages";
import { friendlyError } from "../../../../utils/errorMessages";
import { useAuth } from "../../../../contexts/AuthContext";
import { API_BASE } from "../../../../lib/apiBase";
import { useLanguage } from "../../../../contexts/LanguageContext";
import { tr } from "../../../../lib/tr";

const STAGE_CONFIG = {
  screenwriting: { icon: Pen, labelKey: "stage_screenwriting", color: "var(--mf-violet-soft)" },
  portraits: { icon: ImageIcon, labelKey: "stage_portraits", color: "#c084fc" },
  storyboard: { icon: Layout, labelKey: "stage_storyboard", color: "#818cf8" },
  frames: { icon: ImageIcon, labelKey: "stage_frames", color: "#60a5fa" },
  video: { icon: Video, labelKey: "stage_video", color: "#34d399" },
  assembly: { icon: Film, labelKey: "stage_assembly", color: "var(--mf-gold)" },
  music: { icon: Music, labelKey: "stage_music", color: "#f472b6" },
  // Stages the pipeline really emits (see idea2video._assemble_final_drama and
  // _lipsync_scenes) that had no entry here at all, so the live log printed
  // their raw slugs and coloured them like plain text.
  lipsync: { icon: AudioLines, labelKey: "stage_lipsync", color: "#f472b6" },
  grade: { icon: Palette, labelKey: "stage_grade", color: "var(--mf-gold)" },
  subtitles: { icon: Subtitles, labelKey: "stage_subtitles", color: "#60a5fa" },
  finishing: { icon: Sparkles, labelKey: "stage_finishing", color: "var(--mf-gold)" },
  script_ready: { icon: Pen, labelKey: "stage_script_ready", color: "var(--mf-violet-soft)" },
  scene_complete: { icon: CheckCircle2, labelKey: "stage_scene_complete", color: "var(--mf-ok)" },
  complete: { icon: CheckCircle2, labelKey: "stage_complete", color: "var(--mf-ok)" },
  cancelled: { icon: Ban, labelKey: "stage_cancelled", color: "var(--mf-gold)" },
  error: { icon: XCircle, labelKey: "stage_error", color: "#ef4444" },
};

const PIPELINE_STAGES = ["screenwriting", "portraits", "storyboard", "frames", "video", "assembly", "music", "complete"];

function SkeletonBlock({ className = "" }) {
  return (
    <div className={`rounded-2xl animate-pulse ${className}`}
      style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line)" }} />
  );
}

function LiveGallery({ events }) {
  const { t } = useLanguage();
  const frames = events
    .filter((e) => e.data?.frame_url || e.data?.portrait_url)
    .map((e) => e.data?.frame_url || e.data?.portrait_url)
    .filter(Boolean)
    .slice(-6);
  if (!frames.length) return null;
  return (
    <div className="glass rounded-2xl p-4 mb-5 animate-fade-in">
      <p className="text-xs font-medium mb-3" style={{ color: "var(--mf-ink-3)" }}>{t("live_gallery")}</p>
      <div className="grid grid-cols-3 gap-2">
        {frames.map((url, i) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={i} src={url} alt={`Ara çıktı ${i + 1}`}
            className="w-full aspect-video object-cover rounded-lg animate-fade-in"
            style={{ border: "1px solid var(--mf-line-strong)" }} />
        ))}
      </div>
    </div>
  );
}

export default function GeneratePage() {
  const { job_id } = useParams();
  const { getAccessToken } = useAuth();
  const { t } = useLanguage();
  const [job, setJob] = useState(null);
  // fetchJob's closure captures this state, and it is deliberately not in the
  // dependency list (adding it would tear down and re-open the EventSource).
  // A ref reads current without re-creating the callback.
  const estimateRequestedRef = useRef(false);
  // The last remaining-seconds figure the SERVER reported, and the client
  // clock reading at which it arrived. Everything shown is derived from this
  // pair: the countdown ticks down locally between updates and re-anchors
  // whenever a fresh figure lands (every event, and every 15s heartbeat).
  //
  // Replaces an extrapolation from the progress percentage, which was the
  // wrong instrument for the job — progress% advances in steps while
  // wall-clock advances continuously, so it read as "4 minutes left" through
  // a stalled stage and then hit zero with a third of the render still to go.
  const etaRef = useRef({ seconds: null, at: 0 });
  const [events, setEvents] = useState([]);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("running");
  const [error, setError] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [inspoIdx] = useState(() => Math.floor(Math.random() * 6));
  const [nowTick, setNowTick] = useState(0);
  const [editScript, setEditScript] = useState(null);
  const [approving, setApproving] = useState(false);
  // Bumped to force a NEW EventSource. The server's SSE generator only streams
  // while the job is queued/running (jobs.JobStore.subscribe), so it closes the
  // moment the job parks in awaiting_script_approval — and nothing reopened it
  // once production actually started. The whole script-approval flow therefore
  // ended in a frozen 10% progress bar until the user reloaded by hand.
  const [streamEpoch, setStreamEpoch] = useState(0);
  const logRef = useRef(null);
  const seenSeq = useRef(new Set());
  const startTimeRef = useRef(Date.now());
  const stageMsgCountRef = useRef({});

  const authHeaders = useCallback(async () => {
    const token = await getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [getAccessToken]);

  // Anchor a server-reported ETA to the local clock. `nowTick` (below) drives
  // the once-a-second re-render that makes it visibly count down.
  const syncEta = useCallback((seconds) => {
    if (typeof seconds !== "number" || seconds < 0) return;
    etaRef.current = { seconds, at: Date.now() };
  }, []);

  const addEvent = useCallback((evt) => {
    // A heartbeat carries no progress of its own, but it DOES carry a freshly
    // measured ETA — it is the only thing that arrives during the long silence
    // of a multi-minute provider call, so it is taken before the early return.
    if (typeof evt.eta_seconds === "number") syncEta(evt.eta_seconds);
    if (evt.stage === "heartbeat") return;
    if (typeof evt.seq === "number" && evt.seq >= 0) {
      if (seenSeq.current.has(evt.seq)) return;
      seenSeq.current.add(evt.seq);
    }
    stageMsgCountRef.current[evt.stage] = (stageMsgCountRef.current[evt.stage] || 0) + 1;
    setEvents((prev) => [...prev, evt]);
    if (typeof evt.progress === "number") setProgress(evt.progress);
    if (evt.stage === "error") { setError(friendlyError(evt.message)); setStatus("failed"); }
    if (evt.stage === "complete") setStatus("completed");
    if (evt.stage === "cancelled") setStatus("cancelled");
    if (evt.stage === "script_ready") {
      setStatus("awaiting_script_approval");
      if (evt.data?.script) setEditScript(evt.data.script);
    }
  }, [syncEta]);

  const fetchJob = useCallback(async () => {
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API_BASE}/api/jobs/${job_id}`, { headers });
      if (res.ok) {
        const data = await res.json();
        setJob(data);
        (data.events || []).forEach(addEvent);
        if (data.progress) setProgress(data.progress);
        if (data.status) setStatus(data.status);
        if (data.error) setError(friendlyError(data.error));
        if (data.status === "awaiting_script_approval" && data.result?.script) {
          setEditScript(data.result.script);
        }

        // Once the job is running the server reports a MEASURED figure (see
        // interfaces/render_eta), so this call only has to cover the gap
        // before the first scene lands.
        if (typeof data.eta_seconds === "number") syncEta(data.eta_seconds);

        // The opening estimate. It has to describe THIS job: the request used
        // to send num_scenes alone, so a Pro job with dialogue and lip sync --
        // the slowest configuration the product sells, and the one where the
        // wait most needs explaining — was quoted the time of the cheapest one
        // and blew through its own countdown within minutes.
        if (!estimateRequestedRef.current && typeof data.num_scenes === "number") {
          estimateRequestedRef.current = true;
          fetch(`${API_BASE}/api/estimate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              num_scenes: data.num_scenes,
              music_enabled: !!data.music_enabled,
              dialogue_enabled: !!data.dialogue_enabled,
              lipsync_enabled: !!data.lipsync_enabled,
              plan: data.plan || "free",
            }),
          })
            .then((r) => (r.ok ? r.json() : null))
            .then((est) => {
              // Never let the prior overwrite a measurement that has already
              // arrived — this response can land after the first SSE event.
              if (est?.estimated_seconds && etaRef.current.seconds === null) {
                syncEta(est.estimated_seconds);
              }
            })
            .catch(() => {});
        }
      }
    } finally {
      setInitialLoading(false);
    }
  }, [job_id, addEvent, authHeaders]);

  useEffect(() => {
    if (!job_id) return;
    fetchJob();
    const source = new EventSource(`${API_BASE}/api/jobs/${job_id}/stream`);
    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.stage === "done") {
          setStatus(data.status);
          source.close();
          fetchJob();
          return;
        }
        addEvent(data);
      } catch { /* ignore */ }
    };
    source.onerror = () => { source.close(); fetchJob(); };
    return () => source.close();
  }, [job_id, fetchJob, addEvent, streamEpoch]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  const handleCancel = async () => {
    setCancelling(true);
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API_BASE}/api/jobs/${job_id}/cancel`, { method: "POST", headers });
      if (res.ok) {
        setStatus("cancelled");
      } else if (res.status === 400) {
        // Job already finished (completed/failed/cancelled) by the time
        // the click landed -- not really a failure, just re-sync the UI.
        await fetchJob();
      } else {
        // Previously: any non-2xx response (404 -- job lost from memory
        // after a server restart -- or 403, etc.) left `cancelling` stuck
        // true forever with no feedback, since only the res.ok branch
        // ever reset it. The button would show "Cancelling..." forever
        // even though nothing was actually happening anymore.
        setError(t("gen_cancel_failed"));
      }
    } catch {
      // Network-level failure (backend unreachable/mid-restart, CORS,
      // etc.) -- same fix: don't leave the button stuck, tell the user.
      setError(t("gen_cancel_failed"));
    } finally {
      setCancelling(false);
    }
  };

  const handleRetry = () => window.location.href = "/";

  const handleApproveScript = async () => {
    if (!editScript || approving) return;
    setApproving(true);
    setError(null);
    try {
      const headers = await authHeaders();
      const res = await fetch(`${API_BASE}/api/jobs/${job_id}/approve-script`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify({ script: editScript }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : t("gen_approve_failed")
        );
      }
      setStatus("running");
      // Production has restarted server-side; re-subscribe so its progress is
      // actually streamed. The ETA clock restarts here too — it was measuring
      // from page load, which on this path includes however long the user spent
      // reading and editing the script.
      startTimeRef.current = Date.now();
      // Drop the pre-approval figure rather than letting it tick down against
      // the run that is only now starting; the server re-arms its own clock at
      // the same moment and the first event brings a fresh one.
      etaRef.current = { seconds: null, at: 0 };
      setStreamEpoch((n) => n + 1);
    } catch (err) {
      setError(err.message || t("gen_approve_failed"));
    } finally {
      setApproving(false);
    }
  };

  const updateSceneText = (idx, value) => {
    setEditScript((prev) => {
      if (!prev) return prev;
      const scenes = [...(prev.scenes || [])];
      const current = scenes[idx];
      scenes[idx] =
        current && typeof current === "object"
          ? { ...current, action: value }
          : value;
      return { ...prev, scenes };
    });
  };

  const nonHB = events.filter((e) => e.stage !== "heartbeat");
  const currentStage = nonHB.length > 0 ? nonHB[nonHB.length - 1].stage : "screenwriting";
  const stageIndex = PIPELINE_STAGES.indexOf(currentStage);
  const isRunning = status === "running" || status === "queued";
  const isAwaitingScript = status === "awaiting_script_approval";

  // Keep the ETA / overtime label fresh while the job is running.
  useEffect(() => {
    if (!isRunning) return undefined;
    const id = setInterval(() => setNowTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [isRunning]);

  // ETA. The figure itself comes from the server, which measures this
  // deployment's real scene rate rather than assuming one (interfaces/
  // render_eta); all this does is tick the last reported value down between
  // updates so the number visibly moves. Updates land on every progress event
  // and on the 15s heartbeat, at which point it re-anchors — so a batch that
  // runs long corrects the estimate instead of silently exhausting it.
  void nowTick; // re-render tick
  const elapsed = Math.round((Date.now() - startTimeRef.current) / 1000);
  const OVERTIME_KEYS = ["gen_overtime_1", "gen_overtime_2", "gen_overtime_3", "gen_overtime_4"];
  // Every other string on this page is translated; the countdown was written
  // in Turkish inline, so a reader on any of the other nineteen locales got
  // "~4dk kaldı" in the middle of their own language.
  const remainingLabel = (seconds) =>
    seconds < 60
      ? tr(t, "gen_eta_seconds", `~${seconds}s kaldı`, { n: seconds })
      : tr(t, "gen_eta_minutes", `~${Math.round(seconds / 60)}dk kaldı`, {
          n: Math.round(seconds / 60),
        });

  let remainingSeconds = null;
  if (etaRef.current.seconds !== null) {
    const sinceSync = Math.round((Date.now() - etaRef.current.at) / 1000);
    remainingSeconds = Math.max(0, etaRef.current.seconds - sinceSync);
  }

  let etaLabel = null;
  if (!isRunning || remainingSeconds === null) {
    // Nothing measurable (a re-cut, a retake on an older job, a job parked on
    // script approval). Showing no countdown is the honest answer; the stage
    // messages still say what is happening.
    etaLabel = null;
  } else if (remainingSeconds > 0) {
    etaLabel = remainingLabel(remainingSeconds);
  } else {
    // The server floors its own estimate just above zero while work is still
    // open, so reaching zero here means the last update is stale — a provider
    // call has outrun even the corrected figure. Say that, rather than
    // freezing on "~0s".
    const idx = Math.floor(elapsed / 9) % OVERTIME_KEYS.length;
    etaLabel = t(OVERTIME_KEYS[idx]);
  }

  // Stage-specific inspiration message (i18n via t())
  const msgCount = stageMsgCountRef.current[currentStage] || 0;
  const stageMessage = isRunning ? getStageMessage(currentStage, msgCount, t) : "";

  if (initialLoading) {
    return (
      <main className="min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
        <div className="max-w-4xl mx-auto px-6 py-12 space-y-6">
          <SkeletonBlock className="h-8 w-32" />
          <SkeletonBlock className="h-32" />
          <SkeletonBlock className="h-20" />
          <SkeletonBlock className="h-64" />
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-12">

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <Link href="/" className="inline-flex items-center gap-2 text-sm transition-colors hover:text-violet-soft" style={{ color: "var(--mf-ink-3)" }}>
            <ArrowLeft size={16} /> {t("gen_home")}
          </Link>
          {isRunning && (
            <button onClick={handleCancel} disabled={cancelling}
              className="inline-flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg transition-colors"
              style={{ backgroundColor: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.3)", color: "var(--mf-err-soft)", cursor: cancelling ? "not-allowed" : "pointer" }}>
              <Ban size={14} />
              {cancelling ? t("gen_cancelling") : t("gen_cancel")}
            </button>
          )}
        </div>

        {/* Title */}
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold mb-2">
            {status === "completed" ? null
              : status === "failed" ? <span style={{ color: "#ef4444" }}>{t("gen_failed")}</span>
              : status === "cancelled" ? <span style={{ color: "var(--mf-gold)" }}>{t("gen_cancelled_title")}</span>
              : isAwaitingScript ? <span className="gradient-text">{t("gen_script_review_title")}</span>
              : <span className="gradient-text">{t("gen_running")}</span>}
          </h1>
          <p className="text-sm flex items-center justify-center gap-2" style={{ color: "var(--mf-ink-3)" }}>
            {t("gen_job_id")}: {job_id}
            {job?.demo && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]"
                style={{ backgroundColor: "rgba(139,92,246,0.15)", color: "var(--mf-violet-soft)" }}>
                <FlaskConical size={10} /> DEMO
              </span>
            )}
          </p>
        </div>

        {/* Completed → VideoResult */}
        {status === "completed" && job && (
          <VideoResult job={job} jobId={job_id} />
        )}

        {/* Script approval */}
        {isAwaitingScript && editScript && (
          <div className="glass rounded-2xl p-5 sm:p-6 mb-6 space-y-4">
            <p className="text-sm" style={{ color: "var(--mf-ink-2)" }}>{t("gen_script_review_desc")}</p>
            <div>
              <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>{t("gen_script_title")}</label>
              <input
                value={editScript.title || ""}
                onChange={(e) => setEditScript({ ...editScript, title: e.target.value })}
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
              />
            </div>
            <div>
              <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>{t("gen_script_mood")}</label>
              <input
                value={editScript.mood || ""}
                onChange={(e) => setEditScript({ ...editScript, mood: e.target.value })}
                className="w-full px-3 py-2 rounded-lg text-sm"
                style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
              />
            </div>
            <div>
              <label className="text-xs mb-1 block" style={{ color: "var(--mf-ink-3)" }}>{t("gen_script_setting")}</label>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <input
                  value={editScript.setting_location || ""}
                  onChange={(e) => setEditScript({ ...editScript, setting_location: e.target.value })}
                  placeholder={t("gen_script_location")}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
                />
                <input
                  value={editScript.setting_time_of_day || ""}
                  onChange={(e) => setEditScript({ ...editScript, setting_time_of_day: e.target.value })}
                  placeholder={t("gen_script_time")}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
                />
                <input
                  value={editScript.setting_era || ""}
                  onChange={(e) => setEditScript({ ...editScript, setting_era: e.target.value })}
                  placeholder={t("gen_script_era")}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
                />
              </div>
            </div>
            <div>
              <label className="text-xs mb-2 block" style={{ color: "var(--mf-ink-3)" }}>{t("gen_script_scenes")}</label>
              <div className="space-y-2">
                {(editScript.scenes || []).map((scene, idx) => (
                  <textarea
                    key={idx}
                    value={scene && typeof scene === "object" ? scene.action || "" : scene}
                    onChange={(e) => updateSceneText(idx, e.target.value)}
                    rows={2}
                    className="w-full px-3 py-2 rounded-lg text-sm"
                    style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
                  />
                ))}
              </div>
            </div>
            {(editScript.characters || []).length > 0 && (
              <div>
                <label className="text-xs mb-2 block" style={{ color: "var(--mf-ink-3)" }}>{t("gen_script_characters")}</label>
                <ul className="space-y-1">
                  {editScript.characters.map((c, i) => (
                    <li key={i} className="text-sm" style={{ color: "var(--mf-ink-2)" }}>
                      <span style={{ color: "var(--mf-violet-soft)" }}>{c.name}</span>
                      {c.description ? ` — ${c.description}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                onClick={handleApproveScript}
                disabled={approving || cancelling}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50"
                style={{ background: "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))", color: "#fff" }}
              >
                {approving ? t("gen_approving") : t("gen_approve_produce")}
              </button>
              <button
                type="button"
                onClick={handleCancel}
                disabled={cancelling}
                className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium disabled:opacity-50"
                style={{ backgroundColor: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.3)", color: "var(--mf-err-soft)" }}
              >
                {cancelling ? t("gen_cancelling") : t("gen_discard_script")}
              </button>
            </div>
          </div>
        )}

        {/* Running state */}
        {isRunning && (
          <>
            {/* Inspiration */}
            <div className="text-center mb-6">
              <p className="text-sm animate-pulse" style={{ color: "var(--mf-violet)" }}>
                {stageMessage || getInspirationMessage(inspoIdx, t)}
              </p>
            </div>

            {/* Central loading + progress */}
            <div className="glass rounded-2xl p-8 mb-6 flex flex-col items-center gap-4">
              <LoadingAnimation size={96} progress={progress} stage="" />
              <div className="w-full max-w-md">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm" style={{ color: "var(--mf-ink-2)" }}>
                    {nonHB.length > 0 ? nonHB[nonHB.length - 1].message : t("gen_starting")}
                  </span>
                  <div className="flex items-center gap-2">
                    {etaLabel && <span className="text-xs" style={{ color: "var(--mf-ink-4)" }}>{etaLabel}</span>}
                    <span className="text-sm font-mono" style={{ color: "var(--mf-violet)" }}>{Math.round(progress)}%</span>
                  </div>
                </div>
                <div className="w-full h-2 rounded-full overflow-hidden" style={{ backgroundColor: "var(--mf-line)" }}>
                  <div className="h-full rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${progress}%`, background: "linear-gradient(90deg,#7c3aed,#a78bfa)" }} />
                </div>
              </div>
            </div>

            {/* Pipeline timeline */}
            <div className="glass rounded-2xl p-5 mb-6">
              <h2 className="text-sm font-medium mb-4 flex items-center gap-2" style={{ color: "var(--mf-violet-soft)" }}>
                <Sparkles size={15} /> {t("gen_pipeline")}
              </h2>
              <div className="grid grid-cols-4 md:grid-cols-8 gap-1.5 sm:gap-2">
                {PIPELINE_STAGES.map((stage, idx) => {
                  const config = STAGE_CONFIG[stage];
                  const Icon = config?.icon || Loader2;
                  const isActive = stage === currentStage;
                  const isDone = stageIndex > idx;
                  return (
                    <div key={stage} className="flex flex-col items-center gap-1.5">
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${isActive ? "animate-pulse" : ""}`}
                        style={{ backgroundColor: isDone ? "rgba(52,211,153,0.15)" : isActive ? "rgba(139,92,246,0.25)" : "var(--mf-panel)", border: isDone ? "1px solid var(--mf-ok)" : isActive ? "1px solid var(--mf-violet)" : "1px solid var(--mf-line-strong)" }}>
                        <Icon size={17} style={{ color: isDone ? "var(--mf-ok)" : isActive ? "var(--mf-violet-soft)" : "var(--mf-ink-3)" }} />
                      </div>
                      <span className="text-[10px] text-center leading-tight"
                        style={{ color: isDone ? "var(--mf-ok)" : isActive ? "var(--mf-violet-soft)" : "var(--mf-ink-3)" }}>
                        {(config?.labelKey && t(config.labelKey)) || stage}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Live gallery */}
            <LiveGallery events={nonHB} />
          </>
        )}

        {/* Error */}
        {error && status !== "completed" && (
          <div className="glass rounded-2xl px-5 py-4 mb-6 flex items-start justify-between gap-4">
            <p className="text-sm" style={{ color: "var(--mf-err-soft)" }}>{error}</p>
            <button onClick={handleRetry}
              className="flex-shrink-0 flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg"
              style={{ backgroundColor: "rgba(139,92,246,0.15)", color: "var(--mf-violet-soft)", border: "1px solid rgba(139,92,246,0.3)" }}>
              <RefreshCw size={13} /> {t("gen_retry")}
            </button>
          </div>
        )}

        {/* Log (always shown while running, collapsible otherwise) */}
        {nonHB.length > 0 && (
          <div className="glass rounded-2xl p-5">
            <h2 className="text-sm font-medium mb-3" style={{ color: "var(--mf-ink-3)" }}>{t("gen_live_log")}</h2>
            <div ref={logRef} className="space-y-1.5 max-h-48 overflow-y-auto font-mono text-xs">
              {nonHB.map((evt, i) => {
                const config = STAGE_CONFIG[evt.stage] || {};
                return (
                  <div key={evt.seq ?? i} className="flex gap-2 py-0.5">
                    <span style={{ color: "var(--mf-ink-4)" }}>{evt.timestamp?.slice(11, 19) || ""}</span>
                    {/* `config.label` never existed — the entries carry
                        `labelKey` — so this always fell through to the raw
                        slug and the log stayed untranslated in all 20 locales. */}
                    <span style={{ color: config.color || "var(--mf-ink-2)" }}>
                      [{config.labelKey ? t(config.labelKey) : evt.stage}]
                    </span>
                    <span style={{ color: "var(--mf-ink-2)" }}>{evt.message}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
