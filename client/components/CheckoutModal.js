"use client";

import { useEffect, useMemo } from "react";
import { X } from "lucide-react";
import { Checkout, CheckoutElement, WhopElements } from "@whop/elements-react";
import { loadWhop } from "@whop/elements";
import { useLanguage } from "../contexts/LanguageContext";

/**
 * Whop's payment form, rendered inside MuseForge instead of on whop.com.
 *
 * Built on Whop Elements (`@whop/elements-react`). The first version used the
 * legacy `@whop/checkout` embed, which answers "This checkout is no longer
 * available" for every fresh checkout configuration.
 *
 * `sessionId` is the checkout configuration (`ch_...`) the server already
 * created: it names the plan and carries the user-id / credit-pack metadata the
 * webhook credits from, so the on-site form bills exactly what the hosted page
 * would. Fulfilment is the webhook's job -- `onComplete` only sends the
 * customer on to the success page.
 *
 * `returnUrl` is where an off-site step (3-D Secure, a bank page) lands, with
 * `payment` and `status` appended. It is the same success URL; the pricing and
 * dashboard pages treat that visit as a display, not as proof of payment.
 */
export default function CheckoutModal({ sessionId, email, returnUrl, successUrl, onClose }) {
  const { locale } = useLanguage();
  // Created once per mount, in the browser: this component only renders after
  // a click, so there is no server render to disagree with.
  const elements = useMemo(() => loadWhop(), []);

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
          <WhopElements elements={elements}>
            <Checkout
              checkoutConfiguration={sessionId}
              returnUrl={returnUrl}
              locale={locale}
              appearance={{
                theme: { appearance: "dark", accentColor: "violet" },
              }}
              onComplete={() => { window.location.href = successUrl; }}
            >
              <CheckoutElement buyerEmail={email || ""} />
            </Checkout>
          </WhopElements>
        </div>
      </div>
    </div>
  );
}
