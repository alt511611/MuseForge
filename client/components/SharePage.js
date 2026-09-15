"use client";

import { useState } from "react";
import Link from "next/link";
import { Play, Copy, Check, Clapperboard, Clock, Layers, Code2, ArrowRight } from "lucide-react";
import { useLanguage } from "../contexts/LanguageContext";
import { tr } from "../lib/tr";
import { embedSnippet, formatDuration } from "../lib/share";

/**
 * The public page for one published film.
 *
 * A plain <Link>, not LocaleLink: /s/* is unlocalized, so a locale-aware link
 * here would prefix nothing and mislead the next person who reads it.
 *
 * The page is built around one question — "what is this, and can I make one?"
 * — and every element below the player answers the second half. The embed
 * snippet is not a convenience feature: an <iframe> someone pastes into their
 * own site is a link back that this product did not have to ask for.
 */
export default function SharePage({ share, videoUrl, pageUrl }) {
  const { t } = useLanguage();

  const aspect =
    share.aspect_ratio === "9:16"
      ? "9 / 16"
      : share.aspect_ratio === "1:1"
      ? "1 / 1"
      : "16 / 9";
  const narrow = share.aspect_ratio === "9:16";

  const facts = [
    share.scene_count
      ? {
          icon: Layers,
          text: tr(t, "share_scene_count", `${share.scene_count} scenes`, {
            n: share.scene_count,
          }),
        }
      : null,
    share.duration_seconds ? { icon: Clock, text: formatDuration(share.duration_seconds) } : null,
    share.style ? { icon: Clapperboard, text: share.style } : null,
  ].filter(Boolean);

  const setting = [share.setting_location, share.setting_time_of_day, share.setting_era]
    .filter(Boolean)
    .join(" · ");

  return (
    <main className="min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
      <div className="relative overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse 60% 40% at 50% 0%, var(--mf-violet)22 0%, transparent 70%)",
          }}
        />

        <div className="relative max-w-4xl mx-auto px-6 pt-10 pb-16">
          <div className={narrow ? "max-w-[320px] mx-auto" : ""}>
            <Player src={videoUrl} poster={share.poster_url} aspect={aspect} title={share.title} />
          </div>

          <h1 className="text-3xl md:text-4xl font-black tracking-tight mt-8 mb-3 leading-tight">
            {share.title}
          </h1>

          {share.logline && (
            <p className="text-lg leading-relaxed" style={{ color: "var(--mf-ink-2)" }}>
              {share.logline}
            </p>
          )}

          {facts.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 mt-5">
              {facts.map(({ icon: Icon, text }) => (
                <span
                  key={text}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs"
                  style={{
                    backgroundColor: "var(--mf-panel)",
                    border: "1px solid var(--mf-line-strong)",
                    color: "var(--mf-ink-3)",
                  }}
                >
                  <Icon size={12} />
                  {text}
                </span>
              ))}
            </div>
          )}

          {setting && (
            <p className="mt-4 text-sm" style={{ color: "var(--mf-ink-3)" }}>
              {setting}
            </p>
          )}

          {/* The whole reason the page is public. Placed directly under the
              film, while the visitor is still impressed by it, rather than in
              a footer nobody scrolls to. */}
          <div className="glass rounded-2xl p-6 mt-10 flex flex-col sm:flex-row sm:items-center gap-4 justify-between">
            <div>
              <p className="font-semibold mb-1">{tr(t, "share_cta_title", "Made with MuseForge")}</p>
              <p className="text-sm" style={{ color: "var(--mf-ink-3)" }}>
                {tr(
                  t,
                  "share_cta_desc",
                  "One sentence in, one finished cinematic scene out. Try it free — no API key needed."
                )}
              </p>
            </div>
            <Link
              href="/"
              className="inline-flex items-center gap-2 px-5 py-3 rounded-xl text-sm font-semibold whitespace-nowrap"
              style={{
                background: "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))",
                color: "#fff",
              }}
            >
              {tr(t, "share_cta_button", "Make your own")}
              <ArrowRight size={16} />
            </Link>
          </div>

          <EmbedBox slug={share.slug} aspectRatio={share.aspect_ratio} pageUrl={pageUrl} />
        </div>
      </div>
    </main>
  );
}

/**
 * The player.
 *
 * `preload="none"` with a poster, not `metadata`: a share link that lands on
 * Reddit is thousands of visitors fetching the head of an mp4 they may never
 * play, out of a Storage plan that has already met its quota once. The poster
 * is a still that is already generated and already cached, and the first byte
 * of video is fetched when somebody presses play.
 */
function Player({ src, poster, aspect, title }) {
  const { t } = useLanguage();
  if (!src) {
    return (
      <div
        className="rounded-2xl flex items-center justify-center text-sm"
        style={{
          aspectRatio: aspect,
          backgroundColor: "var(--mf-panel)",
          border: "1px solid var(--mf-line-strong)",
          color: "var(--mf-ink-3)",
        }}
      >
        <Play size={18} className="mr-2" />
        {tr(t, "share_video_gone", "This video is no longer available.")}
      </div>
    );
  }
  return (
    <video
      className="w-full rounded-2xl"
      style={{ aspectRatio: aspect, backgroundColor: "#000" }}
      src={src}
      poster={poster || undefined}
      controls
      playsInline
      preload="none"
      title={title}
    />
  );
}

/** Copy-to-clipboard for the page link and for the iframe. */
function EmbedBox({ slug, aspectRatio, pageUrl }) {
  const { t } = useLanguage();
  const snippet = embedSnippet(slug, aspectRatio);

  return (
    <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-3">
      <CopyField
        label={tr(t, "share_copy_link", "Link")}
        value={pageUrl}
        icon={Copy}
        done={tr(t, "share_copied", "Copied")}
      />
      <CopyField
        label={tr(t, "share_copy_embed", "Embed")}
        value={snippet}
        icon={Code2}
        done={tr(t, "share_copied", "Copied")}
      />
    </div>
  );
}

function CopyField({ label, value, icon: Icon, done }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* Clipboard is blocked (an insecure origin, a locked-down browser). The
         value is selectable in the field either way, so there is nothing to
         report and nothing to recover from. */
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      className="flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all hover:scale-[1.01]"
      style={{
        backgroundColor: "var(--mf-panel)",
        border: "1px solid var(--mf-line-strong)",
        color: "var(--mf-ink-2)",
      }}
    >
      {copied ? <Check size={16} /> : <Icon size={16} />}
      <span className="min-w-0 flex-1">
        <span className="block text-[10px] uppercase tracking-wide" style={{ color: "var(--mf-ink-3)" }}>
          {copied ? done : label}
        </span>
        <span className="block text-xs truncate font-mono">{value}</span>
      </span>
    </button>
  );
}
