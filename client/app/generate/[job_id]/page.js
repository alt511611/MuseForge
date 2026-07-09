"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  Film,
  Pen,
  Layout,
  Image as ImageIcon,
  Video,
  Music,
  CheckCircle2,
  XCircle,
  Loader2,
  ArrowLeft,
  Sparkles,
  Download,
  Ban,
  FlaskConical,
} from "lucide-react";

const STAGE_CONFIG = {
  screenwriting: { icon: Pen, label: "Screenwriter", color: "#a78bfa" },
  portraits: { icon: ImageIcon, label: "Character Lock", color: "#c084fc" },
  storyboard: { icon: Layout, label: "Storyboard", color: "#818cf8" },
  frames: { icon: ImageIcon, label: "Frame Gen", color: "#60a5fa" },
  video: { icon: Video, label: "Video Gen", color: "#34d399" },
  assembly: { icon: Film, label: "Assembly", color: "#fbbf24" },
  music: { icon: Music, label: "Soundtrack", color: "#f472b6" },
  scene_complete: { icon: CheckCircle2, label: "Scene Done", color: "#4ade80" },
  complete: { icon: CheckCircle2, label: "Complete", color: "#22c55e" },
  cancelled: { icon: Ban, label: "Cancelled", color: "#f59e0b" },
  error: { icon: XCircle, label: "Error", color: "#ef4444" },
};

const PIPELINE_STAGES = [
  "screenwriting",
  "portraits",
  "storyboard",
  "frames",
  "video",
  "assembly",
  "music",
  "complete",
];

export default function GeneratePage() {
  const { job_id } = useParams();
  const [job, setJob] = useState(null);
  const [events, setEvents] = useState([]);
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState("running");
  const [error, setError] = useState(null);
  const [cancelling, setCancelling] = useState(false);
  const logRef = useRef(null);
  const seenSeq = useRef(new Set());

  const addEvent = useCallback((evt) => {
    if (evt.stage === "heartbeat") return;
    const seq = evt.seq;
    if (typeof seq === "number" && seq >= 0) {
      if (seenSeq.current.has(seq)) return;
      seenSeq.current.add(seq);
    }
    setEvents((prev) => [...prev, evt]);
    if (typeof evt.progress === "number") setProgress(evt.progress);
    if (evt.stage === "error") {
      setError(evt.message);
      setStatus("failed");
    }
    if (evt.stage === "complete") setStatus("completed");
    if (evt.stage === "cancelled") setStatus("cancelled");
  }, []);

  const fetchJob = useCallback(async () => {
    try {
      const res = await fetch(`/api/jobs/${job_id}`);
      if (res.ok) {
        const data = await res.json();
        setJob(data);
        (data.events || []).forEach(addEvent);
        if (data.progress) setProgress(data.progress);
        if (data.status) setStatus(data.status);
        if (data.error) setError(data.error);
      }
    } catch {
      /* SSE will provide updates */
    }
  }, [job_id, addEvent]);

  useEffect(() => {
    if (!job_id) return;
    fetchJob();

    const source = new EventSource(`/api/jobs/${job_id}/stream`);
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
      } catch {
        /* ignore parse errors */
      }
    };
    source.onerror = () => {
      source.close();
      fetchJob();
    };
    return () => source.close();
  }, [job_id, fetchJob, addEvent]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [events]);

  const handleCancel = async () => {
    setCancelling(true);
    try {
      await fetch(`/api/jobs/${job_id}/cancel`, { method: "POST" });
    } catch {
      /* ignore */
    }
  };

  const nonHeartbeat = events.filter((e) => e.stage !== "heartbeat");
  const currentStage =
    nonHeartbeat.length > 0 ? nonHeartbeat[nonHeartbeat.length - 1].stage : "screenwriting";
  const stageIndex = PIPELINE_STAGES.indexOf(currentStage);
  const isRunning = status === "running" || status === "queued";
  const result = job?.result;
  const scenes = result?.scenes || [];
  const portraits = result?.portraits || {};

  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="flex items-center justify-between mb-8">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm transition-colors hover:text-purple-400"
            style={{ color: "#64748b" }}
          >
            <ArrowLeft size={16} />
            Back to MuseForge
          </Link>
          {isRunning && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="inline-flex items-center gap-2 text-sm px-3 py-1.5 rounded-lg transition-colors"
              style={{
                backgroundColor: "rgba(239, 68, 68, 0.1)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                color: "#fca5a5",
                cursor: cancelling ? "not-allowed" : "pointer",
              }}
            >
              <Ban size={14} />
              {cancelling ? "Cancelling..." : "Cancel"}
            </button>
          )}
        </div>

        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold mb-2">
            {status === "completed" ? (
              <span className="gradient-text">Generation Complete</span>
            ) : status === "failed" ? (
              <span style={{ color: "#ef4444" }}>Generation Failed</span>
            ) : status === "cancelled" ? (
              <span style={{ color: "#f59e0b" }}>Generation Cancelled</span>
            ) : (
              <span className="gradient-text">Generating Your Drama</span>
            )}
          </h1>
          <p className="text-sm flex items-center justify-center gap-2" style={{ color: "#64748b" }}>
            Job ID: {job_id}
            {job?.demo && (
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]"
                style={{ backgroundColor: "rgba(124,58,237,0.15)", color: "#a78bfa" }}
              >
                <FlaskConical size={10} /> DEMO
              </span>
            )}
          </p>
        </div>

        {/* Progress bar */}
        <div className="glass rounded-2xl p-6 mb-8">
          <div className="flex justify-between items-center mb-3">
            <span className="text-sm font-medium" style={{ color: "#94a3b8" }}>
              {status === "completed"
                ? "All agents finished"
                : status === "failed"
                  ? "Pipeline stopped"
                  : status === "cancelled"
                    ? "Cancelled by user"
                    : nonHeartbeat.length > 0
                      ? nonHeartbeat[nonHeartbeat.length - 1].message
                      : "Initializing pipeline..."}
            </span>
            <span className="text-sm font-mono" style={{ color: "#7c3aed" }}>
              {Math.round(progress)}%
            </span>
          </div>
          <div className="w-full h-2 rounded-full overflow-hidden" style={{ backgroundColor: "#1a1a2e" }}>
            <div
              className="h-full rounded-full transition-all duration-700 ease-out"
              style={{ width: `${progress}%`, background: "linear-gradient(90deg, #7c3aed, #a78bfa)" }}
            />
          </div>
        </div>

        {/* Pipeline timeline */}
        <div className="glass rounded-2xl p-6 mb-8">
          <h2 className="text-sm font-medium mb-4 flex items-center gap-2" style={{ color: "#a78bfa" }}>
            <Sparkles size={16} />
            Agent Pipeline
          </h2>
          <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
            {PIPELINE_STAGES.map((stage, idx) => {
              const config = STAGE_CONFIG[stage];
              const Icon = config?.icon || Loader2;
              const isActive = stage === currentStage && isRunning;
              const isDone = stageIndex > idx || status === "completed";
              return (
                <div key={stage} className="flex flex-col items-center gap-1.5">
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all ${
                      isActive ? "animate-pulse" : ""
                    }`}
                    style={{
                      backgroundColor: isDone
                        ? "rgba(34, 197, 94, 0.15)"
                        : isActive
                          ? "rgba(124, 58, 237, 0.25)"
                          : "#12121a",
                      border: isDone
                        ? "1px solid #22c55e"
                        : isActive
                          ? "1px solid #7c3aed"
                          : "1px solid #22223a",
                    }}
                  >
                    <Icon size={18} style={{ color: isDone ? "#22c55e" : isActive ? "#a78bfa" : "#64748b" }} />
                  </div>
                  <span
                    className="text-[10px] text-center leading-tight"
                    style={{ color: isDone ? "#22c55e" : isActive ? "#a78bfa" : "#64748b" }}
                  >
                    {config?.label || stage}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Result: video player */}
        {status === "completed" && result && (
          <div className="glass rounded-2xl p-6 mb-8 animate-fade-in">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-xl font-bold" style={{ color: "#e2e8f0" }}>
                  {result.title || "Your Drama"}
                </h3>
                <p className="text-sm" style={{ color: "#64748b" }}>
                  {result.logline}
                </p>
              </div>
              <a
                href={`/api/jobs/${job_id}/video`}
                download
                className="inline-flex items-center gap-2 text-sm px-4 py-2 rounded-lg font-medium"
                style={{ background: "linear-gradient(135deg, #7c3aed, #6d28d9)", color: "#fff" }}
              >
                <Download size={16} />
                Download
              </a>
            </div>
            <video
              key={job_id}
              controls
              playsInline
              className="w-full rounded-xl"
              style={{ backgroundColor: "#000", maxHeight: "70vh" }}
              poster={scenes?.[0]?.shots?.[0]?.frame_url}
              src={result.video_url || `/api/jobs/${job_id}/video`}
            />
            <p className="text-xs mt-3" style={{ color: "#475569" }}>
              {result.scene_count} scenes · character-locked consistency · {result.director_style}
            </p>
          </div>
        )}

        {/* Storyboard gallery */}
        {scenes.length > 0 && (
          <div className="glass rounded-2xl p-6 mb-8">
            <h2 className="text-sm font-medium mb-4 flex items-center gap-2" style={{ color: "#a78bfa" }}>
              <Layout size={16} />
              Storyboard
            </h2>
            {Object.keys(portraits).length > 0 && (
              <div className="mb-5">
                <p className="text-xs mb-2" style={{ color: "#64748b" }}>
                  Locked characters
                </p>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(portraits).map(([name, url]) => (
                    <div key={name} className="flex flex-col items-center gap-1">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={url}
                        alt={name}
                        className="w-14 h-14 rounded-full object-cover"
                        style={{ border: "2px solid #7c3aed" }}
                      />
                      <span className="text-[10px]" style={{ color: "#94a3b8" }}>
                        {name}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="space-y-4">
              {scenes.map((scene) => (
                <div key={scene.index}>
                  <p className="text-xs mb-2" style={{ color: "#64748b" }}>
                    Scene {scene.index + 1}: {scene.script}
                  </p>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                    {(scene.shots || []).map((shot, i) =>
                      shot.frame_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          key={i}
                          src={shot.frame_url}
                          alt={shot.visual_desc || `Shot ${i + 1}`}
                          className="w-full aspect-video object-cover rounded-lg"
                          style={{ border: "1px solid #22223a" }}
                        />
                      ) : null
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Event log */}
        <div className="glass rounded-2xl p-6 mb-8">
          <h2 className="text-sm font-medium mb-3" style={{ color: "#94a3b8" }}>
            Live Agent Log
          </h2>
          <div ref={logRef} className="space-y-2 max-h-64 overflow-y-auto font-mono text-xs">
            {nonHeartbeat.length === 0 && isRunning && (
              <div className="flex items-center gap-2" style={{ color: "#64748b" }}>
                <Loader2 size={14} className="animate-spin" />
                Waiting for agent updates...
              </div>
            )}
            {nonHeartbeat.map((evt, i) => {
              const config = STAGE_CONFIG[evt.stage] || {};
              return (
                <div key={evt.seq ?? i} className="flex gap-3 py-1">
                  <span style={{ color: "#475569" }}>{evt.timestamp?.slice(11, 19) || ""}</span>
                  <span style={{ color: config.color || "#94a3b8" }}>[{config.label || evt.stage}]</span>
                  <span style={{ color: "#cbd5e1" }}>{evt.message}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div
            className="rounded-xl px-4 py-3 text-sm mb-8"
            style={{
              backgroundColor: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              color: "#fca5a5",
            }}
          >
            {error}
          </div>
        )}
      </div>
    </main>
  );
}
