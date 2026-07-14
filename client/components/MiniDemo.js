"use client";

import { useState, useEffect } from "react";
import { Sparkles, Loader2, CheckCircle2, Pen, Layout, Image as ImageIcon } from "lucide-react";
import { useLanguage } from "../contexts/LanguageContext";

const MOCK_STAGES = [
  { icon: Pen,        label: "Writing screenplay...",  ms: 900 },
  { icon: Layout,     label: "Designing storyboard...", ms: 1100 },
  { icon: ImageIcon,  label: "Generating frames...",    ms: 1300 },
  { icon: CheckCircle2, label: "Done!",                 ms: 0 },
];

const MOCK_CARDS = [
  { scene: "Scene 1", desc: "Opening shot — establishing the world.", color: "#1e3a8a" },
  { scene: "Scene 2", desc: "Rising action — the conflict ignites.",  color: "#7c3aed" },
  { scene: "Scene 3", desc: "Climax — the turning point arrives.",    color: "#be185d" },
];

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
    <div
      className="rounded-2xl p-6 max-w-2xl mx-auto"
      style={{ backgroundColor: "#12121a", border: "1px solid rgba(124,58,237,0.25)" }}
    >
      <div className="flex items-center gap-2 mb-4">
        <Sparkles size={16} style={{ color: "#a78bfa" }} />
        <span className="text-sm font-semibold" style={{ color: "#e2e8f0" }}>
          Live Preview — no account needed
        </span>
        <span
          className="ml-auto text-xs px-2 py-0.5 rounded-full"
          style={{ backgroundColor: "rgba(124,58,237,0.15)", color: "#a78bfa" }}
        >
          Mock
        </span>
      </div>

      {phase === "idle" && (
        <div className="flex gap-2">
          <input
            type="text"
            value={idea}
            onChange={(e) => setIdea(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
            placeholder="Type any idea and see the pipeline in action..."
            className="flex-1 px-4 py-2.5 rounded-xl text-sm focus:outline-none"
            style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a", color: "#e2e8f0" }}
          />
          <button
            onClick={run}
            disabled={!idea.trim()}
            className="px-4 py-2.5 rounded-xl text-sm font-semibold transition-all"
            style={{
              background: idea.trim() ? "linear-gradient(135deg,#7c3aed,#6d28d9)" : "#1a1a26",
              color: idea.trim() ? "#fff" : "#4b5563",
              cursor: idea.trim() ? "pointer" : "not-allowed",
            }}
          >
            Preview
          </button>
        </div>
      )}

      {phase === "running" && (
        <div className="space-y-2">
          {MOCK_STAGES.slice(0, stageIdx + 1).map((s, i) => {
            const done = i < stageIdx;
            return (
              <div key={i} className="flex items-center gap-3 text-sm animate-fade-in">
                {done
                  ? <CheckCircle2 size={16} style={{ color: "#4ade80" }} />
                  : <Loader2 size={16} className="animate-spin" style={{ color: "#a78bfa" }} />}
                <span style={{ color: done ? "#4ade80" : "#e2e8f0" }}>{s.label}</span>
              </div>
            );
          })}
        </div>
      )}

      {phase === "done" && (
        <div className="animate-fade-in">
          <p className="text-xs mb-3" style={{ color: "#64748b" }}>
            Mock storyboard for: <span style={{ color: "#a78bfa" }}>"{idea}"</span>
          </p>
          <div className="grid grid-cols-3 gap-2 mb-4">
            {MOCK_CARDS.map((c) => (
              <div
                key={c.scene}
                className="rounded-xl p-3 text-xs"
                style={{
                  background: `linear-gradient(135deg, ${c.color}55 0%, #12121a 100%)`,
                  border: `1px solid ${c.color}66`,
                }}
              >
                <p className="font-semibold mb-1" style={{ color: "#e2e8f0" }}>{c.scene}</p>
                <p style={{ color: "#94a3b8" }}>{c.desc}</p>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => onTryReal && onTryReal(idea)}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
            >
              {t("form_generate")} →
            </button>
            <button
              onClick={reset}
              className="px-4 py-2.5 rounded-xl text-sm transition-all"
              style={{ backgroundColor: "#1a1a26", border: "1px solid #22223a", color: "#64748b" }}
            >
              Reset
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
