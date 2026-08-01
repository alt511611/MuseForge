"use client";

import { useState } from "react";
import { Sparkles, Loader2, CheckCircle2, Pen, Layout, Image as ImageIcon } from "lucide-react";
import { useLanguage } from "../contexts/LanguageContext";

const MOCK_STAGES = [
  { icon: Pen,          label: "Writing screenplay...",   ms: 900 },
  { icon: Layout,       label: "Designing storyboard...", ms: 1100 },
  { icon: ImageIcon,    label: "Generating frames...",    ms: 1300 },
  { icon: CheckCircle2, label: "Done!",                   ms: 0 },
];

function buildMockScenes(idea) {
  const topic = idea.trim().split(/\s+/).slice(0, 4).join(" ") || "your story";
  return [
    { scene: "Scene 1", tc: "00:00", desc: `Opening shot: we meet the world of "${topic}".`, color: "#3b5bdb" },
    { scene: "Scene 2", tc: "00:08", desc: `Rising action: tension builds around "${topic}".`, color: "#8b5cf6" },
    { scene: "Scene 3", tc: "00:16", desc: `Climax: "${topic}" reaches its turning point.`, color: "#be185d" },
  ];
}

export default function MiniDemo({ onTryReal }) {
  const { t } = useLanguage();
  const [idea, setIdea] = useState("");
  const [phase, setPhase] = useState("idle"); // idle | running | done
  const [stageIdx, setStageIdx] = useState(0);

  const run = () => {
    if (!idea.trim() || phase !== "idle") return;
    setPhase("running");
    setStageIdx(0);

    let idx = 0;
    const next = () => {
      if (idx >= MOCK_STAGES.length - 1) {
        setPhase("done");
        return;
      }
      idx++;
      setStageIdx(idx);
      setTimeout(next, MOCK_STAGES[idx].ms);
    };
    setTimeout(next, MOCK_STAGES[0].ms);
  };

  const reset = () => { setPhase("idle"); setStageIdx(0); setIdea(""); };

  return (
    <div className="mf-card p-6 max-w-2xl mx-auto" style={{ borderColor: "rgba(139,92,246,0.28)" }}>
      {/* Slate header — reads like a take marker on set */}
      <div className="flex items-center gap-2 mb-5 pb-4" style={{ borderBottom: "1px solid var(--mf-line)" }}>
        <Sparkles size={15} style={{ color: "var(--mf-violet-soft)" }} />
        <span className="text-sm font-semibold" style={{ color: "var(--mf-ink)" }}>
          Live preview — no account needed
        </span>
        <span
          className="slate-label ml-auto px-2 py-0.5 rounded-full"
          style={{ fontSize: "9px", backgroundColor: "rgba(232,182,76,0.12)", color: "var(--mf-gold)" }}
        >
          Mock
        </span>
      </div>

      {phase === "idle" && (
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="text"
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
            placeholder="Type any idea and see the pipeline in action..."
            className="flex-1 px-4 py-3 rounded-xl text-sm focus:outline-none transition-colors"
            style={{ backgroundColor: "var(--mf-stage)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink)" }}
            onFocus={(e) => (e.target.style.borderColor = "var(--mf-violet)")}
            onBlur={(e) => (e.target.style.borderColor = "var(--mf-line-strong)")}
          />
          <button
            onClick={run}
            disabled={!idea.trim()}
            className={idea.trim() ? "mf-btn-primary px-5 py-3 rounded-xl text-sm font-semibold" : "px-5 py-3 rounded-xl text-sm font-semibold"}
            style={
              idea.trim()
                ? undefined
                : { backgroundColor: "var(--mf-panel-2)", color: "var(--mf-ink-4)", cursor: "not-allowed", border: "1px solid var(--mf-line)" }
            }
          >
            Preview
          </button>
        </div>
      )}

      {phase === "running" && (
        <div className="space-y-2.5">
          {MOCK_STAGES.slice(0, stageIdx + 1).map((s, i) => {
            const done = i < stageIdx;
            return (
              <div key={i} className="flex items-center gap-3 text-sm animate-fade-in">
                {done
                  ? <CheckCircle2 size={16} style={{ color: "var(--mf-ok)" }} />
                  : <Loader2 size={16} className="animate-spin" style={{ color: "var(--mf-violet-soft)" }} />}
                <span style={{ color: done ? "var(--mf-ok)" : "var(--mf-ink)" }}>{s.label}</span>
                <span className="slate-label ml-auto" style={{ fontSize: "9px" }}>
                  {String(i + 1).padStart(2, "0")}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {phase === "done" && (
        <div className="animate-fade-in">
          <p className="text-xs mb-3" style={{ color: "var(--mf-ink-3)" }}>
            Mock storyboard for: <span style={{ color: "var(--mf-violet-soft)" }}>&quot;{idea}&quot;</span>
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 mb-5">
            {buildMockScenes(idea).map((c) => (
              <div
                key={c.scene}
                className="relative rounded-xl overflow-hidden p-3 text-xs film-grain"
                style={{
                  background: `linear-gradient(160deg, ${c.color}4d 0%, var(--mf-panel) 100%)`,
                  border: `1px solid ${c.color}59`,
                }}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <p className="font-semibold" style={{ color: "var(--mf-ink)" }}>{c.scene}</p>
                  <span className="slate-label" style={{ fontSize: "9px" }}>{c.tc}</span>
                </div>
                <p style={{ color: "var(--mf-ink-2)" }}>{c.desc}</p>
              </div>
            ))}
          </div>
          <div className="flex flex-col sm:flex-row gap-2">
            <button
              onClick={() => onTryReal && onTryReal(idea)}
              className="mf-btn-primary flex-1 py-3 rounded-xl text-sm font-semibold"
            >
              {t("form_generate")} →
            </button>
            <button onClick={reset} className="mf-btn-ghost px-5 py-3 rounded-xl text-sm">
              Reset
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
