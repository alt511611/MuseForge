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
  Music,
} from "lucide-react";

import { useLanguage } from "../contexts/LanguageContext";
import { useAuth } from "../contexts/AuthContext";
import { createClient } from "../lib/supabase";
import { API_BASE } from "../lib/apiBase";

// Plans allowed to attach optional background music. Kept in sync with the
// server-side gate in server/api.py (music_enabled is silently ignored for
// any other plan).
const MUSIC_ELIGIBLE_PLANS = ["creator", "pro"];

// Real, currently-enforced scene caps. Kept in sync with server/api.py's
// PLAN_MAX_SCENES — this just avoids the user hitting a 400 after the fact.
const PLAN_MAX_SCENES = { free: 3, creator: 3, pro: 5 };

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
  const { user, getAccessToken } = useAuth();
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
  const [plan, setPlan] = useState(null);
  const [musicEnabled, setMusicEnabled] = useState(false);
  const [requireScriptApproval, setRequireScriptApproval] = useState(false);
  const [libraryCharacters, setLibraryCharacters] = useState([]);
  const [selectedLibraryIds, setSelectedLibraryIds] = useState([]);

  // Look up the signed-in user's plan (Creator/Pro unlock optional music +
  // a higher scene cap). Anonymous/free users simply never see the toggle.
  useEffect(() => {
    if (!user) {
      setPlan(null);
      return;
    }
    let cancelled = false;
    const supabase = createClient();
    if (!supabase) return;
    supabase
      .from("profiles")
      .select("plan")
      .eq("id", user.id)
      .single()
      .then(({ data, error }) => {
        if (cancelled) return;
        if (error) {
          // Supabase JS returns query errors (RLS denial, 0/2+ rows from
          // .single(), etc.) as { data: null, error } -- it does NOT throw
          // for these, so the .catch() below never fires for them. The
          // previous code only checked `data`, meaning any such error
          // silently left `plan` as null forever with zero visibility --
          // indistinguishable from "you're on the free plan" in the UI,
          // and nothing logged anywhere to diagnose it.
          console.error("Failed to fetch user plan (music toggle will stay hidden):", error);
          return;
        }
        if (data) setPlan(data.plan);
      })
      .catch((err) => {
        if (!cancelled) console.error("Failed to fetch user plan (network/client error):", err);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const musicEligible = MUSIC_ELIGIBLE_PLANS.includes(plan);
  const maxScenes = PLAN_MAX_SCENES[plan] ?? 5;
  const libraryEligible = plan === "pro";

  // Pro-only: load saved characters for multi-select reuse.
  useEffect(() => {
    if (!user || !libraryEligible) {
      setLibraryCharacters([]);
      setSelectedLibraryIds([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const token = await getAccessToken();
        if (!token || cancelled) return;
        const res = await fetch(`${API_BASE}/api/characters`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok || cancelled) return;
        const data = await res.json();
        if (!cancelled) setLibraryCharacters(Array.isArray(data.characters) ? data.characters : []);
      } catch {
        /* ignore — picker simply stays empty */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user, libraryEligible, getAccessToken]);

  useEffect(() => {
    if (!musicEligible && musicEnabled) setMusicEnabled(false);
  }, [musicEligible, musicEnabled]);

  useEffect(() => {
    if (numScenes > maxScenes) setNumScenes(maxScenes);
  }, [maxScenes, numScenes]);

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
      body: JSON.stringify({
        num_scenes: numScenes,
        music_enabled: musicEligible && musicEnabled,
        dialogue_enabled: false,
        plan: plan || "free",
      }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => !cancelled && d && setEstimate(d))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [numScenes, musicEligible, musicEnabled, plan]);

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
    const selectedLibraryCharacters =
      libraryEligible
        ? libraryCharacters
            .filter((c) => selectedLibraryIds.includes(c.id))
            .map((c) => ({
              name: c.name,
              static_features: c.static_features,
              portrait_url: c.portrait_url,
            }))
        : [];
    onSubmit({
      idea: idea.trim(),
      style,
      director_style: directorStyle,
      aspect_ratio: aspectRatio,
      num_scenes: numScenes,
      user_requirement: userRequirement.trim(),
      character_image: characterImage,
      character_name: characterImage ? characterName.trim() : "",
      music_enabled: musicEligible && musicEnabled,
      require_script_approval: requireScriptApproval,
      library_characters: selectedLibraryCharacters,
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

      {libraryEligible && libraryCharacters.length > 0 && (
        <div className="mb-6">
          <label className="text-sm font-medium mb-2 block" style={{ color: "#94a3b8" }}>
            {t("form_library_chars") || "Kayıtlı karakterlerimden seç"}
          </label>
          <p className="text-xs mb-3" style={{ color: "#64748b" }}>
            {t("form_library_chars_hint") || "Seçilen karakterler senaryoya doğrudan dahil edilir."}
          </p>
          <div className="flex flex-wrap gap-3">
            {libraryCharacters.map((c) => {
              const selected = selectedLibraryIds.includes(c.id);
              return (
                <button
                  key={c.id}
                  type="button"
                  disabled={isSubmitting}
                  onClick={() =>
                    setSelectedLibraryIds((prev) =>
                      selected ? prev.filter((id) => id !== c.id) : [...prev, c.id]
                    )
                  }
                  className="flex items-center gap-2 px-3 py-2 rounded-xl text-left transition-all"
                  style={{
                    backgroundColor: selected ? "rgba(124, 58, 237, 0.15)" : "#0a0a0f",
                    border: selected ? "1px solid #7c3aed" : "1px solid #22223a",
                  }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={c.portrait_url}
                    alt={c.name}
                    className="w-9 h-9 rounded-full object-cover"
                    style={{ border: "1px solid #7c3aed" }}
                  />
                  <span className="text-xs" style={{ color: selected ? "#a78bfa" : "#94a3b8" }}>
                    {c.name}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

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
              max={maxScenes}
              value={Math.min(numScenes, maxScenes)}
              onChange={(e) => setNumScenes(Number(e.target.value))}
              className="w-full accent-purple-500"
              disabled={isSubmitting}
            />
            <div className="flex justify-between text-xs mt-1" style={{ color: "#64748b" }}>
              <span>2 scenes (~16s)</span>
              <span>{maxScenes} scenes (~{maxScenes * 8}s)</span>
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

      {musicEligible && (
        <div className="flex items-center justify-between gap-3 mb-4 px-4 py-3 rounded-xl" style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a" }}>
          <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: "#94a3b8" }}>
            <Music size={16} style={{ color: "#a78bfa" }} />
            {t("form_music_toggle")}
          </label>
          <div className="flex items-center gap-3">
            {musicEnabled && !demoMode && (
              <span className="text-xs" style={{ color: "#fbbf24" }}>
                {t("form_music_credit_note", { n: numScenes + 1 })}
              </span>
            )}
            <button
              type="button"
              role="switch"
              aria-checked={musicEnabled}
              onClick={() => setMusicEnabled((v) => !v)}
              disabled={isSubmitting}
              className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors"
              style={{ backgroundColor: musicEnabled ? "#7c3aed" : "#22223a" }}
            >
              <span
                className="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
                style={{ transform: musicEnabled ? "translateX(18px)" : "translateX(2px)" }}
              />
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-3 mb-4 px-4 py-3 rounded-xl" style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a" }}>
        <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: "#94a3b8" }}>
          <Clapperboard size={16} style={{ color: "#a78bfa" }} />
          <span>
            {t("form_script_approval_toggle")}
            <span className="block text-[11px] mt-0.5" style={{ color: "#475569" }}>
              {t("form_script_approval_hint")}
            </span>
          </span>
        </label>
        <button
          type="button"
          role="switch"
          aria-checked={requireScriptApproval}
          onClick={() => setRequireScriptApproval((v) => !v)}
          disabled={isSubmitting}
          className="relative inline-flex h-5 w-9 flex-shrink-0 items-center rounded-full transition-colors"
          style={{ backgroundColor: requireScriptApproval ? "#7c3aed" : "#22223a" }}
        >
          <span
            className="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
            style={{ transform: requireScriptApproval ? "translateX(18px)" : "translateX(2px)" }}
          />
        </button>
      </div>

      <div className="flex flex-col gap-1.5 mb-4 text-xs" style={{ color: "#64748b" }}>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
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
              <Sparkles size={11} />{" "}
              {t("form_credit_cost", {
                n:
                  typeof estimate?.total_credits === "number"
                    ? estimate.total_credits
                    : musicEligible && musicEnabled
                      ? numScenes + 1
                      : numScenes,
              })}
            </span>
          )}
        </div>
        {!demoMode && Array.isArray(estimate?.breakdown) && estimate.breakdown.length > 0 && (
          <ul className="sm:self-end space-y-0.5 text-[11px] leading-relaxed" style={{ color: "#64748b" }}>
            {estimate.breakdown.map((row) => (
              <li key={row.label}>
                {row.label}: {row.credits}
              </li>
            ))}
          </ul>
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
