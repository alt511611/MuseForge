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
  MessagesSquare,
  MapPin,
  AudioLines,
} from "lucide-react";

import { useLanguage } from "../contexts/LanguageContext";
import { useAuth } from "../contexts/AuthContext";
import { API_BASE } from "../lib/apiBase";
import { tr } from "../lib/tr";

// Plans allowed to attach optional background music. Kept in sync with the
// server-side gate in server/api.py (music_enabled is silently ignored for
// any other plan).
const MUSIC_ELIGIBLE_PLANS = ["creator", "pro"];

// Lip sync is Pro-only too, and additionally requires dialogue: with no
// generated voice there is nothing to sync a mouth to. The deployment-level
// readiness (feature flag + fal.ai key) arrives as health.lipsync_available.
const LIPSYNC_ELIGIBLE_PLANS = ["pro"];

// Plans allowed to attach spoken character dialogue. Kept in sync with the
// server-side gate in server/api.py (dialogue_enabled is Pro-only there).
// Dialogue is ALSO behind a server feature flag, surfaced as
// health.dialogue_available -- both must hold before the toggle is offered.
const DIALOGUE_ELIGIBLE_PLANS = ["pro"];

// Real, currently-enforced scene caps. Kept in sync with server/api.py's
// PLAN_MAX_SCENES — this just avoids the user hitting a 400 after the fact.
// Avg ~7.5s/scene → Pro 24 ≈ up to ~3 min of finished video.
const PLAN_MAX_SCENES = { free: 8, creator: 16, pro: 24 };
const AVG_SCENE_SECONDS = 7.5;

function formatVideoDuration(sceneCount) {
  const secs = Math.round(sceneCount * AVG_SCENE_SECONDS);
  if (secs < 60) return `~${secs}s`;
  const mins = secs / 60;
  const label = Number.isInteger(mins) ? String(mins) : mins.toFixed(1).replace(/\.0$/, "");
  return `~${label} min`;
}

const MAX_UPLOAD_BYTES = 5 * 1024 * 1024; // 5MB — keep in sync with server/constants.py

// Long enough to absorb the first-paint burst (plan + dialogue availability
// landing a few ms apart) and slider drags, short enough that the cost
// estimate still feels live.
const ESTIMATE_DEBOUNCE_MS = 300;

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
  const { user, profile, getAccessToken } = useAuth();
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
  const [locationImage, setLocationImage] = useState(null);
  const [locationError, setLocationError] = useState(null);
  const [lipsyncAvailable, setLipsyncAvailable] = useState(false);
  const [lipsyncEnabled, setLipsyncEnabled] = useState(false);
  const [musicEnabled, setMusicEnabled] = useState(false);
  const [dialogueEnabled, setDialogueEnabled] = useState(false);
  const [dialogueAvailable, setDialogueAvailable] = useState(false);
  // ON by default. The script step is the only place the user's own intention
  // enters the film -- everything after it is the pipeline executing a brief it
  // has already committed to. Defaulted off, the product's normal path was a
  // one-line idea going straight to a finished master, which is the workflow
  // that reliably produces something that looks expensive and means nothing.
  //
  // It costs a click, not money: credits are charged on approval, not on
  // submit, so the default also stops a misread brief from spending anything.
  const [requireScriptApproval, setRequireScriptApproval] = useState(true);
  const [libraryCharacters, setLibraryCharacters] = useState([]);
  const [selectedLibraryIds, setSelectedLibraryIds] = useState([]);

  // The signed-in user's plan (Creator/Pro unlock optional music + a higher
  // scene cap) comes from AuthContext, which fetches the profile row once per
  // user -- this component used to run its own query alongside Navbar's,
  // hitting the same row twice on a single page load. Anonymous/free users
  // simply never see the toggle.
  const plan = profile?.plan ?? null;

  const musicEligible = MUSIC_ELIGIBLE_PLANS.includes(plan);
  const dialogueEligible =
    dialogueAvailable && DIALOGUE_ELIGIBLE_PLANS.includes(plan);
  const lipsyncEligible =
    lipsyncAvailable && LIPSYNC_ELIGIBLE_PLANS.includes(plan);
  const maxScenes = PLAN_MAX_SCENES[plan] ?? PLAN_MAX_SCENES.free;
  const libraryEligible = plan === "pro";

  // If the user's plan loads with a lower cap than the current slider value,
  // clamp so we never submit above what the server will accept.
  useEffect(() => {
    if (numScenes > maxScenes) setNumScenes(maxScenes);
  }, [maxScenes, numScenes]);
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
    if (!dialogueEligible && dialogueEnabled) setDialogueEnabled(false);
  }, [dialogueEligible, dialogueEnabled]);

  // Turning dialogue back off must clear lip sync too, or the estimate would
  // keep quoting a stage the server is about to drop (it requires dialogue).
  useEffect(() => {
    if ((!lipsyncEligible || !dialogueEnabled) && lipsyncEnabled) {
      setLipsyncEnabled(false);
    }
  }, [lipsyncEligible, dialogueEnabled, lipsyncEnabled]);

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
      .then((d) => {
        if (!d) return;
        setDemoMode(!!d.demo_mode);
        setDialogueAvailable(!!d.dialogue_available);
        setLipsyncAvailable(!!d.lipsync_available);
      })
      .catch(() => {});
  }, []);

  // Debounced: the inputs below settle in a burst on first paint (`plan`
  // arrives from the profile fetch, `dialogueEligible` flips once
  // /api/health resolves), which previously fired three separate POSTs for
  // one page load. Dragging the scene slider had the same problem -- one
  // request per intermediate value. Waiting out the burst collapses each of
  // those into a single request.
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      fetch(`${API_BASE}/api/estimate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          num_scenes: numScenes,
          music_enabled: musicEligible && musicEnabled,
          dialogue_enabled: dialogueEligible && dialogueEnabled,
          lipsync_enabled: lipsyncEligible && dialogueEnabled && lipsyncEnabled,
          plan: plan || "free",
        }),
      })
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => !cancelled && d && setEstimate(d))
        .catch(() => {});
    }, ESTIMATE_DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [
    numScenes,
    musicEligible,
    musicEnabled,
    dialogueEligible,
    dialogueEnabled,
    lipsyncEligible,
    lipsyncEnabled,
    plan,
  ]);

  const handlePhotoUpload = (e) => {
    const file = e.target.files?.[0];
    setUploadError(null);
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadError(tr(t, "form_photo_size_error", "Photo must be smaller than 5MB."));
      e.target.value = "";
      return;
    }
    if (!file.type.startsWith("image/")) {
      setUploadError(tr(t, "form_photo_type_error", "Please select an image file."));
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

  const handleLocationUpload = (e) => {
    const file = e.target.files?.[0];
    setLocationError(null);
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setLocationError(tr(t, "form_photo_size_error", "Photo must be smaller than 5MB."));
      e.target.value = "";
      return;
    }
    if (!file.type.startsWith("image/")) {
      setLocationError(tr(t, "form_photo_type_error", "Please select an image file."));
      e.target.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = (ev) => setLocationImage(ev.target.result);
    reader.readAsDataURL(file);
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
              // Sent back so a returning character speaks with the voice
              // they were first cast with. Empty for entries saved before
              // the library stored one, which simply re-cast as before.
              voice_id: c.voice_id || "",
              // Same reason as the voice: the reference portrait cannot carry
              // an outfit, so it travels as text or it does not travel.
              wardrobe: c.wardrobe || "",
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
      location_image: locationImage,
      music_enabled: musicEligible && musicEnabled,
      dialogue_enabled: dialogueEligible && dialogueEnabled,
      lipsync_enabled: lipsyncEligible && dialogueEnabled && lipsyncEnabled,
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
          style={{ color: "var(--mf-violet-soft)" }}
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
            backgroundColor: "var(--mf-stage)",
            border: "1px solid var(--mf-line-strong)",
            color: "var(--mf-ink)",
          }}
          disabled={isSubmitting}
        />
        <div className="flex justify-between mt-2 text-xs" style={{ color: "var(--mf-ink-3)" }}>
          <span>{t("form_idea_hint")}</span>
          <span>{charCount}/2000</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div>
          <label className="text-sm font-medium mb-2 block" style={{ color: "var(--mf-ink-2)" }}>
            {t("form_style_label")}
          </label>
          <select
            value={style}
            onChange={(e) => setStyle(e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl text-sm focus:outline-none"
            style={{
              backgroundColor: "var(--mf-stage)",
              border: "1px solid var(--mf-line-strong)",
              color: "var(--mf-ink)",
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
          <label className="text-sm font-medium mb-2 block" style={{ color: "var(--mf-ink-2)" }}>
            {t("form_director_label")}
          </label>
          <select
            value={directorStyle}
            onChange={(e) => setDirectorStyle(e.target.value)}
            className="w-full px-4 py-2.5 rounded-xl text-sm focus:outline-none"
            style={{
              backgroundColor: "var(--mf-stage)",
              border: "1px solid var(--mf-line-strong)",
              color: "var(--mf-ink)",
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
        <label className="text-sm font-medium mb-3 block" style={{ color: "var(--mf-ink-2)" }}>
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
                backgroundColor: aspectRatio === id ? "rgba(139, 92, 246, 0.15)" : "var(--mf-stage)",
                border: aspectRatio === id ? "1px solid var(--mf-violet)" : "1px solid var(--mf-line-strong)",
                color: aspectRatio === id ? "var(--mf-violet-soft)" : "var(--mf-ink-2)",
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
        <label className="text-sm font-medium mb-2 block" style={{ color: "var(--mf-ink-2)" }}>
          {t("form_char_label")}{" "}
          <span style={{ color: "var(--mf-ink-4)", fontWeight: 400 }}>{t("form_char_optional")}</span>
        </label>
        <p className="text-xs mb-3" style={{ color: "var(--mf-ink-3)" }}>
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
              style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink-2)" }}
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
              style={{ border: "2px solid var(--mf-violet)" }}
            />
            <input
              type="text"
              value={characterName}
              onChange={(e) => setCharacterName(e.target.value)}
              placeholder={t("form_char_name_ph")}
              maxLength={60}
              className="flex-1 px-4 py-2.5 rounded-xl text-sm focus:outline-none"
              style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
              disabled={isSubmitting}
            />
            <button
              type="button"
              onClick={clearPhoto}
              className="p-2 rounded-lg transition-colors"
              style={{ color: "var(--mf-ink-3)" }}
              disabled={isSubmitting}
              aria-label="Fotoğrafı kaldır"
            >
              <X size={16} />
            </button>
          </div>
        )}
        {uploadError && (
          <p className="text-xs mt-2" style={{ color: "var(--mf-err-soft)" }}>{uploadError}</p>
        )}
        {characterImage && !characterName.trim() && (
          <p className="text-xs mt-2" style={{ color: "var(--mf-gold)" }}>
            {tr(t, "form_char_name_warning", "Enter the character name so the script can match this photo to the right character.")}
          </p>
        )}
      </div>

      <div className="mb-6">
        <label className="text-sm font-medium mb-2 block" style={{ color: "var(--mf-ink-2)" }}>
          {tr(t, "form_location_label", "Mekân fotoğrafı")}{" "}
          <span style={{ color: "var(--mf-ink-4)", fontWeight: 400 }}>{t("form_char_optional")}</span>
        </label>
        <p className="text-xs mb-3" style={{ color: "var(--mf-ink-3)" }}>
          {tr(t, "form_location_desc", "Yüklerseniz her sahne bu mekânda geçer. Yüklemezseniz senaryonun mekânı bir kez üretilip tüm sahnelerde aynı kalır.")}
        </p>
        {!locationImage ? (
          <>
            <input
              type="file"
              accept="image/*"
              onChange={handleLocationUpload}
              className="hidden"
              id="location-photo-upload"
              disabled={isSubmitting}
            />
            <label
              htmlFor="location-photo-upload"
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm cursor-pointer transition-all"
              style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink-2)" }}
            >
              <MapPin size={15} />
              {tr(t, "form_location_upload_btn", "Mekân fotoğrafı yükle")}
            </label>
          </>
        ) : (
          <div className="flex items-center gap-3">
            <img
              src={locationImage}
              alt={tr(t, "form_location_preview_alt", "Mekân önizleme")}
              className="w-16 h-10 rounded-lg object-cover"
              style={{ border: "2px solid var(--mf-violet)" }}
            />
            <span className="flex-1 text-xs" style={{ color: "var(--mf-ink-3)" }}>
              {tr(t, "form_location_locked", "Bu mekân tüm sahnelerde kilitlenecek.")}
            </span>
            <button
              type="button"
              onClick={() => {
                setLocationImage(null);
                setLocationError(null);
              }}
              className="p-2 rounded-lg transition-colors"
              style={{ color: "var(--mf-ink-3)" }}
              disabled={isSubmitting}
              aria-label={tr(t, "form_location_remove", "Mekân fotoğrafını kaldır")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {locationError && (
          <p className="text-xs mt-2" style={{ color: "var(--mf-err-soft)" }}>{locationError}</p>
        )}
      </div>

      {libraryEligible && libraryCharacters.length > 0 && (
        <div className="mb-6">
          <label className="text-sm font-medium mb-2 block" style={{ color: "var(--mf-ink-2)" }}>
            {tr(t, "form_library_chars", "Kayıtlı karakterlerimden seç")}
          </label>
          <p className="text-xs mb-3" style={{ color: "var(--mf-ink-3)" }}>
            {tr(t, "form_library_chars_hint", "Seçilen karakterler senaryoya doğrudan dahil edilir.")}
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
                    backgroundColor: selected ? "rgba(139, 92, 246, 0.15)" : "var(--mf-stage)",
                    border: selected ? "1px solid var(--mf-violet)" : "1px solid var(--mf-line-strong)",
                  }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={c.portrait_url}
                    alt={c.name}
                    className="w-9 h-9 rounded-full object-cover"
                    style={{ border: "1px solid var(--mf-violet)" }}
                  />
                  <span className="text-xs" style={{ color: selected ? "var(--mf-violet-soft)" : "var(--mf-ink-2)" }}>
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
        style={{ color: "var(--mf-ink-3)" }}
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
            <label className="text-sm font-medium mb-2 block" style={{ color: "var(--mf-ink-2)" }}>
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
            <div className="flex justify-between text-xs mt-1" style={{ color: "var(--mf-ink-3)" }}>
              <span>2 scenes ({formatVideoDuration(2)})</span>
              <span>
                {maxScenes} scenes ({formatVideoDuration(maxScenes)})
              </span>
            </div>
            {plan !== "pro" && numScenes >= maxScenes && (
              <p className="text-xs mt-2" style={{ color: "var(--mf-gold)" }}>
                {t("form_scenes_upgrade_hint", { max: maxScenes })}
              </p>
            )}
          </div>
          <div>
            <label className="text-sm font-medium mb-2 block" style={{ color: "var(--mf-ink-2)" }}>
              {t("form_req_label")}
            </label>
            <input
              type="text"
              value={userRequirement}
              onChange={(e) => setUserRequirement(e.target.value)}
              placeholder={t("form_req_ph")}
              className="w-full px-4 py-2.5 rounded-xl text-sm focus:outline-none"
              style={{
                backgroundColor: "var(--mf-stage)",
                border: "1px solid var(--mf-line-strong)",
                color: "var(--mf-ink)",
              }}
              disabled={isSubmitting}
            />
          </div>
        </div>
      )}

      {musicEligible && (
        <div className="flex items-center justify-between gap-3 mb-4 px-4 py-3 rounded-xl" style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)" }}>
          <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: "var(--mf-ink-2)" }}>
            <Music size={16} style={{ color: "var(--mf-violet-soft)" }} />
            {t("form_music_toggle")}
          </label>
          <div className="flex items-center gap-3">
            {musicEnabled && !demoMode && (
              <span className="text-xs" style={{ color: "var(--mf-gold)" }}>
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
              style={{ backgroundColor: musicEnabled ? "var(--mf-violet)" : "var(--mf-line-strong)" }}
            >
              <span
                className="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
                style={{ transform: musicEnabled ? "translateX(18px)" : "translateX(2px)" }}
              />
            </button>
          </div>
        </div>
      )}

      {dialogueEligible && (
        <div className="flex items-center justify-between gap-3 mb-4 px-4 py-3 rounded-xl" style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)" }}>
          <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: "var(--mf-ink-2)" }}>
            <MessagesSquare size={16} style={{ color: "var(--mf-violet-soft)" }} />
            <span>
              {t("form_dialogue_toggle")}
              <span className="block text-[11px] mt-0.5" style={{ color: "var(--mf-ink-4)" }}>
                {t("form_dialogue_hint")}
              </span>
            </span>
          </label>
          <div className="flex items-center gap-3">
            {dialogueEnabled && !demoMode && (
              <span className="text-xs" style={{ color: "var(--mf-gold)" }}>
                {t("form_dialogue_credit_note", {
                  n:
                    numScenes +
                    numScenes +
                    (musicEligible && musicEnabled ? 1 : 0),
                })}
              </span>
            )}
            <button
              type="button"
              role="switch"
              aria-checked={dialogueEnabled}
              onClick={() => setDialogueEnabled((v) => !v)}
              disabled={isSubmitting}
              className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors"
              style={{ backgroundColor: dialogueEnabled ? "var(--mf-violet)" : "var(--mf-line-strong)" }}
            >
              <span
                className="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
                style={{ transform: dialogueEnabled ? "translateX(18px)" : "translateX(2px)" }}
              />
            </button>
          </div>
        </div>
      )}

      {lipsyncEligible && dialogueEnabled && (
        <div className="flex items-center justify-between gap-3 mb-4 px-4 py-3 rounded-xl" style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)" }}>
          <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: "var(--mf-ink-2)" }}>
            <AudioLines size={16} style={{ color: "var(--mf-violet-soft)" }} />
            <span>
              {tr(t, "form_lipsync_toggle", "Dudak senkronu")}
              <span className="block text-[11px] mt-0.5" style={{ color: "var(--mf-ink-4)" }}>
                {tr(t, "form_lipsync_hint", "Karakterlerin ağzı, üretilen sesle konuşur. Kapalıyken ses görüntünün üstüne bindirilir.")}
              </span>
            </span>
          </label>
          <div className="flex items-center gap-3">
            {lipsyncEnabled && !demoMode && (
              <span className="text-xs" style={{ color: "var(--mf-gold)" }}>
                {tr(t, "form_lipsync_credit_note", `+${numScenes} kredi`, { n: numScenes })}
              </span>
            )}
            <button
              type="button"
              role="switch"
              aria-checked={lipsyncEnabled}
              onClick={() => setLipsyncEnabled((v) => !v)}
              disabled={isSubmitting}
              className="relative inline-flex h-5 w-9 items-center rounded-full transition-colors"
              style={{ backgroundColor: lipsyncEnabled ? "var(--mf-violet)" : "var(--mf-line-strong)" }}
            >
              <span
                className="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
                style={{ transform: lipsyncEnabled ? "translateX(18px)" : "translateX(2px)" }}
              />
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-3 mb-4 px-4 py-3 rounded-xl" style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)" }}>
        <label className="flex items-center gap-2 text-sm cursor-pointer" style={{ color: "var(--mf-ink-2)" }}>
          <Clapperboard size={16} style={{ color: "var(--mf-violet-soft)" }} />
          <span>
            {t("form_script_approval_toggle")}
            <span className="block text-[11px] mt-0.5" style={{ color: "var(--mf-ink-4)" }}>
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
          style={{ backgroundColor: requireScriptApproval ? "var(--mf-violet)" : "var(--mf-line-strong)" }}
        >
          <span
            className="inline-block h-4 w-4 transform rounded-full bg-white transition-transform"
            style={{ transform: requireScriptApproval ? "translateX(18px)" : "translateX(2px)" }}
          />
        </button>
      </div>

      <div className="flex flex-col gap-1.5 mb-4 text-xs" style={{ color: "var(--mf-ink-3)" }}>
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
              style={{ backgroundColor: "rgba(139,92,246,0.15)", color: "var(--mf-violet-soft)" }}
            >
              <FlaskConical size={11} /> {t("form_demo_badge")}
            </span>
          ) : (
            <span
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full"
              style={{ backgroundColor: "rgba(232,182,76,0.12)", color: "var(--mf-gold)" }}
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
          <ul className="sm:self-end space-y-0.5 text-[11px] leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>
            {estimate.breakdown.map((row) => (
              <li key={row.label}>
                {row.label}: {row.credits}
              </li>
            ))}
          </ul>
        )}
        {!demoMode && estimate?.wait_warning_minutes != null && (
          <p className="text-[11px] leading-relaxed" style={{ color: "var(--mf-gold)" }}>
            {t("form_long_job_warning", { minutes: estimate.wait_warning_minutes })}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={!idea.trim() || isSubmitting}
        className="w-full py-4 rounded-xl font-semibold text-base transition-all flex items-center justify-center gap-2"
        style={{
          background: isSubmitting
            ? "var(--mf-violet-deep)"
            : "linear-gradient(135deg, var(--mf-violet) 0%, var(--mf-violet-deep) 100%)",
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
