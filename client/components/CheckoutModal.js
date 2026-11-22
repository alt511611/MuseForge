"use client";

import { useEffect } from "react";
import { X } from "lucide-react";
import { WhopCheckoutEmbed } from "@whop/checkout/react";
import { useLanguage } from "../contexts/LanguageContext";

/**
 * Whop's payment form, rendered inside MuseForge instead of on whop.com.
 *
 * `sessionId` is the checkout configuration the server already created (it
 * carries the user id / credit-pack metadata the webhook credits from), so the
 * on-site form bills exactly what the hosted page would. `returnUrl` is only
 * used for 3-D Secure style redirects; a plain card payment finishes in place
 * and `onComplete` sends the customer to the same success URL as before.
 */
export default function CheckoutModal({ sessionId, email, returnUrl, successUrl, onClose }) {
  const { locale } = useLanguage();

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center px-3 py-6 overflow-y-auto"
      style={{ backgroundColor: "rgba(0,0,0,0.75)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="relative w-full max-w-md rounded-2xl p-5 my-auto"
        style={{ background: "var(--mf-bg)", border: "1px solid rgba(139,92,246,0.35)" }}
      >
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute top-3 right-3"
          style={{ color: "var(--mf-ink-3)" }}
        >
          <X size={18} />
        </button>
        <div className="pt-4">
          <WhopCheckoutEmbed
            sessionId={sessionId}
            theme="dark"
            themeOptions={{
              accentColor: "#8b5cf6",
              backgroundColor: "#0a0a0f",
              borderRadius: 12,
            }}
            locale={locale}
            prefill={email ? { email } : undefined}
            returnUrl={returnUrl}
            hideTermsAndConditions={false}
            onComplete={() => { window.location.href = successUrl; }}
            fallback={
              <p className="text-sm text-center py-10" style={{ color: "var(--mf-ink-3)" }}>…</p>
            }
          />
        </div>
      </div>
    </div>
  );
}
