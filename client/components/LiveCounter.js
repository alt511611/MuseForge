"use client";

import { useEffect, useState } from "react";
import { useLanguage } from "../contexts/LanguageContext";
import { API_BASE } from "../lib/apiBase";

// Hide the counter until total_completed clears this bar — a tiny number is
// weak social proof. Override via NEXT_PUBLIC_COUNTER_THRESHOLD in .env.
const COUNTER_THRESHOLD = (() => {
  const raw = process.env.NEXT_PUBLIC_COUNTER_THRESHOLD;
  const n = raw !== undefined && raw !== "" ? Number(raw) : 50;
  return Number.isFinite(n) && n >= 0 ? n : 50;
})();

export default function LiveCounter() {
  const { t } = useLanguage();
  const [count, setCount] = useState(null);
  const [displayed, setDisplayed] = useState(0);

  useEffect(() => {
    fetch(`${API_BASE}/api/stats`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d) return;
        // Gate on all-time total; stay fully hidden below the threshold.
        const total = d.total_completed ?? 0;
        if (total < COUNTER_THRESHOLD) return;
        setCount(d.monthly_completed ?? total);
      })
      .catch(() => {});
  }, []);

  // Animated count-up
  useEffect(() => {
    if (count === null) return;
    const target = count;
    const duration = 1200;
    const start = performance.now();
    const tick = (now) => {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayed(Math.round(eased * target));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [count]);

  if (count === null || count === 0) return null;

  return (
    <div className="flex items-center justify-center gap-3 py-4">
      <div
        className="flex items-center gap-2 px-5 py-2.5 rounded-full text-sm font-medium"
        style={{ backgroundColor: "rgba(124,58,237,0.1)", border: "1px solid rgba(124,58,237,0.25)", color: "#a78bfa" }}
      >
        <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse inline-block" />
        <span className="text-xl font-black" style={{ color: "#c4b5fd" }}>
          {displayed.toLocaleString()}+
        </span>
        <span>{t("live_counter_label")}</span>
      </div>
    </div>
  );
}
