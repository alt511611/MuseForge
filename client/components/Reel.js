"use client";

import { useEffect, useRef, useState } from "react";
import { Volume2, VolumeX, Clapperboard } from "lucide-react";
import { useLanguage } from "../contexts/LanguageContext";

/**
 * One example reel.
 *
 * Autoplays muted and looping only while it is on screen — three of these on a
 * page should not keep decoding video the visitor has scrolled past. Sound is
 * opt-in via the corner button, so the page is never noisy on load.
 *
 * With no `src` the slot stays an empty graded frame marked as pending: the
 * layout holds its shape while footage is being rendered, without dressing a
 * gradient up as real output.
 */
export default function Reel({ reel, className = "", showMeta = true, priority = false }) {
  const { t } = useLanguage();
  const videoRef = useRef(null);
  const frameRef = useRef(null);
  const [muted, setMuted] = useState(true);

  useEffect(() => {
    const el = videoRef.current;
    const frame = frameRef.current;
    if (!el || !frame) return;

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) el.play().catch(() => {});
        else el.pause();
      },
      { threshold: 0.25 }
    );
    io.observe(frame);
    return () => io.disconnect();
  }, [reel.src]);

  const toggleSound = () => {
    const el = videoRef.current;
    if (!el) return;
    el.muted = !el.muted;
    setMuted(el.muted);
    if (!el.muted) el.play().catch(() => {});
  };

  return (
    <figure className={className}>
      <div
        ref={frameRef}
        className="relative overflow-hidden rounded-2xl vignette film-grain"
        style={{
          aspectRatio: reel.aspect,
          background: reel.tone,
          border: "1px solid var(--mf-line)",
        }}
      >
        {reel.src ? (
          <>
            <video
              ref={videoRef}
              className="absolute inset-0 w-full h-full object-cover"
              src={reel.src}
              poster={reel.poster || undefined}
              muted
              loop
              playsInline
              preload={priority ? "metadata" : "none"}
              aria-label={reel.title}
            />
            <button
              type="button"
              onClick={toggleSound}
              aria-label={muted ? t("showcase_unmute") : t("showcase_mute")}
              className="absolute top-3 right-3 z-[4] w-9 h-9 rounded-full flex items-center justify-center transition-colors"
              style={{
                backgroundColor: "rgba(7,7,11,0.62)",
                border: "1px solid var(--mf-line-strong)",
                color: "var(--mf-ink)",
              }}
            >
              {muted ? <VolumeX size={15} /> : <Volume2 size={15} />}
            </button>
          </>
        ) : (
          /* Pending: no footage yet, and the frame says so plainly. */
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2.5 px-6 text-center">
            <Clapperboard size={22} style={{ color: "rgba(255,255,255,0.55)" }} />
            <span
              className="slate-label px-2.5 py-1 rounded-full"
              style={{
                fontSize: "9px",
                backgroundColor: "rgba(7,7,11,0.45)",
                color: "rgba(255,255,255,0.7)",
                border: "1px solid rgba(255,255,255,0.14)",
              }}
            >
              {t("showcase_pending")}
            </span>
          </div>
        )}

        {/* Title strip, held at the bottom of the frame like a lower third. */}
        <div
          className="absolute inset-x-0 bottom-0 z-[3] px-4 pb-3.5 pt-10 pointer-events-none"
          style={{ background: "linear-gradient(to top, rgba(7,7,11,0.9), transparent)" }}
        >
          <p className="text-sm font-semibold" style={{ color: "var(--mf-ink)" }}>
            {reel.title}
          </p>
          {showMeta && (
            <p className="slate-label mt-1" style={{ fontSize: "9px" }}>
              {reel.meta}
            </p>
          )}
        </div>
      </div>

      <figcaption className="mt-3 px-1">
        <p className="slate-label" style={{ fontSize: "9px" }}>
          {t("showcase_prompt_label")}
        </p>
        <p className="text-xs leading-relaxed mt-1.5" style={{ color: "var(--mf-ink-3)" }}>
          &ldquo;{reel.prompt}&rdquo;
        </p>
      </figcaption>
    </figure>
  );
}
