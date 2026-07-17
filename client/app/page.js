"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import IdeaForm from "../components/IdeaForm";
import LiveCounter from "../components/LiveCounter";
import MiniDemo from "../components/MiniDemo";
import ExitIntent from "../components/ExitIntent";
import StickyCtaButton from "../components/StickyCtaButton";
import {
  Film, Zap, GitBranch, Layers, Sparkles, Users, Camera, Wand2,
  ArrowRight, PlayCircle, Rocket, ShieldCheck, Check, X as XIcon,
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useLanguage } from "../contexts/LanguageContext";
import { friendlyError } from "../utils/errorMessages";

export default function HomePage() {
  const router = useRouter();
  const { getAccessToken } = useAuth();
  const { t } = useLanguage();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [creditsExhausted, setCreditsExhausted] = useState(false);
  const [prefill, setPrefill] = useState(null);
  const formRef = useRef(null);

  const scrollToForm = (data) => {
    setPrefill({ ...data, _ts: Date.now() });
    setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };

  const handleSubmit = async (formData) => {
    setIsSubmitting(true);
    setError(null);
    setCreditsExhausted(false);
    try {
      const token = await getAccessToken();
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(formData),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        if (res.status === 402) {
          setCreditsExhausted(true);
          setError(null);
          setIsSubmitting(false);
          return;
        }
        throw new Error(err.detail || "Failed to start generation");
      }
      const data = await res.json();
      router.push(`/generate/${data.job_id}`);
    } catch (err) {
      setError(friendlyError(err.message));
      setIsSubmitting(false);
    }
  };

  const GENRE_TEMPLATES = [
    {
      key: "scifi",
      label: t("genre_scifi"),
      idea: t("genre_scifi_idea"),
      style: "Sci-Fi",
      directorStyle: "cinematic_balanced",
      gradient: "linear-gradient(135deg, #1e3a8a 0%, #7c3aed 100%)",
    },
    {
      key: "romance",
      label: t("genre_romance"),
      idea: t("genre_romance_idea"),
      style: "Romance",
      directorStyle: "intimate_closeup",
      gradient: "linear-gradient(135deg, #be185d 0%, #7c3aed 100%)",
    },
    {
      key: "thriller",
      label: t("genre_thriller"),
      idea: t("genre_thriller_idea"),
      style: "Noir",
      directorStyle: "noir_mystery",
      gradient: "linear-gradient(135deg, #18181b 0%, #7c3aed 100%)",
    },
    {
      key: "fantasy",
      label: t("genre_fantasy"),
      idea: t("genre_fantasy_idea"),
      style: "Fantasy",
      directorStyle: "cinematic_balanced",
      gradient: "linear-gradient(135deg, #065f46 0%, #7c3aed 100%)",
    },
    {
      key: "action",
      label: t("genre_action"),
      idea: t("genre_action_idea"),
      style: "Cinematic",
      directorStyle: "dynamic_action",
      gradient: "linear-gradient(135deg, #991b1b 0%, #7c3aed 100%)",
    },
    {
      key: "anime",
      label: t("genre_anime"),
      idea: t("genre_anime_idea"),
      style: "Anime",
      directorStyle: "anime_expressive",
      gradient: "linear-gradient(135deg, #9d174d 0%, #7c3aed 100%)",
    },
  ];

  const FEATURES = [
    { icon: Users,    title: t("feat_1_title"), desc: t("feat_1_desc") },
    { icon: Camera,   title: t("feat_2_title"), desc: t("feat_2_desc") },
    { icon: GitBranch, title: t("feat_3_title"), desc: t("feat_3_desc") },
    { icon: Rocket,   title: t("feat_4_title"), desc: t("feat_4_desc") },
  ];

  const HOW_IT_WORKS = [
    { icon: Sparkles,   title: t("how_1_title"), desc: t("how_1_desc") },
    { icon: GitBranch,  title: t("how_2_title"), desc: t("how_2_desc") },
    { icon: Wand2,      title: t("how_3_title"), desc: t("how_3_desc") },
    { icon: PlayCircle, title: t("how_4_title"), desc: t("how_4_desc") },
  ];

  const FAQ = [
    { q: t("faq_1_q"), a: t("faq_1_a") },
    { q: t("faq_2_q"), a: t("faq_2_a") },
    { q: t("faq_3_q"), a: t("faq_3_a") },
    { q: t("faq_4_q"), a: t("faq_4_a") },
  ];

  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <ExitIntent />
      <StickyCtaButton onScrollToForm={() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })} />

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div
            className="absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[450px] rounded-full opacity-20"
            style={{ background: "radial-gradient(ellipse at center, #7c3aed 0%, transparent 70%)", filter: "blur(80px)" }}
          />
        </div>
        <div className="relative max-w-5xl mx-auto px-6 pt-20 pb-12 text-center">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mb-6"
            style={{ backgroundColor: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.3)", color: "#a78bfa" }}
          >
            <Zap size={12} />
            {t("hero_badge")}
          </div>
          <h1 className="text-6xl md:text-8xl font-black tracking-tight mb-5 leading-none">
            <span className="gradient-text">MuseForge</span>
          </h1>
          <p className="text-xl md:text-2xl font-light mb-3" style={{ color: "#94a3b8", letterSpacing: "-0.01em" }}>
            {t("hero_sub")}
          </p>
          <p className="text-base max-w-2xl mx-auto mb-10 leading-relaxed" style={{ color: "#64748b" }}>
            {t("hero_desc")}
          </p>

          <div className="flex flex-wrap justify-center gap-2 mb-8">
            {[
              { icon: <Film size={14} />,      label: t("agent_screenwriter") },
              { icon: <GitBranch size={14} />, label: t("agent_storyboard") },
              { icon: <Layers size={14} />,    label: t("agent_frames") },
              { icon: <Zap size={14} />,       label: t("agent_video") },
            ].map((f) => (
              <div key={f.label} className="flex items-center gap-2 px-4 py-2 rounded-full text-sm"
                style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8" }}>
                <span style={{ color: "#7c3aed" }}>{f.icon}</span>
                {f.label}
              </div>
            ))}
          </div>

          {/* Live counter */}
          <LiveCounter />
        </div>
      </div>

      {/* ── Live Mini Demo ───────────────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-6 pb-16">
        <div className="text-center mb-6">
          <span className="text-xs font-semibold tracking-widest uppercase" style={{ color: "#7c3aed" }}>
            Interactive Preview
          </span>
          <h2 className="text-xl font-bold mt-1" style={{ color: "#e2e8f0" }}>
            See how it works — before you commit
          </h2>
        </div>
        <MiniDemo onTryReal={(idea) => scrollToForm({ idea })} />
      </section>

      {/* ── Genre templates ─────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 pb-16">
        <div className="text-center mb-10">
          <h2 className="text-2xl md:text-3xl font-bold mb-3" style={{ color: "#e2e8f0" }}>
            {t("genres_title")}
          </h2>
          <p className="text-sm max-w-lg mx-auto" style={{ color: "#64748b" }}>
            {t("genres_desc")}
          </p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {GENRE_TEMPLATES.map((g) => (
            <button
              key={g.key}
              type="button"
              onClick={() => scrollToForm({ idea: g.idea, style: g.style, directorStyle: g.directorStyle })}
              className="relative overflow-hidden rounded-2xl p-5 text-left group transition-all duration-300 hover:scale-[1.03] hover:shadow-2xl"
              style={{ background: g.gradient, minHeight: "150px" }}
            >
              {/* Subtle overlay — low opacity so gradient stays vivid */}
              <div
                className="absolute inset-0 transition-opacity duration-300 group-hover:opacity-0"
                style={{ background: "linear-gradient(to bottom, transparent 40%, rgba(10,10,15,0.55) 100%)" }}
              />
              {/* Hover glow ring */}
              <div
                className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                style={{ boxShadow: "inset 0 0 0 2px rgba(167,139,250,0.5)" }}
              />
              <div className="relative">
                <span
                  className="inline-block px-2.5 py-1 rounded-full text-xs font-semibold mb-6"
                  style={{ backgroundColor: "rgba(10,10,15,0.45)", color: "#fff" }}
                >
                  {g.label}
                </span>
                <p className="text-sm leading-snug" style={{ color: "rgba(255,255,255,0.92)" }}>
                  {g.idea}
                </p>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* ── How it works ────────────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-16">
        <h2 className="text-2xl md:text-3xl font-bold text-center mb-12" style={{ color: "#e2e8f0" }}>
          {t("how_title")}
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-8">
          {HOW_IT_WORKS.map((step, i) => (
            <div key={step.title} className="text-center">
              <div
                className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
                style={{ backgroundColor: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.3)" }}
              >
                <step.icon size={20} style={{ color: "#a78bfa" }} />
              </div>
              <p className="text-xs font-mono mb-1" style={{ color: "#4b5563" }}>
                {t("how_step")} {i + 1}
              </p>
              <h3 className="text-sm font-semibold mb-2" style={{ color: "#e2e8f0" }}>{step.title}</h3>
              <p className="text-xs leading-relaxed" style={{ color: "#64748b" }}>{step.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Feature showcase ────────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-20">
        <h2 className="text-2xl md:text-3xl font-bold text-center mb-12" style={{ color: "#e2e8f0" }}>
          {t("feat_title")}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="rounded-2xl p-6 group transition-all duration-300 hover:scale-[1.015]"
              style={{ backgroundColor: "#12121a", border: "1px solid #1a1a26" }}
            >
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center mb-4 transition-colors group-hover:bg-purple-500/20"
                style={{ backgroundColor: "rgba(124,58,237,0.15)" }}
              >
                <f.icon size={18} style={{ color: "#a78bfa" }} />
              </div>
              <h3 className="text-base font-semibold mb-2" style={{ color: "#e2e8f0" }}>{f.title}</h3>
              <p className="text-sm leading-relaxed" style={{ color: "#64748b" }}>{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Director Style Gallery ──────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-20">
        <div className="text-center mb-10">
          <h2 className="text-2xl md:text-3xl font-bold mb-3" style={{ color: "#e2e8f0" }}>
            {t("gallery_title")}
          </h2>
          <p className="text-sm max-w-xl mx-auto" style={{ color: "#64748b" }}>{t("gallery_sub")}</p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {[
            { style: "Slow Cinematic",    mood: "Dreamy & contemplative",  color: "#818cf8" },
            { style: "Noir Mystery",      mood: "Dark & high contrast",    color: "#c084fc" },
            { style: "Handheld Kinetic",  mood: "Gritty verité energy",    color: "#60a5fa" },
            { style: "Dynamic Action",    mood: "Fast cuts, bold movement", color: "#34d399" },
            { style: "Warm Nostalgia",    mood: "Golden tone, soft focus",  color: "#fbbf24" },
          ].map(({ style, mood, color }) => (
            <div key={style}
              className="group relative rounded-2xl overflow-hidden cursor-pointer transition-all duration-300 hover:scale-[1.04]"
              style={{ border: "1px solid #1a1a26", backgroundColor: "#0d0d14", aspectRatio: "9/16" }}
              onClick={() => scrollToForm({ director_style: style.toLowerCase().replace(/\s+/g, "_"), _ts: Date.now() })}
            >
              {/* Gradient placeholder frame */}
              <div className="absolute inset-0"
                style={{ background: `radial-gradient(ellipse at 50% 30%, ${color}30 0%, #0a0a0f 70%)` }} />
              <div className="absolute inset-0 flex flex-col justify-end p-3">
                <span className="text-[10px] px-2 py-0.5 rounded-full mb-2 self-start font-medium"
                  style={{ backgroundColor: `${color}20`, color, border: `1px solid ${color}40` }}>
                  {t("gallery_demo_label")}
                </span>
                <p className="text-xs font-bold leading-tight" style={{ color: "#e2e8f0" }}>{style}</p>
                <p className="text-[10px] mt-0.5" style={{ color: "#64748b" }}>{mood}</p>
              </div>
              <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                <div className="px-3 py-1.5 rounded-full text-xs font-semibold"
                  style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
                  Try this style →
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Comparison Table ────────────────────────────────────────────────── */}
      <section className="max-w-4xl mx-auto px-6 pb-20">
        <div className="text-center mb-10">
          <h2 className="text-2xl md:text-3xl font-bold mb-3" style={{ color: "#e2e8f0" }}>
            {t("compare_title")}
          </h2>
          <p className="text-sm" style={{ color: "#64748b" }}>{t("compare_sub")}</p>
        </div>
        <div className="glass rounded-2xl overflow-hidden" style={{ border: "1px solid rgba(124,58,237,0.15)" }}>
          {/* Header */}
          <div className="grid grid-cols-3 px-6 py-4 border-b" style={{ borderColor: "#1a1a26", backgroundColor: "#0d0d14" }}>
            <p className="text-xs font-semibold" style={{ color: "#64748b" }}>{t("compare_feature")}</p>
            <p className="text-xs font-bold text-center gradient-text">MuseForge</p>
            <p className="text-xs font-semibold text-center" style={{ color: "#475569" }}>{t("compare_generic")}</p>
          </div>
          {[
            { label: t("compare_char_lock") },
            { label: t("compare_pipeline") },
            { label: t("compare_presets") },
            { label: t("compare_credits") },
            { label: t("compare_demo") },
          ].map(({ label }, i) => (
            <div key={i} className="grid grid-cols-3 px-6 py-4 border-b transition-colors hover:bg-white/[0.02]"
              style={{ borderColor: "#1a1a26" }}>
              <p className="text-sm" style={{ color: "#94a3b8" }}>{label}</p>
              <div className="flex justify-center">
                <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full"
                  style={{ backgroundColor: "rgba(34,197,94,0.12)", color: "#22c55e" }}>
                  <Check size={11} /> {t("compare_yes").replace("✓ ", "")}
                </span>
              </div>
              <div className="flex justify-center">
                <span className="text-xs" style={{ color: "#475569" }}>{t("compare_no")}</span>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-center mt-3" style={{ color: "#374151" }}>
          * Comparison based on publicly available feature sets. Individual tools may vary.
        </p>
      </section>

      {/* ── Generation form ─────────────────────────────────────────────── */}
      <div ref={formRef} className="max-w-3xl mx-auto px-6 pb-16 scroll-mt-6">
        <div className="text-center mb-8">
          <h2 className="text-2xl md:text-3xl font-bold mb-2" style={{ color: "#e2e8f0" }}>
            {t("form_title")}
          </h2>
          <p className="text-sm" style={{ color: "#64748b" }}>{t("form_sub")}</p>
        </div>
        {creditsExhausted && (
          <div
            className="mb-6 px-5 py-4 rounded-xl animate-fade-in flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
            style={{ backgroundColor: "rgba(251,191,36,0.08)", border: "1px solid rgba(251,191,36,0.35)" }}
          >
            <div>
              <p className="text-sm font-semibold" style={{ color: "#fbbf24" }}>{t("credits_exhausted_title")}</p>
              <p className="text-xs mt-1" style={{ color: "#94a3b8" }}>{t("credits_exhausted_desc")}</p>
            </div>
            <a
              href="/pricing"
              className="inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-semibold flex-shrink-0"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
            >
              {t("credits_exhausted_cta")}
            </a>
          </div>
        )}
        {error && (
          <div
            className="mb-6 px-4 py-3 rounded-xl text-sm animate-fade-in"
            style={{ backgroundColor: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#fca5a5" }}
          >
            {error}
          </div>
        )}
        <IdeaForm onSubmit={handleSubmit} isSubmitting={isSubmitting} prefill={prefill} />
      </div>

      {/* ── FAQ ──────────────────────────────────────────────────────────── */}
      <section className="max-w-2xl mx-auto px-6 pb-20">
        <h2 className="text-xl font-bold text-center mb-10" style={{ color: "#e2e8f0" }}>
          {t("faq_title")}
        </h2>
        {FAQ.map(({ q, a }) => (
          <div key={q} className="border-b py-5" style={{ borderColor: "#1a1a26" }}>
            <p className="text-sm font-medium mb-2" style={{ color: "#e2e8f0" }}>{q}</p>
            <p className="text-sm leading-relaxed" style={{ color: "#64748b" }}>{a}</p>
          </div>
        ))}
      </section>

      {/* ── CTA ──────────────────────────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-6 pb-24 text-center">
        <div
          className="rounded-2xl p-10 relative overflow-hidden"
          style={{ backgroundColor: "#12121a", border: "1px solid rgba(124,58,237,0.2)" }}
        >
          <div
            className="absolute inset-0 pointer-events-none"
            style={{ background: "radial-gradient(ellipse at center bottom, rgba(124,58,237,0.12) 0%, transparent 70%)" }}
          />
          <div className="relative">
            <ShieldCheck size={32} style={{ color: "#a78bfa" }} className="mx-auto mb-4" />
            <h3 className="text-2xl font-bold mb-3" style={{ color: "#e2e8f0" }}>{t("cta_title")}</h3>
            <p className="text-sm mb-7 max-w-sm mx-auto leading-relaxed" style={{ color: "#64748b" }}>
              {t("cta_desc")}
            </p>
            <button
              type="button"
              onClick={() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
              className="inline-flex items-center gap-2 px-8 py-4 rounded-xl text-base font-semibold transition-all hover:scale-105 active:scale-95"
              style={{ background: "linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)", color: "#fff", boxShadow: "0 0 28px rgba(124,58,237,0.35)" }}
            >
              {t("cta_btn")}
              <ArrowRight size={18} />
            </button>
          </div>
        </div>
      </section>

      <footer className="text-center pb-10 text-sm space-y-3" style={{ color: "#374151" }}>
        <p>MuseForge &mdash; Built on MuAPI generative media infrastructure</p>
        <div className="flex justify-center gap-5 text-xs">
          <a href="/pricing" className="hover:text-purple-400 transition-colors">{t("footer_pricing")}</a>
          <a href="/legal/privacy" className="hover:text-purple-400 transition-colors">{t("footer_privacy")}</a>
          <a href="/legal/terms" className="hover:text-purple-400 transition-colors">{t("footer_terms")}</a>
        </div>
      </footer>
    </main>
  );
}
