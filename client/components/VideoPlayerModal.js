"use client";

import { useEffect } from "react";
import { X } from "lucide-react";

/**
 * Lightweight in-page video lightbox. No body scroll lock — keep it simple.
 * Closes via X button, ESC, or backdrop click.
 */
export default function VideoPlayerModal({ src, onClose }) {
  useEffect(() => {
    if (!src) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [src, onClose]);

  if (!src) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.8)", backdropFilter: "blur(4px)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
      role="dialog"
      aria-modal="true"
      aria-label="Video player"
    >
      <div
        className="relative w-full max-w-3xl rounded-2xl overflow-hidden"
        style={{ backgroundColor: "#0a0a0f", border: "1px solid #22223a" }}
      >
        <button
          type="button"
          onClick={onClose}
          className="absolute top-3 right-3 z-10 p-1.5 rounded-lg transition-colors hover:bg-white/10"
          style={{ color: "#e2e8f0", backgroundColor: "rgba(0,0,0,0.45)" }}
          aria-label="Close"
        >
          <X size={18} />
        </button>
        <video
          key={src}
          src={src}
          controls
          autoPlay
          playsInline
          className="w-full max-h-[80vh] bg-black"
        />
      </div>
    </div>
  );
}
