"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Film, Pen, Layout, Image as ImageIcon, Video, Music,
  CheckCircle2, XCircle, Loader2, ArrowLeft, Sparkles,
  Ban, FlaskConical, RefreshCw,
} from "lucide-react";
import LoadingAnimation from "../../../components/LoadingAnimation";
import VideoResult from "../../../components/VideoResult";
import { getStageMessage, getInspirationMessage } from "../../../utils/pipelineMessages";
import { friendlyError } from "../../../utils/errorMessages";
import { useAuth } from "../../../contexts/AuthContext";
import { API_BASE } from "../../../lib/apiBase";
import { useLanguage } from "../../../contexts/LanguageContext";

const STAGE_CONFIG = {
  screenwriting: { icon: Pen, labelKey: "stage_screenwriting", color: "#a78bfa" },
  portraits: { icon: ImageIcon, labelKey: "stage_portraits", color: "#c084fc" },
  storyboard: { icon: Layout, labelKey: "stage_storyboard", color: "#818cf8" },
  frames: { icon: ImageIcon, labelKey: "stage_frames", color: "#60a5fa" },
  video: { icon: Video, labelKey: "stage_video", color: "#34d399" },
  assembly: { icon: Film, labelKey: "stage_assembly", color: "#fbbf24" },
  music: { icon: Music, labelKey: "stage_music", color: "#f472b6" },
  scene_complete: { icon: CheckCircle2, labelKey: "stage_scene_complete", color: "#4ade80" },
  complete: { icon: CheckCircle2, labelKey: "stage_complete", color: "#22c55e" },
  cancelled: { icon: Ban, labelKey: "stage_cancelled", color: "#f59e0b" },
  error: { icon: XCircle, labelKey: "stage_error", color: "#ef4444" },
};

const PIPELINE_STAGES = ["screenwriting", "portraits", "storyboard", "frames", "video", "assembly", "music", "complete"];

function SkeletonBlock({ className = "" }) {
  return (
    <div className={`rounded-2xl animate-pulse ${className}`}
      style={{ backgroundColor: "#12121a", border: "1px solid #1a1a26" }} />
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
      <p className="text-xs font-medium mb-3" style={{ color: "#64748b" }}>{t("live_gallery")}</p>
      <div className="grid grid-cols-3 gap-2">
        {frames.map((url, i) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img key={i} src={url} alt={`Ara çıktı ${i + 1}`}
            className="w-full aspect-video object-cover rounded-lg animate-fade-in"
            style={{ border: "1px solid #22223a" }} />
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
  const [estimatedTotalSeconds, setEstimatedTotalSeconds] = useState(null);
  const [events, setEvents] = useState([]);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("running");
  const [error, setError] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);
  const [inspoIdx] = useState(() => Math.floor(Math.random() * 6));
  const logRef = useRef(null);
  const seenSeq = useRef(new Set());
  const startTimeRef = useRef(Date.now());
  const stageMsgCountRef = useRef({});

  const authHeaders = useCallback(async () => {
    const token = await getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, [getAccessToken]);

  const addEvent = useCallback((evt) => {
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
  }, []);

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

        // Fetch a stable, stage-aware total-duration estimate once we know
        // num_scenes, instead of relying purely on the volatile
        // elapsed/progress extrapolation below (which can spike upward
        // whenever progress% stalls relative to wall-clock time -- e.g.
        // during a slow video-generation stage).
        if (estimatedTotalSeconds === null && typeof data.num_scenes === "number") {
          fetch(`${API_BASE}/api/estimate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ num_scenes: data.num_scenes }),
          })
            .then((r) => (r.ok ? r.json() : null))
            .then((est) => {
              if (est?.estimated_seconds) setEstimatedTotalSeconds(est.estimated_seconds);
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
  }, [job_id, fetchJob, addEvent]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  const handleCancel = async () => {
    setCancelling(true);
    const headers = await authHeaders();
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${job_id}/cancel`, { method: "POST", headers });
      if (res.ok) {
        setStatus("cancelled");
        setCancelling(false);
      }
    } catch { /* ignore — SSE stream will still try to reconcile state */ }
  };

  const handleRetry = () => window.location.href = "/";

  const nonHB = events.filter((e) => e.stage !== "heartbeat");
  const currentStage = nonHB.length > 0 ? nonHB[nonHB.length - 1].stage : "screenwriting";
  const stageIndex = PIPELINE_STAGES.indexOf(currentStage);
  const isRunning = status === "running" || status === "queued";

  // ETA calculation
  const elapsed = Math.round((Date.now() - startTimeRef.current) / 1000);
  // Prefer the stable, stage-aware estimate (total expected duration minus
  // elapsed) over the volatile elapsed/progress extrapolation, which can
  // spike upward whenever the progress percentage stalls relative to real
  // time -- e.g. during a slow video-generation stage that stays at ~50%
  // for several minutes. Fall back to the old formula only until the
  // estimate has loaded.
  const eta =
    estimatedTotalSeconds !== null
      ? Math.max(0, Math.round(estimatedTotalSeconds - elapsed))
      : progress > 5
      ? Math.round((elapsed / progress) * (100 - progress))
      : null;
  const etaLabel = eta !== null ? (eta < 60 ? `~${eta}s kaldı` : `~${Math.round(eta / 60)}dk kaldı`) : null;

  // Stage-specific inspiration message
  const msgCount = stageMsgCountRef.current[currentStage] || 0;
  const stageMessage = isRunning ? getStageMessage(currentStage, msgCount) : "";

  if (initialLoading) {
    return (
      <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
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
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8 sm:py-12">

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <Link href="/" className="inline-flex items-center gap-2 text-sm transition-colors hover:text-purple-400" style={{ color: "#64748b" }}>
            <ArrowLeft size={16} /> {t("gen_home")}
          </Link>
          {isRunning && (
            <button onClick={handleCancel} disabled={cancelling}
              className="inline-flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg transition-colors"
              style={{ backgroundColor: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#fca5a5", cursor: cancelling ? "not-allowed" : "pointer" }}>
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
              : status === "cancelled" ? <span style={{ color: "#f59e0b" }}>{t("gen_cancelled_title")}</span>
              : <span className="gradient-text">{t("gen_running")}</span>}
          </h1>
          <p className="text-sm flex items-center justify-center gap-2" style={{ color: "#64748b" }}>
            {t("gen_job_id")}: {job_id}
            {job?.demo && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]"
                style={{ backgroundColor: "rgba(124,58,237,0.15)", color: "#a78bfa" }}>
                <FlaskConical size={10} /> DEMO
              </span>
            )}
          </p>
        </div>

        {/* Completed → VideoResult */}
        {status === "completed" && job && (
          <VideoResult job={job} jobId={job_id} />
        )}

        {/* Running state */}
        {isRunning && (
          <>
            {/* Inspiration */}
            <div className="text-center mb-6">
              <p className="text-sm animate-pulse" style={{ color: "#7c3aed" }}>
                {stageMessage || getInspirationMessage(inspoIdx)}
              </p>
            </div>

            {/* Central loading + progress */}
            <div className="glass rounded-2xl p-8 mb-6 flex flex-col items-center gap-4">
              <LoadingAnimation size={96} progress={progress} stage="" />
              <div className="w-full max-w-md">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-sm" style={{ color: "#94a3b8" }}>
                    {nonHB.length > 0 ? nonHB[nonHB.length - 1].message : t("gen_starting")}
                  </span>
                  <div className="flex items-center gap-2">
                    {etaLabel && <span className="text-xs" style={{ color: "#475569" }}>{etaLabel}</span>}
                    <span className="text-sm font-mono" style={{ color: "#7c3aed" }}>{Math.round(progress)}%</span>
                  </div>
                </div>
                <div className="w-full h-2 rounded-full overflow-hidden" style={{ backgroundColor: "#1a1a2e" }}>
                  <div className="h-full rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${progress}%`, background: "linear-gradient(90deg,#7c3aed,#a78bfa)" }} />
                </div>
              </div>
            </div>

            {/* Pipeline timeline */}
            <div className="glass rounded-2xl p-5 mb-6">
              <h2 className="text-sm font-medium mb-4 flex items-center gap-2" style={{ color: "#a78bfa" }}>
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
                        style={{ backgroundColor: isDone ? "rgba(34,197,94,0.15)" : isActive ? "rgba(124,58,237,0.25)" : "#12121a", border: isDone ? "1px solid #22c55e" : isActive ? "1px solid #7c3aed" : "1px solid #22223a" }}>
                        <Icon size={17} style={{ color: isDone ? "#22c55e" : isActive ? "#a78bfa" : "#64748b" }} />
                      </div>
                      <span className="text-[10px] text-center leading-tight"
                        style={{ color: isDone ? "#22c55e" : isActive ? "#a78bfa" : "#64748b" }}>
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
            <p className="text-sm" style={{ color: "#fca5a5" }}>{error}</p>
            <button onClick={handleRetry}
              className="flex-shrink-0 flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg"
              style={{ backgroundColor: "rgba(124,58,237,0.15)", color: "#a78bfa", border: "1px solid rgba(124,58,237,0.3)" }}>
              <RefreshCw size={13} /> {t("gen_retry")}
            </button>
          </div>
        )}

        {/* Log (always shown while running, collapsible otherwise) */}
        {nonHB.length > 0 && (
          <div className="glass rounded-2xl p-5">
            <h2 className="text-sm font-medium mb-3" style={{ color: "#64748b" }}>{t("gen_live_log")}</h2>
            <div ref={logRef} className="space-y-1.5 max-h-48 overflow-y-auto font-mono text-xs">
              {nonHB.map((evt, i) => {
                const config = STAGE_CONFIG[evt.stage] || {};
                return (
                  <div key={evt.seq ?? i} className="flex gap-2 py-0.5">
                    <span style={{ color: "#475569" }}>{evt.timestamp?.slice(11, 19) || ""}</span>
                    <span style={{ color: config.color || "#94a3b8" }}>[{config.label || evt.stage}]</span>
                    <span style={{ color: "#cbd5e1" }}>{evt.message}</span>
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
