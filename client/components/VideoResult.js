"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Download, Share2, Plus, ExternalLink, Layout, ChevronDown, ChevronUp } from "lucide-react";
import Confetti from "./Confetti";
import { useLanguage } from "../contexts/LanguageContext";

function NextSteps({ jobId, videoUrl }) {
  const { t } = useLanguage();

  const handleShare = async () => {
    const url = typeof window !== "undefined" ? window.location.href : "";
    if (navigator.share) {
      try { await navigator.share({ title: "Made with MuseForge!", url }); } catch { /* cancelled */ }
    } else {
      await navigator.clipboard.writeText(url);
      alert("Link copied to clipboard!");
    }
  };

  return (
    <div className="glass rounded-2xl p-6">
      <h3 className="text-sm font-semibold mb-4" style={{ color: "#a78bfa" }}>{t("result_whats_next")}</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Link href="/"
          className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:scale-[1.02]"
          style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
          <Plus size={16} />
          {t("result_new_video")}
        </Link>
        <a href={videoUrl || `/api/jobs/${jobId}/video`} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:scale-[1.02]"
          style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}>
          <ExternalLink size={16} />
          {t("result_open_video")}
        </a>
        <button onClick={handleShare}
          className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:scale-[1.02]"
          style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}>
          <Share2 size={16} />
          {t("result_share")}
        </button>
      </div>
    </div>
  );
}

export default function VideoResult({ job, jobId }) {
  const { t } = useLanguage();
  const result = job?.result;
  const [confetti, setConfetti] = useState(false);
  const [storyboardOpen, setStoryboardOpen] = useState(false);
  const notifiedRef = useRef(false);

  useEffect(() => {
    if (!result || notifiedRef.current) return;
    notifiedRef.current = true;

    setConfetti(true);
    setTimeout(() => setConfetti(false), 5000);

    // Browser notification
    const notifyTitle = t("result_ready");
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission().then((perm) => {
        if (perm === "granted") new Notification(notifyTitle, { body: result.title || "Your video is complete.", icon: "/favicon.ico" });
      });
    } else if (Notification.permission === "granted") {
      new Notification(notifyTitle, { body: result.title || "Your video is complete.", icon: "/favicon.ico" });
    }

    // Completion chime
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [523, 659, 784, 1047].forEach((freq, i) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain); gain.connect(ctx.destination);
        osc.frequency.value = freq; osc.type = "sine";
        const st = ctx.currentTime + i * 0.12;
        gain.gain.setValueAtTime(0.15, st);
        gain.gain.exponentialRampToValueAtTime(0.001, st + 0.35);
        osc.start(st); osc.stop(st + 0.35);
      });
    } catch { /* audio not supported */ }
  }, [result, t]);

  if (!result) return null;

  const scenes = result.scenes || [];
  const portraits = result.portraits || {};
  const videoSrc = result.video_url || `/api/jobs/${jobId}/video`;

  return (
    <>
      <Confetti active={confetti} />

      <div className="text-center mb-6 animate-slide-up">
        <div className="text-4xl mb-2">🎉</div>
        <h2 className="text-2xl font-black gradient-text">{t("result_ready")}</h2>
        <p className="text-sm mt-1" style={{ color: "#64748b" }}>
          {result.title} · {result.scene_count} scenes · {result.aspect_ratio}
        </p>
      </div>

      <div className="glass rounded-2xl p-5 mb-5">
        <video
          key={jobId} controls autoPlay playsInline
          className="w-full rounded-xl"
          style={{ backgroundColor: "#000", maxHeight: "70vh" }}
          poster={scenes?.[0]?.shots?.[0]?.frame_url}
          src={videoSrc}
        />
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs truncate" style={{ color: "#475569" }}>{result.logline}</p>
          <a href={`/api/jobs/${jobId}/video`} download
            className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg font-medium flex-shrink-0 ml-3"
            style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
            <Download size={13} />
            Download
          </a>
        </div>
      </div>

      <div className="mb-5">
        <NextSteps jobId={jobId} videoUrl={result.video_url} />
      </div>

      {(scenes.length > 0 || Object.keys(portraits).length > 0) && (
        <div className="glass rounded-2xl">
          <button
            onClick={() => setStoryboardOpen(!storyboardOpen)}
            className="w-full flex items-center justify-between px-5 py-4"
          >
            <span className="text-sm font-medium flex items-center gap-2" style={{ color: "#a78bfa" }}>
              <Layout size={15} />
              Storyboard & Characters
            </span>
            {storyboardOpen ? <ChevronUp size={15} style={{ color: "#64748b" }} /> : <ChevronDown size={15} style={{ color: "#64748b" }} />}
          </button>

          {storyboardOpen && (
            <div className="px-5 pb-5 animate-fade-in">
              {Object.keys(portraits).length > 0 && (
                <div className="mb-4">
                  <p className="text-xs mb-2" style={{ color: "#64748b" }}>Locked Characters</p>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(portraits).map(([name, url]) => (
                      <div key={name} className="flex flex-col items-center gap-1">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={url} alt={name} className="w-14 h-14 rounded-full object-cover"
                          style={{ border: "2px solid #7c3aed" }} />
                        <span className="text-[10px]" style={{ color: "#94a3b8" }}>{name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {scenes.map((scene) => (
                <div key={scene.index} className="mb-4">
                  <p className="text-xs mb-2" style={{ color: "#64748b" }}>
                    Scene {scene.index + 1}: {scene.script}
                  </p>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {(scene.shots || []).filter(s => s.frame_url).map((shot, i) => (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img key={i} src={shot.frame_url} alt={shot.visual_desc || `Frame ${i + 1}`}
                        className="w-full aspect-video object-cover rounded-lg"
                        style={{ border: "1px solid #22223a" }} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}
