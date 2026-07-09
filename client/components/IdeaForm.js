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
} from "lucide-react";

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

export default function IdeaForm({ onSubmit, isSubmitting }) {
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

  useEffect(() => {
    setCharCount(idea.length);
  }, [idea]);

  useEffect(() => {
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && setDemoMode(!!d.demo_mode))
      .catch(() => {});
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/estimate", {
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
          Your Idea
        </label>
        <textarea
          id="idea"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="A lone astronaut discovers a garden growing inside a derelict space station..."
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
          <span>Describe your micro-drama in 1-3 sentences</span>
          <span>{charCount}/2000</span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <div>
          <label className="text-sm font-medium mb-2 block" style={{ color: "#94a3b8" }}>
            Visual Style
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
            Director Preset
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
          Aspect Ratio
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
        Advanced Options
      </button>

      {showAdvanced && (
        <div className="mb-6 space-y-4 animate-fade-in">
          <div>
            <label className="text-sm font-medium mb-2 block" style={{ color: "#94a3b8" }}>
              Number of Scenes ({numScenes})
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
              Additional Requirements
            </label>
            <input
              type="text"
              value={userRequirement}
              onChange={(e) => setUserRequirement(e.target.value)}
              placeholder="e.g. rainy atmosphere, no dialogue, warm color palette"
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

      <div className="flex items-center justify-between mb-4 text-xs" style={{ color: "#64748b" }}>
        <span className="inline-flex items-center gap-1.5">
          <Clock size={13} />
          {estimate
            ? `Est. render ${estimate.estimated_label} · ${estimate.asset_count.frames} frames · ${estimate.asset_count.clips} clips`
            : "Estimating render time..."}
        </span>
        {demoMode && (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full"
            style={{ backgroundColor: "rgba(124,58,237,0.15)", color: "#a78bfa" }}
          >
            <FlaskConical size={11} /> Demo mode — no API key needed
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
            Starting Pipeline...
          </>
        ) : (
          <>
            <Clapperboard size={20} />
            Generate Cinematic Video
          </>
        )}
      </button>
    </form>
  );
}
