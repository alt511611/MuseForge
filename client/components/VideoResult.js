"use client";

import { useEffect, useRef, useState } from "react";
import Link from "./LocaleLink";
import { Download, Share2, Plus, ExternalLink, Layout, ChevronDown, ChevronUp, Loader2, BookmarkPlus, Check, RefreshCw, Wand2, Scissors, ArrowUp, ArrowDown, Eye, EyeOff, AlertTriangle } from "lucide-react";
import Confetti from "./Confetti";
import { useLanguage } from "../contexts/LanguageContext";
import { useAuth } from "../contexts/AuthContext";
import { API_BASE, resolveJobVideoUrl } from "../lib/apiBase";
import { tr } from "../lib/tr";

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
      if (!token) throw new Error(tr(t, "result_save_char_auth", "Sign in required"));
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
        throw new Error(data.detail || tr(t, "result_save_char_failed", "Could not save character"));
      }
      setSaved(true);
    } catch (err) {
      setError(err.message || tr(t, "result_save_char_failed", "Could not save character"));
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
          backgroundColor: saved ? "rgba(52,211,153,0.15)" : "rgba(139,92,246,0.12)",
          color: saved ? "var(--mf-ok)" : "var(--mf-violet-soft)",
          border: "1px solid var(--mf-line-strong)",
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
          ? (tr(t, "result_char_saved", "Kaydedildi"))
          : (tr(t, "result_save_char", "Bu karakteri kaydet"))}
      </button>
      {error && <span className="text-[9px] text-center" style={{ color: "var(--mf-err-soft)" }}>{error}</span>}
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
      <h3 className="text-sm font-semibold mb-4" style={{ color: "var(--mf-violet-soft)" }}>{t("result_whats_next")}</h3>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Link href="/"
          className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:scale-[1.02]"
          style={{ background: "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))", color: "#fff" }}>
          <Plus size={16} />
          {t("result_new_video")}
        </Link>
        <a href={openUrl} target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:scale-[1.02]"
          style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink-2)" }}>
          <ExternalLink size={16} />
          {t("result_open_video")}
        </a>
        <button onClick={handleShare}
          className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:scale-[1.02]"
          style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink-2)" }}>
          <Share2 size={16} />
          {t("result_share")}
        </button>
      </div>
    </div>
  );
}

/** Re-shoot one scene without re-rolling (and re-paying for) the whole drama.
 *
 * Deliberately asks for a reason before firing: the note is passed to the
 * shot brief as binding direction, so a retake WITH one is a correction while
 * a retake without one is just another roll of the same dice.
 */
function RetakeSceneButton({ jobId, sceneIndex, onStarted }) {
  const { t } = useLanguage();
  const { getAccessToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      const token = await getAccessToken();
      const res = await fetch(
        `${API_BASE}/api/jobs/${jobId}/scenes/${sceneIndex}/regenerate`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ director_note: note.trim() }),
        }
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || tr(t, "result_retake_failed", "Retake failed"));
      setOpen(false);
      setNote("");
      onStarted?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-lg transition-colors"
        style={{ color: "var(--mf-ink-3)", border: "1px solid var(--mf-line-strong)" }}
      >
        <RefreshCw size={12} />
        {tr(t, "result_retake_scene", "Bu sahneyi yeniden çek")}
      </button>
    );
  }

  return (
    <div className="flex flex-col gap-2 mt-1">
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        maxLength={500}
        rows={2}
        placeholder={
          tr(t, "result_retake_note_ph", "Neyi değiştirmeli? Örn: çok karanlık, ellerini göster")
        }
        className="w-full px-3 py-2 rounded-lg text-xs focus:outline-none"
        style={{
          backgroundColor: "var(--mf-stage)",
          border: "1px solid var(--mf-line-strong)",
          color: "var(--mf-ink)",
        }}
      />
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={busy}
          className="inline-flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg"
          style={{ backgroundColor: "var(--mf-violet)", color: "white" }}
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          {tr(t, "result_retake_confirm", "Yeniden çek (1 kredi)")}
        </button>
        <button
          type="button"
          onClick={() => {
            setOpen(false);
            setError(null);
          }}
          className="text-[11px] px-2 py-1.5 rounded-lg"
          style={{ color: "var(--mf-ink-3)" }}
        >
          {tr(t, "result_retake_cancel", "Vazgeç")}
        </button>
      </div>
      {error && (
        <p className="text-[11px]" style={{ color: "var(--mf-err-soft)" }}>{error}</p>
      )}
    </div>
  );
}

/** Change one continuity fact — a costume, a set — everywhere it appears.
 *
 * Separate from a retake because the unit of change is different: a retake
 * re-rolls ONE scene, while this moves the locked portrait or set plate and
 * then re-renders every scene anchored to it. That is why it is priced per
 * affected scene, and why the price is only known after the server has worked
 * out which scenes those are.
 */
function ContinuityEditPanel({ jobId, characters, hasLocation, onStarted }) {
  const { t } = useLanguage();
  const { getAccessToken } = useAuth();
  const [target, setTarget] = useState(characters[0] || (hasLocation ? "location" : ""));
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  if (!target) return null;

  const submit = async () => {
    if (busy || instruction.trim().length < 3) return;
    setError(null);
    setBusy(true);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/global-edit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ instruction: instruction.trim(), target }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || tr(t, "result_edit_failed", "Değişiklik uygulanamadı"));
      onStarted?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[11px]" style={{ color: "var(--mf-ink-4)" }}>
        {tr(t, "result_edit_hint", "Kilitli portreyi veya mekânı değiştirir; etkilenen her sahne yeniden çekilir (sahne başına 1 kredi).")}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          className="text-xs px-2 py-2 rounded-lg focus:outline-none"
          style={{
            backgroundColor: "var(--mf-stage)",
            border: "1px solid var(--mf-line-strong)",
            color: "var(--mf-ink)",
          }}
        >
          {characters.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
          {hasLocation && (
            <option value="location">{tr(t, "result_edit_location", "Mekân")}</option>
          )}
        </select>
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          maxLength={300}
          placeholder={tr(t, "result_edit_ph", "Örn: kırmızı palto giydir")}
          className="flex-1 min-w-[180px] px-3 py-2 rounded-lg text-xs focus:outline-none"
          style={{
            backgroundColor: "var(--mf-stage)",
            border: "1px solid var(--mf-line-strong)",
            color: "var(--mf-ink)",
          }}
        />
        <button
          type="button"
          onClick={submit}
          disabled={busy || instruction.trim().length < 3}
          className="inline-flex items-center gap-1.5 text-[11px] px-3 py-2 rounded-lg disabled:opacity-50"
          style={{ backgroundColor: "var(--mf-violet)", color: "white" }}
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Wand2 size={12} />}
          {tr(t, "result_edit_apply", "Her sahnede uygula")}
        </button>
      </div>
      {error && <p className="text-[11px]" style={{ color: "var(--mf-err-soft)" }}>{error}</p>}
    </div>
  );
}

/** Reorder, trim and drop scenes of a finished drama.
 *
 * Every clip already exists, so this calls no generation model and costs
 * nothing — which is the whole reason it exists next to the retake button.
 * Someone who only wants the last scene two seconds shorter should not have to
 * pay to re-roll the take.
 */
function TimelinePanel({ jobId, scenes, onStarted }) {
  const { t } = useLanguage();
  const { getAccessToken } = useAuth();
  const [entries, setEntries] = useState(() =>
    scenes.map((scene) => ({
      scene_index: scene.index,
      label: scene.script || `Scene ${scene.index + 1}`,
      included: true,
      trim_start: 0,
      trim_end: 0,
    }))
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const move = (position, delta) => {
    const target = position + delta;
    if (target < 0 || target >= entries.length) return;
    const next = [...entries];
    [next[position], next[target]] = [next[target], next[position]];
    setEntries(next);
  };

  const patch = (position, changes) =>
    setEntries(entries.map((e, i) => (i === position ? { ...e, ...changes } : e)));

  const kept = entries.filter((e) => e.included);
  const dirty =
    kept.length !== scenes.length ||
    kept.some((e, i) => e.scene_index !== scenes[i]?.index || e.trim_start || e.trim_end);

  const submit = async () => {
    if (busy || !kept.length) return;
    setError(null);
    setBusy(true);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/timeline`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          timeline: kept.map((e) => ({
            scene_index: e.scene_index,
            trim_start: Number(e.trim_start) || 0,
            trim_end: Number(e.trim_end) || 0,
          })),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || tr(t, "result_cut_failed", "Kurgu uygulanamadı"));
      onStarted?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[11px]" style={{ color: "var(--mf-ink-4)" }}>
        {tr(t, "result_cut_hint", "Sahneleri sırala, kırp veya çıkar. Yeniden üretim yok — ücretsiz.")}
      </p>
      {entries.map((entry, position) => (
        <div
          key={entry.scene_index}
          className="flex flex-wrap items-center gap-2 px-2 py-1.5 rounded-lg"
          style={{
            border: "1px solid var(--mf-line-strong)",
            opacity: entry.included ? 1 : 0.45,
          }}
        >
          <span className="text-[11px] w-6 text-center" style={{ color: "var(--mf-ink-4)" }}>
            {position + 1}
          </span>
          <span className="text-[11px] flex-1 min-w-[120px] truncate" style={{ color: "var(--mf-ink-2)" }}>
            {entry.label}
          </span>
          <label className="text-[10px] flex items-center gap-1" style={{ color: "var(--mf-ink-4)" }}>
            {tr(t, "result_cut_trim_start", "baş")}
            <input
              type="number" min={0} max={14} step={0.5}
              value={entry.trim_start}
              onChange={(e) => patch(position, { trim_start: e.target.value })}
              className="w-14 px-1.5 py-1 rounded text-[11px] focus:outline-none"
              style={{
                backgroundColor: "var(--mf-stage)",
                border: "1px solid var(--mf-line-strong)",
                color: "var(--mf-ink)",
              }}
            />
          </label>
          <label className="text-[10px] flex items-center gap-1" style={{ color: "var(--mf-ink-4)" }}>
            {tr(t, "result_cut_trim_end", "son")}
            <input
              type="number" min={0} max={14} step={0.5}
              value={entry.trim_end}
              onChange={(e) => patch(position, { trim_end: e.target.value })}
              className="w-14 px-1.5 py-1 rounded text-[11px] focus:outline-none"
              style={{
                backgroundColor: "var(--mf-stage)",
                border: "1px solid var(--mf-line-strong)",
                color: "var(--mf-ink)",
              }}
            />
          </label>
          <button type="button" onClick={() => move(position, -1)} aria-label={tr(t, "result_cut_up", "Yukarı taşı")}
            className="p-1 rounded" style={{ color: "var(--mf-ink-3)" }}>
            <ArrowUp size={12} />
          </button>
          <button type="button" onClick={() => move(position, 1)} aria-label={tr(t, "result_cut_down", "Aşağı taşı")}
            className="p-1 rounded" style={{ color: "var(--mf-ink-3)" }}>
            <ArrowDown size={12} />
          </button>
          <button
            type="button"
            onClick={() => patch(position, { included: !entry.included })}
            aria-label={entry.included ? (tr(t, "result_cut_drop", "Kesimden çıkar")) : (tr(t, "result_cut_keep", "Kesime geri al"))}
            className="p-1 rounded"
            style={{ color: "var(--mf-ink-3)" }}
          >
            {entry.included ? <Eye size={12} /> : <EyeOff size={12} />}
          </button>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={submit}
          disabled={busy || !kept.length || !dirty}
          className="inline-flex items-center gap-1.5 text-[11px] px-3 py-2 rounded-lg disabled:opacity-50"
          style={{ backgroundColor: "var(--mf-violet)", color: "white" }}
        >
          {busy ? <Loader2 size={12} className="animate-spin" /> : <Scissors size={12} />}
          {tr(t, "result_cut_apply", "Yeni kurguyu uygula (ücretsiz)")}
        </button>
        {!kept.length && (
          <span className="text-[11px]" style={{ color: "var(--mf-err-soft)" }}>
            {tr(t, "result_cut_empty", "En az bir sahne kalmalı.")}
          </span>
        )}
      </div>
      {error && <p className="text-[11px]" style={{ color: "var(--mf-err-soft)" }}>{error}</p>}
    </div>
  );
}

export default function VideoResult({ job, jobId }) {
  const { t } = useLanguage();
  const { getAccessToken } = useAuth();
  const result = job?.result;
  const [confetti, setConfetti] = useState(false);
  const [storyboardOpen, setStoryboardOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [exporting, setExporting] = useState(null); // "9:16" | "1:1" | null
  const [exportError, setExportError] = useState(null);
  const notifiedRef = useRef(false);

  useEffect(() => {
    if (!result || notifiedRef.current) return;
    notifiedRef.current = true;

    setConfetti(true);
    setTimeout(() => setConfetti(false), 5000);

    // Browser notification. The `"Notification" in window` guard only covered
    // the FIRST branch, so on a browser without the API (iOS Safari, and any
    // page served over plain http) the `else if` dereferenced an undefined
    // global and threw a ReferenceError — inside an effect, with no catch, so
    // the finished video the user had just paid for never rendered at all.
    const notifyTitle = t("result_ready");
    const notifyBody = { body: result.title || t("result_notify_body"), icon: "/favicon.ico" };
    if (typeof Notification !== "undefined") {
      try {
        if (Notification.permission === "default") {
          Notification.requestPermission().then((perm) => {
            if (perm === "granted") new Notification(notifyTitle, notifyBody);
          });
        } else if (Notification.permission === "granted") {
          new Notification(notifyTitle, notifyBody);
        }
      } catch {
        /* notifications blocked by policy — the page still works */
      }
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
  const warnings = Array.isArray(result.warnings) ? result.warnings : [];
  const portraits = result.portraits || {};
  // Only scenes whose clip was archived can be re-cut or spliced into.
  const editableScenes = scenes.filter(
    (scene) => scene.clip_index !== null && scene.clip_index !== undefined
  );
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
        <p className="text-sm mt-1" style={{ color: "var(--mf-ink-3)" }}>
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
          <p className="text-xs truncate" style={{ color: "var(--mf-ink-4)" }}>{result.logline}</p>
          <div className="flex flex-wrap items-center gap-2 flex-shrink-0 ml-auto">
            <a href={videoSrc} download
              className="inline-flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg font-medium"
              style={{ background: "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))", color: "#fff" }}>
              <Download size={13} />
              {t("result_download")}
            </a>
            {originalRatio !== "9:16" && (
              <button
                type="button"
                disabled={!!exporting}
                onClick={() => handleExport("9:16")}
                className="inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg font-medium disabled:opacity-50"
                style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink-2)" }}
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
                style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink-2)" }}
                title={t("result_export_crop_note")}
              >
                {exporting === "1:1" ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                {t("result_download_1_1")}
              </button>
            )}
          </div>
        </div>
        <p className="text-[10px] mt-2" style={{ color: "var(--mf-ink-4)" }}>{t("result_export_crop_note")}</p>
        {exportError && (
          <p className="text-xs mt-1" style={{ color: "var(--mf-err-soft)" }}>{exportError}</p>
        )}
      </div>

      {/* Anything the job was asked for and could not deliver. Every audio
          stage fails open server-side, so without this a video that is silent
          (or unscored) looks like a broken feature rather than a stated
          outcome. */}
      {warnings.length > 0 && (
        <div
          className="rounded-2xl px-4 py-3 mb-5 flex gap-3"
          style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)" }}
        >
          <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" style={{ color: "var(--mf-warn, #d9a441)" }} />
          <div>
            <p className="text-xs font-medium" style={{ color: "var(--mf-ink-2)" }}>
              {t("result_warnings_title")}
            </p>
            <ul className="text-xs mt-1 space-y-0.5 list-disc pl-4" style={{ color: "var(--mf-ink-3)" }}>
              {warnings.map((warning, i) => (
                <li key={i}>{warning}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div className="mb-5">
        <NextSteps jobId={jobId} videoUrl={result.video_url} />
      </div>

      {/* Post-production. Only offered when this job archived its scene clips
          — without them there is nothing to re-cut or splice into, and the
          server would refuse the request anyway. */}
      {editableScenes.length > 0 && (
        <div className="glass rounded-2xl mb-5">
          <button
            onClick={() => setEditOpen(!editOpen)}
            className="w-full flex items-center justify-between px-5 py-4"
          >
            <span className="text-sm font-medium flex items-center gap-2" style={{ color: "var(--mf-violet-soft)" }}>
              <Scissors size={15} />
              {tr(t, "result_edit_panel", "Kurgu ve düzeltmeler")}
            </span>
            {editOpen ? <ChevronUp size={15} style={{ color: "var(--mf-ink-3)" }} /> : <ChevronDown size={15} style={{ color: "var(--mf-ink-3)" }} />}
          </button>
          {editOpen && (
            <div className="px-5 pb-5 flex flex-col gap-5 animate-fade-in">
              <ContinuityEditPanel
                jobId={jobId}
                characters={Object.keys(portraits)}
                hasLocation={!!result.location_plate}
                onStarted={() => window.location.reload()}
              />
              <TimelinePanel
                jobId={jobId}
                scenes={editableScenes}
                onStarted={() => window.location.reload()}
              />
            </div>
          )}
        </div>
      )}

      {(scenes.length > 0 || Object.keys(portraits).length > 0) && (
        <div className="glass rounded-2xl">
          <button
            onClick={() => setStoryboardOpen(!storyboardOpen)}
            className="w-full flex items-center justify-between px-5 py-4"
          >
            <span className="text-sm font-medium flex items-center gap-2" style={{ color: "var(--mf-violet-soft)" }}>
              <Layout size={15} />
              {t("result_storyboard")}
            </span>
            {storyboardOpen ? <ChevronUp size={15} style={{ color: "var(--mf-ink-3)" }} /> : <ChevronDown size={15} style={{ color: "var(--mf-ink-3)" }} />}
          </button>

          {storyboardOpen && (
            <div className="px-5 pb-5 animate-fade-in">
              {Object.keys(portraits).length > 0 && (
                <div className="mb-4">
                  <p className="text-xs mb-2" style={{ color: "var(--mf-ink-3)" }}>{t("result_locked_chars")}</p>
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
                            style={{ border: "2px solid var(--mf-violet)" }} />
                          <span className="text-[10px] text-center" style={{ color: "var(--mf-ink-2)" }}>{name}</span>
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
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <p className="text-xs" style={{ color: "var(--mf-ink-3)" }}>
                      Scene {scene.index + 1}: {scene.script}
                      {scene.take > 1 && (
                        <span className="ml-2" style={{ color: "var(--mf-ink-4)" }}>
                          · {tr(t, "result_take_n", `çekim ${scene.take}`, { n: scene.take })}
                        </span>
                      )}
                    </p>
                    {/* Only offered when this job archived its scene clips —
                        older jobs cannot be spliced, and the server would
                        refuse the request anyway. */}
                    {scene.clip_index !== null && scene.clip_index !== undefined && (
                      <RetakeSceneButton
                        jobId={jobId}
                        sceneIndex={scene.index}
                        onStarted={() => window.location.reload()}
                      />
                    )}
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    {(scene.shots || []).filter(s => s.frame_url).map((shot, i) => (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img key={i} src={shot.frame_url} alt={shot.visual_desc || `Frame ${i + 1}`}
                        className="w-full aspect-video object-cover rounded-lg"
                        style={{ border: "1px solid var(--mf-line-strong)" }} />
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
