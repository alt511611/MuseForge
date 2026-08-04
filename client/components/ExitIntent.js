"use client";

import { useEffect, useState } from "react";
import { X, Sparkles } from "lucide-react";
import Link from "./LocaleLink";

const SESSION_KEY = "mf_exit_intent_shown";

export default function ExitIntent() {
  const [visible, setVisible] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    if (typeof sessionStorage !== "undefined" && sessionStorage.getItem(SESSION_KEY)) return;

    let triggered = false;
    const handler = (e) => {
      if (triggered) return;
      if (e.clientY <= 0) {
        triggered = true;
        setVisible(true);
        sessionStorage.setItem(SESSION_KEY, "1");
      }
    };

    // Only on desktop (touch devices have no mouseleave)
    if (!("ontouchstart" in window)) {
      document.addEventListener("mouseleave", handler);
    }
    return () => document.removeEventListener("mouseleave", handler);
  }, []);

  if (!mounted || !visible) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) setVisible(false); }}
    >
      <div
        className="relative max-w-sm w-full rounded-2xl p-7 animate-fade-in text-center"
        style={{ backgroundColor: "var(--mf-panel)", border: "1px solid rgba(139,92,246,0.4)" }}
      >
        <button
          onClick={() => setVisible(false)}
          className="absolute top-3 right-3 p-1.5 rounded-lg transition-colors hover:bg-white/5"
          style={{ color: "var(--mf-ink-4)" }}
          aria-label="Close"
        >
          <X size={16} />
        </button>

        <div
          className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
          style={{ backgroundColor: "rgba(139,92,246,0.15)", border: "1px solid rgba(139,92,246,0.3)" }}
        >
          <Sparkles size={22} style={{ color: "var(--mf-violet-soft)" }} />
        </div>

        <h3 className="text-lg font-bold mb-2" style={{ color: "var(--mf-ink)" }}>
          Wait — try it free first! ✨
        </h3>
        <p className="text-sm mb-5" style={{ color: "var(--mf-ink-2)" }}>
          No API key needed. See how MuseForge turns a single sentence into a
          cinematic video with demo mode.
        </p>

        <div className="flex flex-col gap-2">
          <Link
            href="/"
            onClick={() => setVisible(false)}
            className="block w-full py-3 rounded-xl text-sm font-semibold transition-all text-center"
            style={{ background: "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))", color: "#fff" }}
          >
            Try Demo Mode Free →
          </Link>
          <button
            onClick={() => setVisible(false)}
            className="text-xs py-2"
            style={{ color: "var(--mf-ink-4)" }}
          >
            No thanks, I'll pass
          </button>
        </div>
      </div>
    </div>
  );
}
