"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Download, Share2, Plus, ExternalLink, Layout, ChevronDown, ChevronUp } from "lucide-react";
import Confetti from "./Confetti";

function NextSteps({ jobId, videoUrl }) {
  const shareData = {
    title: "MuseForge ile yaptım!",
    text: "AI ile oluşturduğum sinematik micro-drama'yı izle!",
    url: typeof window !== "undefined" ? window.location.href : "",
  };

  const handleShare = async () => {
    if (navigator.share) {
      try { await navigator.share(shareData); } catch { /* cancelled */ }
    } else {
      await navigator.clipboard.writeText(shareData.url);
      alert("Bağlantı panoya kopyalandı!");
    }
  };

  return (
    <div className="glass rounded-2xl p-6">
      <h3 className="text-sm font-semibold mb-4" style={{ color: "#a78bfa" }}>Sırada Ne Var?</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Link href="/"
          className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:scale-[1.02]"
          style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
          <Plus size={16} />
          Yeni Video Oluştur
        </Link>
        <a href={videoUrl || `/api/jobs/${jobId}/video`} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:scale-[1.02]"
          style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}>
          <ExternalLink size={16} />
          Videoyu Aç
        </a>
        <button onClick={handleShare}
          className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:scale-[1.02]"
          style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}>
          <Share2 size={16} />
          Paylaş
        </button>
      </div>
    </div>
  );
}

export default function VideoResult({ job, jobId }) {
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
    if ("Notification" in window && Notification.permission === "default") {
      Notification.requestPermission().then((perm) => {
        if (perm === "granted") {
          new Notification("🎉 Videonuz Hazır!", {
            body: result.title || "MuseForge micro-drama'nız tamamlandı.",
            icon: "/favicon.ico",
          });
        }
      });
    } else if (Notification.permission === "granted") {
      new Notification("🎉 Videonuz Hazır!", {
        body: result.title || "MuseForge micro-drama'nız tamamlandı.",
        icon: "/favicon.ico",
      });
    }

    // Completion sound
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const notes = [523, 659, 784, 1047];
      notes.forEach((freq, i) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.value = freq;
        osc.type = "sine";
        const t = ctx.currentTime + i * 0.12;
        gain.gain.setValueAtTime(0.15, t);
        gain.gain.exponentialRampToValueAtTime(0.001, t + 0.35);
        osc.start(t);
        osc.stop(t + 0.35);
      });
    } catch { /* audio not supported */ }
  }, [result]);

  if (!result) return null;

  const scenes = result.scenes || [];
  const portraits = result.portraits || {};
  const videoSrc = result.video_url || `/api/jobs/${jobId}/video`;

  return (
    <>
      <Confetti active={confetti} />

      {/* Celebration header */}
      <div className="text-center mb-6 animate-slide-up">
        <div className="text-4xl mb-2">🎉</div>
        <h2 className="text-2xl font-black gradient-text">Videonuz Hazır!</h2>
        <p className="text-sm mt-1" style={{ color: "#64748b" }}>
          {result.title} · {result.scene_count} sahne · {result.aspect_ratio}
        </p>
      </div>

      {/* Video player */}
      <div className="glass rounded-2xl p-5 mb-5">
        <video
          key={jobId}
          controls
          autoPlay
          playsInline
          className="w-full rounded-xl"
          style={{ backgroundColor: "#000", maxHeight: "70vh" }}
          poster={scenes?.[0]?.shots?.[0]?.frame_url}
          src={videoSrc}
        />
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs" style={{ color: "#475569" }}>
            {result.logline}
          </p>
          <a
            href={`/api/jobs/${jobId}/video`}
            download
            className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg font-medium flex-shrink-0 ml-3"
            style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
          >
            <Download size={13} />
            İndir
          </a>
        </div>
      </div>

      {/* Next steps */}
      <div className="mb-5">
        <NextSteps jobId={jobId} videoUrl={result.video_url} />
      </div>

      {/* Storyboard gallery (collapsible) */}
      {(scenes.length > 0 || Object.keys(portraits).length > 0) && (
        <div className="glass rounded-2xl">
          <button
            onClick={() => setStoryboardOpen(!storyboardOpen)}
            className="w-full flex items-center justify-between px-5 py-4"
          >
            <span className="text-sm font-medium flex items-center gap-2" style={{ color: "#a78bfa" }}>
              <Layout size={15} />
              Storyboard & Karakter Galerisi
            </span>
            {storyboardOpen ? <ChevronUp size={15} style={{ color: "#64748b" }} /> : <ChevronDown size={15} style={{ color: "#64748b" }} />}
          </button>

          {storyboardOpen && (
            <div className="px-5 pb-5 animate-fade-in">
              {Object.keys(portraits).length > 0 && (
                <div className="mb-4">
                  <p className="text-xs mb-2" style={{ color: "#64748b" }}>Kilitli Karakterler</p>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(portraits).map(([name, url]) => (
                      <div key={name} className="flex flex-col items-center gap-1">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={url} alt={name}
                          className="w-14 h-14 rounded-full object-cover"
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
                    Sahne {scene.index + 1}: {scene.script}
                  </p>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {(scene.shots || []).filter(s => s.frame_url).map((shot, i) => (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img key={i} src={shot.frame_url} alt={shot.visual_desc || `Kare ${i + 1}`}
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
