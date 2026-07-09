"use client";

import { useState, useEffect } from "react";
import { Sparkles, Loader2, Upload } from "lucide-react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

const STYLES = [
  { value: "Cinematic", label: "Cinematic", desc: "Epic film quality" },
  { value: "Realistic", label: "Realistic", desc: "True-to-life" },
  { value: "Anime", label: "Anime", desc: "Japanese animation" },
  { value: "Fantasy", label: "Fantasy", desc: "Magical & fantastical" },
  { value: "Documentary", label: "Documentary", desc: "Journalistic style" },
];

const MODES = [
  {
    value: "idea2video",
    label: "Idea to Video",
    desc: "Full agentic pipeline: story, scenes, storyboard, video",
  },
  {
    value: "script2video",
    label: "Script to Video",
    desc: "Start from your own scene script",
  },
];

const FALLBACK_DIRECTOR_STYLES = [
  { key: "cinematic_balanced", label: "Cinematic", description: "Balanced dramatic coverage" },
  { key: "slow_cinematic", label: "Slow Cinematic", description: "Deliberate pushes, negative space" },
  { key: "handheld_kinetic", label: "Handheld Kinetic", description: "Raw, urgent, documentary energy" },
  { key: "static_wide", label: "Static Wide", description: "Locked-off, observational" },
  { key: "dynamic_action", label: "Dynamic Action", description: "Fast tracking, dramatic angles" },
];

const MAX_UPLOAD_BYTES = 5 * 1024 * 1024; // 5MB

export default function IdeaForm({ onSubmit, isSubmitting }) {
  const [idea, setIdea] = useState("");
  const [userRequirement, setUserRequirement] = useState("");
  const [style, setStyle] = useState("Cinematic");
  const [mode, setMode] = useState("idea2video");
  const [script, setScript] = useState("");
  const [directorStyle, setDirectorStyle] = useState("cinematic_balanced");
  const [directorStyles, setDirectorStyles] = useState(FALLBACK_DIRECTOR_STYLES);
  const [characterImage, setCharacterImage] = useState(null);
  const [characterName, setCharacterName] = useState("");
  const [uploadError, setUploadError] = useState(null);

  useEffect(() => {
    fetch(`${API_URL}/api/director-styles`)
      .then((res) => res.json())
      .then((data) => {
        if (data.styles && data.styles.length > 0) {
          setDirectorStyles(data.styles);
          setDirectorStyle(data.styles[0].key);
        }
      })
      .catch(() => {});
  }, []);

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    setUploadError(null);
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      setUploadError("Image must be smaller than 5MB.");
      e.target.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = (event) => {
      setCharacterImage(event.target.result);
    };
    reader.readAsDataURL(file);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!idea.trim() && (mode !== "script2video" || !script.trim())) return;
    onSubmit({
      idea: idea.trim(),
      user_requirement: userRequirement.trim(),
      style,
      mode,
      script: script.trim(),
      director_style: directorStyle,
      character_image: characterImage,
      character_name: characterImage ? characterName.trim() : "",
    });
  };

  const inputStyle = {
    backgroundColor: "#12121a",
    border: "1px solid #22223a",
    borderRadius: "12px",
    color: "#e2e8f0",
    padding: "12px 16px",
    width: "100%",
    fontSize: "14px",
    transition: "border-color 0.2s",
    outline: "none",
    resize: "vertical",
  };

  const labelStyle = {
    display: "block",
    fontSize: "13px",
    fontWeight: "500",
    marginBottom: "8px",
    color: "#94a3b8",
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-2xl p-6 space-y-6"
      style={{
        backgroundColor: "#12121a",
        border: "1px solid #1a1a26",
      }}
    >
      <div>
        <label style={labelStyle}>Generation Mode</label>
        <div className="grid grid-cols-2 gap-3">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => setMode(m.value)}
              className="text-left p-4 rounded-xl transition-all"
              style={{
                backgroundColor: mode === m.value ? "rgba(124, 58, 237, 0.15)" : "#1a1a26",
                border: mode === m.value
                  ? "1px solid rgba(124, 58, 237, 0.5)"
                  : "1px solid #22223a",
                cursor: "pointer",
              }}
            >
              <div
                className="text-sm font-semibold mb-1"
                style={{ color: mode === m.value ? "#a78bfa" : "#e2e8f0" }}
              >
                {m.label}
              </div>
              <div className="text-xs" style={{ color: "#6b7280" }}>
                {m.desc}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div>
        <label style={labelStyle}>
          {mode === "script2video" ? "Brief idea or title" : "Your Idea *"}
        </label>
        <textarea
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder={
            mode === "idea2video"
              ? "e.g. A lone astronaut discovers an ancient alien structure on Mars..."
              : "Brief title or concept for your video"
          }
          rows={3}
          required={mode === "idea2video"}
          style={inputStyle}
          onFocus={(e) => (e.target.style.borderColor = "#7c3aed")}
          onBlur={(e) => (e.target.style.borderColor = "#22223a")}
        />
      </div>

      {mode === "script2video" && (
        <div>
          <label style={labelStyle}>Scene Script *</label>
          <textarea
            value={script}
            onChange={(e) => setScript(e.target.value)}
            placeholder="Write your scene script here..."
            rows={6}
            required
            style={inputStyle}
            onFocus={(e) => (e.target.style.borderColor = "#7c3aed")}
            onBlur={(e) => (e.target.style.borderColor = "#22223a")}
          />
        </div>
      )}

      <div>
        <label style={labelStyle}>Visual Style</label>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {STYLES.map((s) => (
            <button
              key={s.value}
              type="button"
              onClick={() => setStyle(s.value)}
              className="p-3 rounded-xl text-center transition-all"
              style={{
                backgroundColor: style === s.value ? "rgba(124, 58, 237, 0.15)" : "#1a1a26",
                border: style === s.value
                  ? "1px solid rgba(124, 58, 237, 0.5)"
                  : "1px solid #22223a",
                cursor: "pointer",
              }}
            >
              <div
                className="text-xs font-semibold mb-1"
                style={{ color: style === s.value ? "#a78bfa" : "#e2e8f0" }}
              >
                {s.label}
              </div>
              <div className="text-xs" style={{ color: "#4b5563", fontSize: "10px" }}>
                {s.desc}
              </div>
            </button>
          ))}
        </div>
      </div>

      {directorStyles.length > 0 && (
        <div>
          <label style={labelStyle}>Cinema Studio — Director Style</label>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {directorStyles.map((d) => (
              <button
                key={d.key}
                type="button"
                onClick={() => setDirectorStyle(d.key)}
                title={d.description}
                className="p-3 rounded-xl text-center transition-all"
                style={{
                  backgroundColor: directorStyle === d.key ? "rgba(124, 58, 237, 0.15)" : "#1a1a26",
                  border: directorStyle === d.key
                    ? "1px solid rgba(124, 58, 237, 0.5)"
                    : "1px solid #22223a",
                  cursor: "pointer",
                }}
              >
                <div
                  className="text-xs font-semibold mb-1"
                  style={{ color: directorStyle === d.key ? "#a78bfa" : "#e2e8f0" }}
                >
                  {d.label}
                </div>
                <div className="text-xs" style={{ color: "#4b5563", fontSize: "10px" }}>
                  {d.description.slice(0, 20)}...
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <label style={labelStyle}>
          Upload Character Photo (optional)
          <span style={{ color: "#4b5563", fontWeight: 400, marginLeft: "8px" }}>
            — for consistency
          </span>
        </label>
        <div className="flex items-center gap-4">
          <input
            type="file"
            accept="image/*"
            onChange={handleFileUpload}
            className="hidden"
            id="char-upload"
          />
          <label
            htmlFor="char-upload"
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm cursor-pointer transition-all"
            style={{
              backgroundColor: "#1a1a26",
              border: "1px solid #22223a",
              color: "#94a3b8",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#7c3aed")}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = "#22223a")}
          >
            <Upload size={14} />
            Choose file
          </label>
          {characterImage && (
            <div className="flex items-center gap-2">
              <img
                src={characterImage}
                alt="Character"
                className="w-10 h-10 rounded-full object-cover border border-purple-500"
              />
              <input
                type="text"
                value={characterName}
                onChange={(e) => setCharacterName(e.target.value)}
                placeholder="Character name (required)"
                className="text-sm bg-transparent border-b border-gray-600 focus:border-purple-500 outline-none"
                style={{ color: "#e2e8f0" }}
              />
            </div>
          )}
        </div>
        {uploadError && (
          <p className="text-xs mt-2" style={{ color: "#fca5a5" }}>{uploadError}</p>
        )}
        {characterImage && !characterName.trim() && (
          <p className="text-xs mt-2" style={{ color: "#fde047" }}>
            Enter the character's name so the script can match it to this photo.
          </p>
        )}
      </div>

      <div>
        <label style={labelStyle}>
          Additional Requirements{" "}
          <span style={{ color: "#4b5563", fontWeight: 400 }}>(optional)</span>
        </label>
        <textarea
          value={userRequirement}
          onChange={(e) => setUserRequirement(e.target.value)}
          placeholder="Any specific instructions, mood, pacing, color palette..."
          rows={2}
          style={inputStyle}
          onFocus={(e) => (e.target.style.borderColor = "#7c3aed")}
          onBlur={(e) => (e.target.style.borderColor = "#22223a")}
        />
      </div>

      <button
        type="submit"
        disabled={isSubmitting || (!idea.trim() && (mode !== "script2video" || !script.trim()))}
        className="w-full py-4 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 transition-all"
        style={{
          background: isSubmitting
            ? "#3b3b5c"
            : "linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)",
          color: isSubmitting ? "#6b7280" : "white",
          cursor: isSubmitting ? "not-allowed" : "pointer",
          boxShadow: isSubmitting ? "none" : "0 4px 20px rgba(124, 58, 237, 0.4)",
        }}
      >
        {isSubmitting ? (
          <>
            <Loader2 size={16} className="animate-spin" />
            Starting pipeline...
          </>
        ) : (
          <>
            <Sparkles size={16} />
            Generate Video
          </>
        )}
      </button>
    </form>
  );
}
