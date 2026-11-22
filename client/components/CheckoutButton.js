"use client";

import { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { API_BASE } from "../lib/apiBase";
import { useLanguage } from "../contexts/LanguageContext";
import { friendlyError } from "../utils/errorMessages";
import CheckoutModal from "./CheckoutModal";

export default function CheckoutButton({ plan, interval = "annual", children, className = "", style = {} }) {
  const { user, getAccessToken } = useAuth();
  const { t, localeHref } = useLanguage();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [embed, setEmbed] = useState(null);

  const handleClick = async () => {
    if (!user) {
      router.push(localeHref("/login?next=/pricing"));
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const token = await getAccessToken();
      const origin = window.location.origin;

      const res = await fetch(`${API_BASE}/api/create-checkout-session`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          plan,
          // Sent explicitly rather than left to the server default, so the
          // cycle the customer is charged on is always the one the toggle was
          // showing when they clicked.
          interval,
          success_url: `${origin}/pricing?success=1&plan=${plan}`,
          cancel_url: `${origin}/pricing?cancelled=1`,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || t("checkout_failed"));
      }

      const { url, session_id } = await res.json();
      if (session_id) {
        // Whop: take the payment on this page. Stripe (no session_id) and any
        // failure to mount the form still fall back to the hosted redirect.
        setEmbed({
          sessionId: session_id,
          successUrl: `${origin}/pricing?success=1&plan=${plan}`,
        });
        setLoading(false);
        return;
      }
      window.location.href = url;
    } catch (err) {
      setError(friendlyError(err.message));
      setLoading(false);
    }
  };

  return (
    <div>
      <button
        onClick={handleClick}
        disabled={loading}
        className={`flex items-center justify-center gap-2 transition-all ${className}`}
        style={{ opacity: loading ? 0.7 : 1, cursor: loading ? "not-allowed" : "pointer", ...style }}
      >
        {loading ? <Loader2 size={16} className="animate-spin" /> : null}
        {children}
      </button>
      {embed && (
        <CheckoutModal
          sessionId={embed.sessionId}
          email={user?.email}
          returnUrl={embed.successUrl}
          successUrl={embed.successUrl}
          onClose={() => setEmbed(null)}
        />
      )}
      {error && (
        <p className="text-xs mt-2 text-center" style={{ color: "var(--mf-err-soft)" }}>{error}</p>
      )}
    </div>
  );
}
