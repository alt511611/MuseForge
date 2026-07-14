"use client";

import { useEffect, useState } from "react";
import { Clapperboard } from "lucide-react";
import { useLanguage } from "../contexts/LanguageContext";

export default function StickyCtaButton({ onScrollToForm }) {
  const { t } = useLanguage();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const onScroll = () => setVisible(window.scrollY > 400);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  if (!visible) return null;

  return (
    <button
      onClick={onScrollToForm}
      className="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-5 py-3 rounded-full text-sm font-semibold shadow-2xl transition-all animate-fade-in hover:scale-105 active:scale-95"
      style={{
        background: "linear-gradient(135deg,#7c3aed,#6d28d9)",
        color: "#fff",
        boxShadow: "0 0 24px rgba(124,58,237,0.4)",
      }}
      aria-label="Try Now"
    >
      <Clapperboard size={16} />
      {t("cta_btn")}
    </button>
  );
}
