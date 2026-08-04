"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "../../components/LocaleLink";
import IdeaForm from "../../components/IdeaForm";
import { API_BASE } from "../../lib/apiBase";
import MiniDemo from "../../components/MiniDemo";
import ExitIntent from "../../components/ExitIntent";
import StickyCtaButton from "../../components/StickyCtaButton";
import {
  Film, Zap, GitBranch, Layers, Sparkles, Users, Camera, Wand2,
  ArrowRight, PlayCircle, Rocket, ShieldCheck, Check, Plus,
} from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { useLanguage } from "../../contexts/LanguageContext";
import { friendlyError } from "../../utils/errorMessages";

/* Example videos shown under the hero. Drop your own files in
   `client/public/examples/` and set `src` (plus an optional `poster` image);
   a slot with no `src` stays an empty graded frame rather than showing a
   stand-in that pretends to be real output. */
const SHOWCASE = [
  {
    label: "",
    src: null,   // e.g. "/examples/example-1.mp4"
    poster: null, // e.g. "/examples/example-1.jpg"
    tone: "linear-gradient(160deg,#2a2140 0%,#6d28d9 60%,#07070b 100%)",
  },
  {
    label: "",
    src: null,
    poster: null,
    tone: "linear-gradient(160deg,#1e3a8a 0%,#8b5cf6 60%,#07070b 100%)",
  },
  {
    label: "",
    src: null,
    poster: null,
    tone: "linear-gradient(160deg,#7c2d12 0%,#e8b64c 60%,#07070b 100%)",
  },
];

/* A section eyebrow styled like a film slate: "02 / GENRES". Numbering the
   sections gives the long page a sense of running order. */
function Slate({ n, children }) {
  return (
    <p className="slate-label flex items-center justify-center gap-2.5">
      <span style={{ color: "var(--mf-gold)" }}>{String(n).padStart(2, "0")}</span>
      <span style={{ color: "var(--mf-ink-4)" }}>/</span>
      <span>{children}</span>
    </p>
  );
}

function SectionHead({ n, eyebrow, title, sub }) {
  return (
    <div className="text-center mb-10">
      <Slate n={n}>{eyebrow}</Slate>
      <h2 className="display text-3xl md:text-4xl mt-3" style={{ color: "var(--mf-ink)" }}>
        {title}
      </h2>
      {sub && (
        <p className="text-sm max-w-xl mx-auto mt-3 leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>
          {sub}
        </p>
      )}
    </div>
  );
}

export default function HomeContent() {
  const router = useRouter();
  const { getAccessToken } = useAuth();
  const { t, localeHref } = useLanguage();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [creditsExhausted, setCreditsExhausted] = useState(false);
  const [prefill, setPrefill] = useState(null);
  const formRef = useRef(null);

  const scrollToForm = (data) => {
    setPrefill({ ...data, _ts: Date.now() });
    setTimeout(() => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };

  const jumpToForm = () => formRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });

  const handleSubmit = async (formData) => {
    setIsSubmitting(true);
    setError(null);
    setCreditsExhausted(false);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/generate`, {
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
      router.push(localeHref(`/generate/${data.job_id}`));
    } catch (err) {
      setError(friendlyError(err.message));
      setIsSubmitting(false);
    }
  };

  const PIPELINE = [
    { icon: Film,      label: t("agent_screenwriter") },
    { icon: GitBranch, label: t("agent_storyboard") },
    { icon: Layers,    label: t("agent_frames") },
    { icon: Zap,       label: t("agent_video") },
  ];

  const GENRE_TEMPLATES = [
    {
      key: "scifi",
      label: t("genre_scifi"),
      idea: t("genre_scifi_idea"),
      style: "Sci-Fi",
      directorStyle: "cinematic_balanced",
      grade: "linear-gradient(150deg, #1e3a8a 0%, #4c1d95 55%, #0a0a0f 100%)",
      key_light: "#60a5fa",
    },
    {
      key: "romance",
      label: t("genre_romance"),
      idea: t("genre_romance_idea"),
      style: "Romance",
      directorStyle: "intimate_closeup",
      grade: "linear-gradient(150deg, #be185d 0%, #7c3aed 55%, #0a0a0f 100%)",
      key_light: "#f472b6",
    },
    {
      key: "thriller",
      label: t("genre_thriller"),
      idea: t("genre_thriller_idea"),
      style: "Noir",
      directorStyle: "noir_mystery",
      grade: "linear-gradient(150deg, #27272a 0%, #4c1d95 60%, #0a0a0f 100%)",
      key_light: "#c084fc",
    },
    {
      key: "fantasy",
      label: t("genre_fantasy"),
      idea: t("genre_fantasy_idea"),
      style: "Fantasy",
      directorStyle: "cinematic_balanced",
      grade: "linear-gradient(150deg, #065f46 0%, #5b21b6 60%, #0a0a0f 100%)",
      key_light: "#34d399",
    },
    {
      key: "action",
      label: t("genre_action"),
      idea: t("genre_action_idea"),
      style: "Cinematic",
      directorStyle: "dynamic_action",
      grade: "linear-gradient(150deg, #991b1b 0%, #6d28d9 60%, #0a0a0f 100%)",
      key_light: "#fb923c",
    },
    {
      key: "anime",
      label: t("genre_anime"),
      idea: t("genre_anime_idea"),
      style: "Anime",
      directorStyle: "anime_expressive",
      grade: "linear-gradient(150deg, #9d174d 0%, #6366f1 60%, #0a0a0f 100%)",
      key_light: "#f9a8d4",
    },
  ];

  const FEATURES = [
    { icon: Users,     title: t("feat_1_title"), desc: t("feat_1_desc") },
    { icon: Camera,    title: t("feat_2_title"), desc: t("feat_2_desc") },
    { icon: GitBranch, title: t("feat_3_title"), desc: t("feat_3_desc") },
    { icon: Rocket,    title: t("feat_4_title"), desc: t("feat_4_desc") },
  ];

  const HOW_IT_WORKS = [
    { icon: Sparkles,   title: t("how_1_title"), desc: t("how_1_desc") },
    { icon: GitBranch,  title: t("how_2_title"), desc: t("how_2_desc") },
    { icon: Wand2,      title: t("how_3_title"), desc: t("how_3_desc") },
    { icon: PlayCircle, title: t("how_4_title"), desc: t("how_4_desc") },
  ];

  const DIRECTOR_STYLES = [
    { style: "Slow Cinematic",   mood: "Dreamy & contemplative",   color: "#818cf8" },
    { style: "Noir Mystery",     mood: "Dark & high contrast",     color: "#c084fc" },
    { style: "Handheld Kinetic", mood: "Gritty verité energy",     color: "#60a5fa" },
    { style: "Dynamic Action",   mood: "Fast cuts, bold movement", color: "#34d399" },
    { style: "Warm Nostalgia",   mood: "Golden tone, soft focus",  color: "#e8b64c" },
  ];

  const FAQ = [
    { q: t("faq_1_q"), a: t("faq_1_a") },
    { q: t("faq_2_q"), a: t("faq_2_a") },
    { q: t("faq_3_q"), a: t("faq_3_a") },
    { q: t("faq_4_q"), a: t("faq_4_a") },
  ];

  return (
    <main className="min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
      <ExitIntent />
      <StickyCtaButton onScrollToForm={jumpToForm} />

      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <section className="relative overflow-hidden film-grain">
        {/* Stage lighting */}
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div
            className="absolute -top-40 left-1/2 -translate-x-1/2 w-[1100px] h-[620px] rounded-full"
            style={{ background: "radial-gradient(ellipse at center, rgba(139,92,246,0.30) 0%, transparent 68%)", filter: "blur(90px)" }}
          />
          <div
            className="absolute top-40 right-[8%] w-[420px] h-[420px] rounded-full"
            style={{ background: "radial-gradient(circle, rgba(232,182,76,0.10) 0%, transparent 70%)", filter: "blur(80px)" }}
          />
          {/* Faint production grid */}
          <div
            className="absolute inset-0 opacity-[0.35]"
            style={{
              backgroundImage:
                "linear-gradient(var(--mf-line) 1px, transparent 1px), linear-gradient(90deg, var(--mf-line) 1px, transparent 1px)",
              backgroundSize: "72px 72px",
              maskImage: "radial-gradient(ellipse at 50% 0%, #000 0%, transparent 70%)",
              WebkitMaskImage: "radial-gradient(ellipse at 50% 0%, #000 0%, transparent 70%)",
            }}
          />
        </div>

        <div className="relative max-w-6xl mx-auto px-6 pt-16 md:pt-24 pb-14">
          <div className="max-w-3xl mx-auto text-center animate-rise">
            <div
              className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium mb-7"
              style={{
                backgroundColor: "rgba(139,92,246,0.12)",
                border: "1px solid rgba(139,92,246,0.32)",
                color: "var(--mf-violet-soft)",
              }}
            >
              <Zap size={12} />
              {t("hero_badge")}
            </div>

            <h1 className="display text-display-sm md:text-display-md lg:text-display-lg mb-6" style={{ color: "var(--mf-ink)" }}>
              {t("hero_sub")}
            </h1>

            <p className="text-base md:text-lg max-w-2xl mx-auto mb-9 leading-relaxed" style={{ color: "var(--mf-ink-2)" }}>
              {t("hero_desc")}
            </p>

            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 mb-10">
              <button
                type="button"
                onClick={jumpToForm}
                className="mf-btn-primary inline-flex items-center gap-2 px-7 py-3.5 rounded-xl text-base font-semibold w-full sm:w-auto justify-center"
              >
                {t("cta_btn")}
                <ArrowRight size={17} />
              </button>
              <Link
                href="/pricing"
                className="mf-btn-ghost inline-flex items-center gap-2 px-7 py-3.5 rounded-xl text-base font-medium w-full sm:w-auto justify-center"
              >
                {t("nav_pricing")}
              </Link>
            </div>
          </div>

          {/* ── Showcase: three slots for real example videos. ─────────────
                 Fill in `src` (and optionally `poster`) in SHOWCASE above to
                 turn a slot into a playing video; until then the slot renders
                 as an empty graded frame — no claims, no placeholder assets. */}
          <div className="mt-14 grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
            {SHOWCASE.map((f, i) => (
              <div
                key={i}
                className="relative overflow-hidden rounded-xl vignette film-grain animate-rise"
                style={{
                  aspectRatio: "16/9",
                  background: f.tone,
                  border: "1px solid var(--mf-line)",
                  animationDelay: `${0.12 * (i + 1)}s`,
                }}
              >
                {f.src ? (
                  <video
                    className="absolute inset-0 w-full h-full object-cover"
                    src={f.src}
                    poster={f.poster || undefined}
                    muted
                    loop
                    playsInline
                    autoPlay
                    preload="metadata"
                    aria-label={f.label}
                  />
                ) : null}
                {f.label ? (
                  <div
                    className="absolute inset-x-0 bottom-0 z-[3] flex items-center px-3 pb-3 pt-8"
                    style={{ background: "linear-gradient(to top, rgba(7,7,11,0.85), transparent)" }}
                  >
                    <span className="text-[11px] font-semibold" style={{ color: "var(--mf-ink)" }}>{f.label}</span>
                  </div>
                ) : null}
              </div>
            ))}
          </div>

          {/* ── Pipeline rail ──────────────────────────────────────────────── */}
          <div className="mt-12">
            <p className="slate-label text-center">{t("sec_pipeline")}</p>
            <div className="relative mt-6">
              {/* Connecting rail */}
              <div
                className="absolute left-0 right-0 top-[26px] h-px hidden md:block overflow-hidden"
                style={{ background: "var(--mf-line)" }}
                aria-hidden="true"
              >
                <div
                  className="h-full w-1/3 rail-sweep"
                  style={{ background: "linear-gradient(90deg, transparent, var(--mf-violet), transparent)" }}
                />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                {PIPELINE.map((p, i) => (
                  <div key={p.label} className="relative text-center">
                    <div
                      className="w-[52px] h-[52px] rounded-xl mx-auto flex items-center justify-center relative z-10"
                      style={{
                        background: "linear-gradient(180deg, var(--mf-panel-2), var(--mf-panel))",
                        border: "1px solid var(--mf-line-strong)",
                        boxShadow: "0 0 0 6px var(--mf-stage)",
                      }}
                    >
                      <p.icon size={19} style={{ color: "var(--mf-violet-soft)" }} />
                    </div>
                    <p className="text-sm font-semibold mt-3" style={{ color: "var(--mf-ink)" }}>{p.label}</p>
                    <p className="slate-label mt-1" style={{ fontSize: "10px" }}>
                      {String(i + 1).padStart(2, "0")}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <div className="sprockets" aria-hidden="true" />
      </section>

      {/* ── Live Mini Demo ───────────────────────────────────────────────── */}
      <section className="max-w-3xl mx-auto px-6 pt-16 pb-16">
        <SectionHead
          n={1}
          eyebrow={t("sec_preview")}
          title={t("sec_preview_title")}
          sub={t("sec_preview_sub")}
        />
        <MiniDemo onTryReal={(idea) => scrollToForm({ idea })} />
      </section>

      {/* ── Genre templates ─────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 pb-20">
        <SectionHead n={2} eyebrow={t("sec_genres")} title={t("genres_title")} sub={t("genres_desc")} />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {GENRE_TEMPLATES.map((g) => (
            <button
              key={g.key}
              type="button"
              onClick={() => scrollToForm({ idea: g.idea, style: g.style, directorStyle: g.directorStyle })}
              className="group relative overflow-hidden rounded-2xl text-left mf-card-hover film-grain"
              style={{ border: "1px solid var(--mf-line)", background: g.grade, minHeight: "196px" }}
            >
              {/* Key light from the top-left, like a lit set */}
              <div
                className="absolute inset-0 pointer-events-none transition-opacity duration-500 opacity-70 group-hover:opacity-100"
                style={{ background: `radial-gradient(ellipse at 12% 8%, ${g.key_light}44 0%, transparent 62%)` }}
              />
              <div
                className="absolute inset-0 pointer-events-none"
                style={{ background: "linear-gradient(to bottom, transparent 30%, rgba(7,7,11,0.82) 100%)" }}
              />
              <div className="relative h-full flex flex-col justify-between p-5" style={{ minHeight: "196px" }}>
                <div className="flex items-center justify-between">
                  <span
                    className="slate-label"
                    style={{ color: "rgba(255,255,255,0.75)", fontSize: "10px" }}
                  >
                    {g.label}
                  </span>
                  <span
                    className="w-7 h-7 rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                    style={{ backgroundColor: "rgba(255,255,255,0.14)", color: "#fff" }}
                    aria-hidden="true"
                  >
                    <ArrowRight size={14} />
                  </span>
                </div>
                <div>
                  <p className="text-sm leading-snug" style={{ color: "rgba(255,255,255,0.94)" }}>
                    {g.idea}
                  </p>
                  <p className="slate-label mt-3" style={{ fontSize: "9px", color: "rgba(255,255,255,0.45)" }}>
                    {g.directorStyle.replace(/_/g, " ")}
                  </p>
                </div>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* ── How it works ────────────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-20">
        <SectionHead n={3} eyebrow={t("sec_flow")} title={t("how_title")} />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {HOW_IT_WORKS.map((step, i) => (
            <div key={step.title} className="mf-card mf-card-hover p-6">
              <div className="flex items-center justify-between mb-5">
                <div
                  className="w-11 h-11 rounded-xl flex items-center justify-center"
                  style={{ backgroundColor: "rgba(139,92,246,0.14)", border: "1px solid rgba(139,92,246,0.3)" }}
                >
                  <step.icon size={19} style={{ color: "var(--mf-violet-soft)" }} />
                </div>
                <span className="display text-3xl" style={{ color: "var(--mf-line-strong)" }}>
                  {String(i + 1).padStart(2, "0")}
                </span>
              </div>
              <h3 className="text-sm font-semibold mb-2" style={{ color: "var(--mf-ink)" }}>{step.title}</h3>
              <p className="text-xs leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>{step.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Feature showcase ────────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-20">
        <SectionHead n={4} eyebrow={t("sec_different")} title={t("feat_title")} />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {FEATURES.map((f) => (
            <div key={f.title} className="mf-card mf-card-hover p-7 flex gap-5">
              <div
                className="w-11 h-11 rounded-xl flex-shrink-0 flex items-center justify-center"
                style={{ backgroundColor: "rgba(139,92,246,0.14)", border: "1px solid rgba(139,92,246,0.3)" }}
              >
                <f.icon size={19} style={{ color: "var(--mf-violet-soft)" }} />
              </div>
              <div>
                <h3 className="text-base font-semibold mb-2" style={{ color: "var(--mf-ink)" }}>{f.title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Director Style Gallery ──────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-6 pb-20">
        <SectionHead n={5} eyebrow={t("sec_presets")} title={t("gallery_title")} sub={t("gallery_sub")} />
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          {DIRECTOR_STYLES.map(({ style, mood, color }) => (
            <button
              key={style}
              type="button"
              className="group relative rounded-2xl overflow-hidden text-left vignette film-grain transition-transform duration-300 hover:scale-[1.03]"
              style={{ border: "1px solid var(--mf-line)", backgroundColor: "var(--mf-bg)", aspectRatio: "9/16" }}
              onClick={() => scrollToForm({ director_style: style.toLowerCase().replace(/\s+/g, "_") })}
            >
              {/* Two lights: a strong key from above and a rim from the lower
                  edge, so each preset reads as a distinctly graded frame
                  rather than five near-identical dark rectangles. */}
              <div
                className="absolute inset-0"
                style={{ background: `radial-gradient(ellipse at 50% 22%, ${color}80 0%, ${color}1a 48%, #07070b 78%)` }}
              />
              <div
                className="absolute inset-0"
                style={{ background: `radial-gradient(ellipse at 50% 100%, ${color}33 0%, transparent 55%)` }}
              />
              <div className="absolute inset-0 flex flex-col justify-end p-3 z-[3]">
                <span
                  className="slate-label mb-2 self-start px-2 py-0.5 rounded-full"
                  style={{ fontSize: "9px", backgroundColor: `${color}1f`, color, border: `1px solid ${color}3d` }}
                >
                  {t("gallery_demo_label")}
                </span>
                <p className="text-xs font-bold leading-tight" style={{ color: "var(--mf-ink)" }}>{style}</p>
                <p className="text-[10px] mt-0.5 leading-snug" style={{ color: "var(--mf-ink-3)" }}>{mood}</p>
              </div>
              <div className="absolute inset-0 z-[4] flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                style={{ backgroundColor: "rgba(7,7,11,0.45)" }}>
                <span className="mf-btn-primary px-3 py-1.5 rounded-full text-[11px] font-semibold">
                  {t("sec_try_style")} →
                </span>
              </div>
            </button>
          ))}
        </div>
      </section>

      {/* ── Comparison Table ────────────────────────────────────────────── */}
      <section className="max-w-4xl mx-auto px-6 pb-20">
        <SectionHead n={6} eyebrow={t("sec_compare")} title={t("compare_title")} sub={t("compare_sub")} />
        <div className="mf-card overflow-hidden">
          <div
            className="grid grid-cols-3 px-6 py-4 border-b"
            style={{ borderColor: "var(--mf-line)", backgroundColor: "rgba(7,7,11,0.6)" }}
          >
            <p className="slate-label" style={{ fontSize: "10px" }}>{t("compare_feature")}</p>
            <p className="text-xs font-bold text-center gradient-text">MuseForge</p>
            <p className="slate-label text-center" style={{ fontSize: "10px" }}>{t("compare_generic")}</p>
          </div>
          {[
            t("compare_char_lock"),
            t("compare_pipeline"),
            t("compare_presets"),
            t("compare_credits"),
            t("compare_demo"),
          ].map((label, i, arr) => (
            <div
              key={i}
              className="grid grid-cols-3 items-center px-6 py-4 transition-colors hover:bg-white/[0.025]"
              style={{ borderBottom: i === arr.length - 1 ? "none" : "1px solid var(--mf-line)" }}
            >
              <p className="text-sm" style={{ color: "var(--mf-ink-2)" }}>{label}</p>
              <div className="flex justify-center">
                <span
                  className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full"
                  style={{ backgroundColor: "rgba(52,211,153,0.12)", color: "var(--mf-ok)" }}
                >
                  <Check size={11} /> {t("compare_yes").replace("✓ ", "")}
                </span>
              </div>
              <div className="flex justify-center">
                <span className="text-xs" style={{ color: "var(--mf-ink-4)" }}>{t("compare_no")}</span>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-center mt-3" style={{ color: "var(--mf-ink-4)" }}>
          {t("compare_footnote")}
        </p>
      </section>

      {/* ── Generation form ─────────────────────────────────────────────── */}
      <section ref={formRef} className="relative max-w-3xl mx-auto px-6 pb-20 scroll-mt-24">
        <SectionHead n={7} eyebrow={t("sec_action")} title={t("form_title")} sub={t("form_sub")} />

        {creditsExhausted && (
          <div
            className="mb-6 px-5 py-4 rounded-xl animate-fade-in flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"
            style={{ backgroundColor: "rgba(232,182,76,0.08)", border: "1px solid rgba(232,182,76,0.35)" }}
          >
            <div>
              <p className="text-sm font-semibold" style={{ color: "var(--mf-gold)" }}>{t("credits_exhausted_title")}</p>
              <p className="text-xs mt-1" style={{ color: "var(--mf-ink-2)" }}>{t("credits_exhausted_desc")}</p>
            </div>
            <Link
              href="/pricing"
              className="mf-btn-primary inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-semibold flex-shrink-0"
            >
              {t("credits_exhausted_cta")}
            </Link>
          </div>
        )}
        {error && (
          <div
            className="mb-6 px-4 py-3 rounded-xl text-sm animate-fade-in"
            style={{ backgroundColor: "rgba(248,113,113,0.1)", border: "1px solid rgba(248,113,113,0.3)", color: "var(--mf-err-soft)" }}
          >
            {error}
          </div>
        )}
        <IdeaForm onSubmit={handleSubmit} isSubmitting={isSubmitting} prefill={prefill} />
      </section>

      {/* ── FAQ ──────────────────────────────────────────────────────────── */}
      <section className="max-w-2xl mx-auto px-6 pb-20">
        <SectionHead n={8} eyebrow={t("sec_questions")} title={t("faq_title")} />
        <div className="mf-card overflow-hidden">
          {FAQ.map(({ q, a }, i, arr) => (
            <details
              key={q}
              className="group px-6"
              style={{ borderBottom: i === arr.length - 1 ? "none" : "1px solid var(--mf-line)" }}
            >
              <summary
                className="flex items-center justify-between gap-4 py-5 cursor-pointer list-none text-sm font-medium"
                style={{ color: "var(--mf-ink)" }}
              >
                {q}
                <Plus
                  size={16}
                  className="flex-shrink-0 transition-transform duration-300 group-open:rotate-45"
                  style={{ color: "var(--mf-violet-soft)" }}
                />
              </summary>
              <p className="text-sm leading-relaxed pb-5 -mt-1" style={{ color: "var(--mf-ink-3)" }}>
                {a}
              </p>
            </details>
          ))}
        </div>
      </section>

      {/* ── Closing CTA ──────────────────────────────────────────────────── */}
      <section className="max-w-4xl mx-auto px-6 pb-24">
        <div className="relative rounded-3xl overflow-hidden text-center px-6 py-14 film-grain"
          style={{ border: "1px solid rgba(139,92,246,0.24)", backgroundColor: "var(--mf-panel)" }}>
          <div
            className="absolute inset-0 pointer-events-none"
            style={{ background: "radial-gradient(ellipse at 50% 120%, rgba(139,92,246,0.28) 0%, transparent 65%)" }}
          />
          <div className="relative">
            <ShieldCheck size={30} style={{ color: "var(--mf-violet-soft)" }} className="mx-auto mb-5" />
            <h3 className="display text-3xl md:text-4xl mb-4" style={{ color: "var(--mf-ink)" }}>{t("cta_title")}</h3>
            <p className="text-sm mb-8 max-w-md mx-auto leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>
              {t("cta_desc")}
            </p>
            <button
              type="button"
              onClick={jumpToForm}
              className="mf-btn-primary inline-flex items-center gap-2 px-8 py-4 rounded-xl text-base font-semibold"
            >
              {t("cta_btn")}
              <ArrowRight size={18} />
            </button>
          </div>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer className="border-t" style={{ borderColor: "var(--mf-line)" }}>
        <div className="max-w-5xl mx-auto px-6 py-12 grid grid-cols-2 md:grid-cols-4 gap-8">
          <div className="col-span-2 md:col-span-1">
            <div className="flex items-center gap-2 mb-3">
              <Film size={18} style={{ color: "var(--mf-violet)" }} />
              <span className="font-black tracking-tight gradient-text text-lg">MuseForge</span>
            </div>
            <p className="text-xs leading-relaxed" style={{ color: "var(--mf-ink-4)" }}>{t("footer_built")}</p>
          </div>

          <div>
            <p className="slate-label mb-3" style={{ fontSize: "10px" }}>{t("nav_solutions")}</p>
            <div className="flex flex-col gap-2 text-xs" style={{ color: "var(--mf-ink-3)" }}>
              <Link href="/solutions/agencies" className="hover:text-violet-soft transition-colors">{t("sol_agencies")}</Link>
              <Link href="/solutions/creators" className="hover:text-violet-soft transition-colors">{t("sol_creators")}</Link>
              <Link href="/solutions/filmmakers" className="hover:text-violet-soft transition-colors">{t("sol_filmmakers")}</Link>
              <Link href="/solutions/education" className="hover:text-violet-soft transition-colors">{t("sol_education")}</Link>
            </div>
          </div>

          <div>
            <p className="slate-label mb-3" style={{ fontSize: "10px" }}>{t("footer_product")}</p>
            <div className="flex flex-col gap-2 text-xs" style={{ color: "var(--mf-ink-3)" }}>
              <Link href="/pricing" className="hover:text-violet-soft transition-colors">{t("footer_pricing")}</Link>
              <Link href="/dashboard" className="hover:text-violet-soft transition-colors">{t("nav_dashboard")}</Link>
              <Link href="/login" className="hover:text-violet-soft transition-colors">{t("nav_signin")}</Link>
            </div>
          </div>

          <div>
            <p className="slate-label mb-3" style={{ fontSize: "10px" }}>{t("footer_legal")}</p>
            <div className="flex flex-col gap-2 text-xs" style={{ color: "var(--mf-ink-3)" }}>
              <Link href="/legal/privacy" className="hover:text-violet-soft transition-colors">{t("footer_privacy")}</Link>
              <Link href="/legal/terms" className="hover:text-violet-soft transition-colors">{t("footer_terms")}</Link>
            </div>
          </div>
        </div>
        <div className="hairline" />
        <p className="text-center py-6 text-xs" style={{ color: "var(--mf-ink-4)" }}>
          © {new Date().getFullYear()} MuseForge
        </p>
      </footer>
    </main>
  );
}
