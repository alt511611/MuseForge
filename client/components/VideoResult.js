"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Download, Share2, Plus, ExternalLink, Layout, ChevronDown, ChevronUp, Loader2, BookmarkPlus, Check } from "lucide-react";
import Confetti from "./Confetti";
import { useLanguage } from "../contexts/LanguageContext";
import { useAuth } from "../contexts/AuthContext";
import { API_BASE, resolveJobVideoUrl } from "../lib/apiBase";

function SaveCharacterButton({ character }) {
  const { t } = useLanguage();
  const { getAccessToken } = useAuth();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  const handleSave = async () => {
    if (saving || saved) return;
    setError(null);
    setSaving(true);
    try {
      const token = await getAccessToken();
      if (!token) throw new Error(t("result_save_char_auth") || "Sign in required");
      const res = await fetch(`${API_BASE}/api/characters`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: character.name,
          static_features: character.static_features || character.name,
          portrait_url: character.portrait_url,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || t("result_save_char_failed") || "Could not save character");
      }
      setSaved(true);
    } catch (err) {
      setError(err.message || t("result_save_char_failed") || "Could not save character");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col items-center gap-0.5">
      <button
        type="button"
        onClick={handleSave}
        disabled={saving || saved}
        className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-md disabled:opacity-70"
        style={{
          backgroundColor: saved ? "rgba(34,197,94,0.15)" : "rgba(124,58,237,0.12)",
          color: saved ? "#86efac" : "#a78bfa",
          border: "1px solid #22223a",
        }}
      >
        {saving ? (
          <Loader2 size={10} className="animate-spin" />
        ) : saved ? (
          <Check size={10} />
        ) : (
          <BookmarkPlus size={10} />
        )}
        {saved
          ? (t("result_char_saved") || "Kaydedildi")
          : (t("result_save_char") || "Bu karakteri kaydet")}
      </button>
      {error && <span className="text-[9px] text-center" style={{ color: "#fca5a5" }}>{error}</span>}
    </div>
  );
}

function NextSteps({ jobId, videoUrl }) {
  const { t } = useLanguage();
  const openUrl = resolveJobVideoUrl(videoUrl, jobId);

  const handleShare = async () => {
    const url = typeof window !== "undefined" ? window.location.href : "";
    if (navigator.share) {
      try { await navigator.share({ title: t("result_share_title"), url }); } catch { /* cancelled */ }
    } else {
      await navigator.clipboard.writeText(url);
      alert(t("result_link_copied"));
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
        <a href={openUrl} target="_blank" rel="noopener noreferrer"
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
  const { getAccessToken } = useAuth();
  const result = job?.result;
  const [confetti, setConfetti] = useState(false);
  const [storyboardOpen, setStoryboardOpen] = useState(false);
  const [exporting, setExporting] = useState(null); // "9:16" | "1:1" | null
  const [exportError, setExportError] = useState(null);
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
        if (perm === "granted") new Notification(notifyTitle, { body: result.title || t("result_notify_body"), icon: "/favicon.ico" });
      });
    } else if (Notification.permission === "granted") {
      new Notification(notifyTitle, { body: result.title || t("result_notify_body"), icon: "/favicon.ico" });
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
  const videoSrc = resolveJobVideoUrl(result.video_url, jobId);
  const originalRatio = result.aspect_ratio || "16:9";

  const handleExport = async (aspectRatio) => {
    setExportError(null);
    setExporting(aspectRatio);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/export`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ aspect_ratio: aspectRatio }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || t("result_export_failed"));
      }
      const url = resolveJobVideoUrl(data.video_url, jobId);
      // Trigger download without leaving the page.
      const a = document.createElement("a");
      a.href = url;
      a.download = `museforge_${jobId}_${aspectRatio.replace(":", "x")}.mp4`;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      setExportError(err.message || t("result_export_failed"));
    } finally {
      setExporting(null);
    }
  };

  return (
    <>
      <Confetti active={confetti} />

      <div className="text-center mb-6 animate-slide-up">
        <div className="text-4xl mb-2">🎉</div>
        <h2 className="text-2xl font-black gradient-text">{t("result_ready")}</h2>
        <p className="text-sm mt-1" style={{ color: "#64748b" }}>
          {result.title} · {t("result_scenes_count", { n: result.scene_count })} · {result.aspect_ratio}
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
        <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
          <p className="text-xs truncate" style={{ color: "#475569" }}>{result.logline}</p>
          <div className="flex flex-wrap items-center gap-2 flex-shrink-0 ml-auto">
            <a href={videoSrc} download
              className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg font-medium"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
              <Download size={13} />
              {t("result_download")}
            </a>
            {originalRatio !== "9:16" && (
              <button
                type="button"
                disabled={!!exporting}
                onClick={() => handleExport("9:16")}
                className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-medium disabled:opacity-50"
                style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}
                title={t("result_export_crop_note")}
              >
                {exporting === "9:16" ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                {t("result_download_9_16")}
              </button>
            )}
            {originalRatio !== "1:1" && (
              <button
                type="button"
                disabled={!!exporting}
                onClick={() => handleExport("1:1")}
                className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-medium disabled:opacity-50"
                style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}
                title={t("result_export_crop_note")}
              >
                {exporting === "1:1" ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                {t("result_download_1_1")}
              </button>
            )}
          </div>
        </div>
        <p className="text-[10px] mt-2" style={{ color: "#475569" }}>{t("result_export_crop_note")}</p>
        {exportError && (
          <p className="text-xs mt-1" style={{ color: "#fca5a5" }}>{exportError}</p>
        )}
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
              {t("result_storyboard")}
            </span>
            {storyboardOpen ? <ChevronUp size={15} style={{ color: "#64748b" }} /> : <ChevronDown size={15} style={{ color: "#64748b" }} />}
          </button>

          {storyboardOpen && (
            <div className="px-5 pb-5 animate-fade-in">
              {Object.keys(portraits).length > 0 && (
                <div className="mb-4">
                  <p className="text-xs mb-2" style={{ color: "#64748b" }}>{t("result_locked_chars")}</p>
                  <div className="flex flex-wrap gap-3">
                    {(result.characters?.length
                      ? result.characters
                      : Object.entries(portraits).map(([name, url]) => ({
                          name,
                          portrait_url: url,
                          static_features: "",
                        }))
                    ).map((char) => {
                      const name = char.name;
                      const url = char.portrait_url || portraits[name];
                      if (!url) return null;
                      return (
                        <div key={name} className="flex flex-col items-center gap-1 max-w-[88px]">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={url} alt={name} className="w-14 h-14 rounded-full object-cover"
                            style={{ border: "2px solid #7c3aed" }} />
                          <span className="text-[10px] text-center" style={{ color: "#94a3b8" }}>{name}</span>
                          { (job?.plan === "pro" || result?.plan === "pro") && (
                            <SaveCharacterButton
                              character={{
                                name,
                                static_features: char.static_features || char.description || name,
                                portrait_url: url,
                              }}
                            />
                          )}
                        </div>
                      );
                    })}
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
