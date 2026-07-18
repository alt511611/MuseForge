"use client";

import { useState, useEffect } from "react";
import {
  Sparkles,
  Clapperboard,
  Monitor,
  Film,
  ChevronDown,
  Loader2,
  Clock,
  FlaskConical,
  Upload,
  X,
} from "lucide-react";

import { useLanguage } from "../contexts/LanguageContext";
import { API_BASE } from "../lib/apiBase";

const MAX_UPLOAD_BYTES = 5 * 1024 * 1024; // 5MB — keep in sync with server/constants.py

const STYLES = [
  "Cinematic",
  "Noir",
  "Sci-Fi",
  "Fantasy",
  "Horror",
  "Romance",
  "Documentary",
  "Anime",
];

const DIRECTOR_STYLES = [
  { id: "slow_cinematic", label: "Slow Cinematic", desc: "Long takes, breathing room" },
  { id: "cinematic_balanced", label: "Balanced", desc: "Classic film pacing" },
  { id: "dynamic_action", label: "Dynamic Action", desc: "Fast cuts, high energy" },
  { id: "intimate_closeup", label: "Intimate", desc: "Close-ups, emotional depth" },
  { id: "noir_mystery", label: "Noir Mystery", desc: "Shadows, tension, clues" },
  { id: "anime_expressive", label: "Anime", desc: "Bold, expressive frames" },
];

const ASPECT_RATIOS = [
  { id: "16:9", label: "Landscape 16:9", icon: Monitor },
  { id: "9:16", label: "Vertical 9:16", icon: Film },
  { id: "1:1", label: "Square 1:1", icon: Clapperboard },
];

export default function IdeaForm({ onSubmit, isSubmitting, prefill }) {
  const { t } = useLanguage();
  const [idea, setIdea] = useState("");
  const [style, setStyle] = useState("Cinematic");
  const [directorStyle, setDirectorStyle] = useState("cinematic_balanced");
  const [aspectRatio, setAspectRatio] = useState("16:9");
  const [numScenes, setNumScenes] = useState(3);
  const [userRequirement, setUserRequirement] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [charCount, setCharCount] = useState(0);
  const [estimate, setEstimate] = useState(null);
  const [demoMode, setDemoMode] = useState(false);
  const [characterImage, setCharacterImage] = useState(null);
  const [characterName, setCharacterName] = useState("");
  const [uploadError, setUploadError] = useState(null);

  // Allows landing-page example cards to pre-fill idea + style, and
  // scrolls the form into view so the click feels responsive.
  useEffect(() => {
    if (!prefill) return;
    if (prefill.idea) setIdea(prefill.idea);
    if (prefill.style) setStyle(prefill.style);
    if (prefill.directorStyle) setDirectorStyle(prefill.directorStyle);
  }, [prefill]);

  useEffect(() => {
    setCharCount(idea.length);
  }, [idea]);

  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setDemoMode(!!d.demo_mode))
      .catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/api/estimate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ num_scenes: numScenes }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => !cancelled && d && setEstimate(d))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [numScenes]);

  const handlePhotoUpload = (e) => {
    const file = e.target.files?.[0];
    setUploadError(null);
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadError(t("form_photo_size_error") || "Photo must be smaller than 5MB.");
      e.target.value = "";
      return;
    }
    if (!file.type.startsWith("image/")) {
      setUploadError(t("form_photo_type_error") || "Please select an image file.");
      e.target.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => setCharacterImage(ev.target.result);
    reader.readAsDataURL(file);
  };

  const clearPhoto = () => {
    setCharacterImage(null);
    setCharacterName("");
    setUploadError(null);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!idea.trim() || isSubmitting) return;
    onSubmit({
      idea: idea.trim(),
      style,
      director_style: directorStyle,
      aspect_ratio: aspectRatio,
      num_scenes: numScenes,
      user_requirement: userRequirement.trim(),
      character_image: characterImage,
      character_name: characterImage ? characterName.trim() : "",
    });
  };

  return (
    <form onSubmit={handleSubmit} className="glass rounded-2xl p-8 border-glow">
      <div className="mb-6">
        <label
          htmlFor="idea"
          className="flex items-center gap-2 text-sm font-medium mb-3"
          style={{ color: "#a78bfa" }}
        >
          <Sparkles size={16} />
          {t("form_idea_label")}
        </label>
        <textarea
          id="idea"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder={t("form_idea_hint")}
          rows={4}
          maxLength={2000}
          className="w-full px-4 py-3 rounded-xl text-base resize-none transition-all focus:outline-none"
          style={{
            backgroundColor: "#0a0a0f",
            border: "1px solid #22223a",
            color: "#e2e8f0",
          }}
          disabled={isSubmitting}
        />
        <div className="flex justify-between mt-2 text-xs" style={{ color: "#64748b" }}>
          <span>{t("form_idea_hint")}</span>
          <span>{charCount}/2000</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div>
          <label className="text-sm font-medium mb-2 block" style={{ color: "#94a3b8" }}>
            {t("form_style_label")}
          </label>
          <select
            value={style}
            onChange={(e) => setStyle(e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl text-sm focus:outline-none"
            style={{
              backgroundColor: "#0a0a0f",
              border: "1px solid #22223a",
              color: "#e2e8f0",
            }}
            disabled={isSubmitting}
          >
            {STYLES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-sm font-medium mb-2 block" style={{ color: "#94a3b8" }}>
            {t("form_director_label")}
          </label>
          <select
            value={directorStyle}
            onChange={(e) => setDirectorStyle(e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl text-sm focus:outline-none"
            style={{
              backgroundColor: "#0a0a0f",
              border: "1px solid #22223a",
              color: "#e2e8f0",
            }}
            disabled={isSubmitting}
          >
            {DIRECTOR_STYLES.map((d) => (
              <option key={d.id} value={d.id}>
                {d.label} — {d.desc}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mb-6">
        <label className="text-sm font-medium mb-3 block" style={{ color: "#94a3b8" }}>
          {t("form_ratio_label")}
        </label>
        <div className="grid grid-cols-3 gap-3">
          {ASPECT_RATIOS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setAspectRatio(id)}
              className="flex flex-col items-center gap-2 px-4 py-3 rounded-xl text-sm transition-all"
              style={{
                backgroundColor: aspectRatio === id ? "rgba(124, 58, 237, 0.15)" : "#0a0a0f",
                border: aspectRatio === id ? "1px solid #7c3aed" : "1px solid #22223a",
                color: aspectRatio === id ? "#a78bfa" : "#94a3b8",
              }}
              disabled={isSubmitting}
            >
              <Icon size={18} />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-6">
        <label className="text-sm font-medium mb-2 block" style={{ color: "#94a3b8" }}>
          {t("form_char_label")}{" "}
          <span style={{ color: "#4b5563", fontWeight: 400 }}>{t("form_char_optional")}</span>
        </label>
        <p className="text-xs mb-3" style={{ color: "#64748b" }}>
          {t("form_char_desc")}
        </p>
        {!characterImage ? (
          <>
            <input
              type="file"
              accept="image/*"
              onChange={handlePhotoUpload}
              className="hidden"
              id="character-photo-upload"
              disabled={isSubmitting}
            />
            <label
              htmlFor="character-photo-upload"
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm cursor-pointer transition-all"
              style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a", color: "#94a3b8" }}
            >
              <Upload size={15} />
              {t("form_upload_btn")}
            </label>
          </>
        ) : (
          <div className="flex items-center gap-3">
            <img
              src={characterImage}
              alt="Karakter önizleme"
              className="w-12 h-12 rounded-full object-cover"
              style={{ border: "2px solid #7c3aed" }}
            />
            <input
              type="text"
              value={characterName}
              onChange={(e) => setCharacterName(e.target.value)}
              placeholder={t("form_char_name_ph")}
              maxLength={60}
              className="flex-1 px-4 py-2.5 rounded-xl text-sm focus:outline-none"
              style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a", color: "#e2e8f0" }}
              disabled={isSubmitting}
            />
            <button
              type="button"
              onClick={clearPhoto}
              className="p-2 rounded-lg transition-colors"
              style={{ color: "#64748b" }}
              disabled={isSubmitting}
              aria-label="Fotoğrafı kaldır"
            >
              <X size={16} />
            </button>
          </div>
        )}
        {uploadError && (
          <p className="text-xs mt-2" style={{ color: "#fca5a5" }}>{uploadError}</p>
        )}
        {characterImage && !characterName.trim() && (
          <p className="text-xs mt-2" style={{ color: "#fde047" }}>
            {t("form_char_name_warning") || "Enter the character name so the script can match this photo to the right character."}
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex items-center gap-2 text-sm mb-4 transition-colors"
        style={{ color: "#64748b" }}
      >
        <ChevronDown
          size={16}
          className={`transition-transform ${showAdvanced ? "rotate-180" : ""}`}
        />
        {t("form_advanced")}
      </button>

      {showAdvanced && (
        <div className="mb-6 space-y-4 animate-fade-in">
          <div>
            <label className="text-sm font-medium mb-2 block" style={{ color: "#94a3b8" }}>
              {t("form_scenes_label")} ({numScenes})
            </label>
            <input
              type="range"
              min={2}
              max={5}
              value={numScenes}
              onChange={(e) => setNumScenes(Number(e.target.value))}
              className="w-full accent-purple-500"
              disabled={isSubmitting}
            />
            <div className="flex justify-between text-xs mt-1" style={{ color: "#64748b" }}>
              <span>2 scenes (~16s)</span>
              <span>5 scenes (~40s)</span>
            </div>
          </div>
          <div>
            <label className="text-sm font-medium mb-2 block" style={{ color: "#94a3b8" }}>
              {t("form_req_label")}
            </label>
            <input
              type="text"
              value={userRequirement}
              onChange={(e) => setUserRequirement(e.target.value)}
              placeholder={t("form_req_ph")}
              className="w-full px-4 py-2.5 rounded-xl text-sm focus:outline-none"
              style={{
                backgroundColor: "#0a0a0f",
                border: "1px solid #22223a",
                color: "#e2e8f0",
              }}
              disabled={isSubmitting}
            />
          </div>
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-4 text-xs" style={{ color: "#64748b" }}>
        <span className="inline-flex items-center gap-1.5">
          <Clock size={13} />
          {estimate
            ? t("form_est_render", {
                label: estimate.estimated_label,
                frames: estimate.asset_count.frames,
                clips: estimate.asset_count.clips,
              })
            : t("form_est_loading")}
        </span>
        {demoMode ? (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full"
            style={{ backgroundColor: "rgba(124,58,237,0.15)", color: "#a78bfa" }}
          >
            <FlaskConical size={11} /> {t("form_demo_badge")}
          </span>
        ) : (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full"
            style={{ backgroundColor: "rgba(251,191,36,0.12)", color: "#fbbf24" }}
          >
            <Sparkles size={11} /> {t("form_credit_cost", { n: numScenes })}
          </span>
        )}
      </div>

      <button
        type="submit"
        disabled={!idea.trim() || isSubmitting}
        className="w-full py-4 rounded-xl font-semibold text-base transition-all flex items-center justify-center gap-2"
        style={{
          background: isSubmitting
            ? "#4c1d95"
            : "linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)",
          color: "#fff",
          opacity: !idea.trim() ? 0.5 : 1,
          cursor: !idea.trim() || isSubmitting ? "not-allowed" : "pointer",
        }}
      >
        {isSubmitting ? (
          <>
            <Loader2 size={20} className="animate-spin" />
            {t("form_generating")}
          </>
        ) : (
          <>
            <Clapperboard size={20} />
            {t("form_generate")}
          </>
        )}
      </button>
    </form>
  );
}
