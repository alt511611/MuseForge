"use client";

import Link from "../../components/LocaleLink";
import { Film, ArrowLeft } from "lucide-react";
import { useLanguage } from "../../contexts/LanguageContext";

export default function NotFound() {
  const { t } = useLanguage();

  return (
    <main className="min-h-screen flex items-center justify-center px-6" style={{ backgroundColor: "var(--mf-stage)" }}>
      <div className="text-center max-w-md">
        <div className="text-[120px] font-black leading-none mb-4 gradient-text select-none" aria-hidden="true">
          404
        </div>

        <h1 className="text-2xl font-bold mb-3" style={{ color: "var(--mf-ink)" }}>
          {t("notfound_title")}
        </h1>
        <p className="text-sm mb-8" style={{ color: "var(--mf-ink-3)" }}>
          {t("notfound_desc")}
        </p>

        <div className="flex flex-col sm:flex-row justify-center gap-3">
          <Link
            href="/"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold transition-all"
            style={{ background: "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))", color: "#fff" }}
          >
            <Film size={16} />
            {t("notfound_back")}
          </Link>
          <Link
            href="/pricing"
            className="inline-flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-medium transition-all"
            style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)", color: "var(--mf-ink-2)" }}
          >
            <ArrowLeft size={14} />
            {t("notfound_pricing")}
          </Link>
        </div>
      </div>
    </main>
  );
}
