"use client";

import { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";

export default function CheckoutButton({ plan, children, className = "", style = {} }) {
  const { user, getAccessToken } = useAuth();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleClick = async () => {
    if (!user) {
      router.push("/login?next=/pricing");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const token = await getAccessToken();
      const origin = window.location.origin;

      const res = await fetch("/api/create-checkout-session", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          plan,
          success_url: `${origin}/pricing?success=1&plan=${plan}`,
          cancel_url: `${origin}/pricing?cancelled=1`,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Ödeme oturumu başlatılamadı");
      }

      const { url } = await res.json();
      window.location.href = url;
    } catch (err) {
      setError(err.message);
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
      {error && (
        <p className="text-xs mt-2 text-center" style={{ color: "#fca5a5" }}>{error}</p>
      )}
    </div>
  );
}
