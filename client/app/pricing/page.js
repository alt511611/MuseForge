"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { Check, Zap, Film, Crown, Loader2, Settings } from "lucide-react";
import CheckoutButton from "../../components/CheckoutButton";
import { useAuth } from "../../contexts/AuthContext";
import { useLanguage } from "../../contexts/LanguageContext";
import Confetti from "../../components/Confetti";

function ManagePortalButton({ getAccessToken }) {
  const { t } = useLanguage();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const handle = async () => {
    setLoading(true); setErr(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/stripe-portal`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ return_url: window.location.href }),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Error"); }
      const { url } = await res.json();
      window.location.href = url;
    } catch (e) { setErr(e.message); setLoading(false); }
  };
  return (
    <div className="text-center mt-8">
      <button onClick={handle} disabled={loading}
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all"
        style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#94a3b8", opacity: loading ? 0.6 : 1 }}>
        {loading ? <Loader2 size={14} className="animate-spin" /> : <Settings size={14} />}
        {t("pricing_manage")}
      </button>
      {err && <p className="text-xs mt-2 text-center" style={{ color: "#fca5a5" }}>{err}</p>}
      <p className="text-xs mt-2" style={{ color: "#374151" }}>{t("pricing_portal_hint")}</p>
    </div>
  );
}

function PricingContent() {
  const { user, getAccessToken } = useAuth();
  const { t } = useLanguage();
  const searchParams = useSearchParams();
  const success = searchParams.get("success");
  const successPlan = searchParams.get("plan");
  const [confetti, setConfetti] = useState(false);

  useEffect(() => {
    if (success) { setConfetti(true); setTimeout(() => setConfetti(false), 5000); }
  }, [success]);

  const PLANS = [
    {
      id: "free",
      name: t("plan_free_name"),
      icon: Film,
      price: "$0",
      description: t("plan_free_desc"),
      credits: 3,
      features: ["3 videos / mo", "Up to 3 scenes", "Demo mode", "16:9 · 9:16 · 1:1 ratios", "Standard quality"],
      unavailable: ["HD export", "Priority render"],
      cta: user ? t("plan_free_cta") : t("plan_free_cta_anon"),
      highlight: false,
    },
    {
      id: "creator",
      name: t("plan_creator_name"),
      icon: Zap,
      price: "$9",
      description: t("plan_creator_desc"),
      credits: 30,
      features: ["30 videos / mo", "Up to 5 scenes", "All director presets", "All aspect ratios", "Priority render queue"],
      unavailable: ["HD export"],
      cta: t("plan_creator_cta"),
      highlight: true,
      badge: t("plan_popular"),
    },
    {
      id: "pro",
      name: t("plan_pro_name"),
      icon: Crown,
      price: "$29",
      description: t("plan_pro_desc"),
      credits: 150,
      features: ["150 videos / mo", "Up to 5 scenes", "All director presets", "All aspect ratios", "HD export", "Priority render queue", "API access (coming soon)"],
      unavailable: [],
      cta: t("plan_pro_cta"),
      highlight: false,
    },
  ];

  const PRICING_FAQ = [
    { q: t("pricing_faq_1_q"), a: t("pricing_faq_1_a") },
    { q: t("pricing_faq_2_q"), a: t("pricing_faq_2_a") },
    { q: t("pricing_faq_3_q"), a: t("pricing_faq_3_a") },
    { q: t("pricing_faq_4_q"), a: t("pricing_faq_4_a") },
  ];

  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      <Confetti active={confetti} />

      {success && (
        <div
          className="py-3 text-center text-sm font-medium animate-fade-in"
          style={{ background: "linear-gradient(90deg,rgba(34,197,94,0.2),rgba(34,197,94,0.1))", color: "#86efac", borderBottom: "1px solid rgba(34,197,94,0.2)" }}
        >
          🎉 {successPlan ? `Welcome to ${successPlan.charAt(0).toUpperCase() + successPlan.slice(1)}!` : t("pricing_success")}
        </div>
      )}

      <div className="max-w-5xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="text-center mb-14">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mb-5"
            style={{ backgroundColor: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.3)", color: "#a78bfa" }}
          >
            <Zap size={12} /> {t("pricing_badge")}
          </div>
          <h1 className="text-4xl md:text-5xl font-black tracking-tight mb-4">
            <span className="gradient-text">{t("pricing_header")}</span>
          </h1>
          <p className="text-base max-w-xl mx-auto" style={{ color: "#64748b" }}>
            {t("pricing_sub")}
          </p>
        </div>

        {/* Plans grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {PLANS.map((plan) => {
            const Icon = plan.icon;
            return (
              <div
                key={plan.id}
                className="relative glass rounded-2xl p-7 flex flex-col transition-all"
                style={{
                  border: plan.highlight ? "1px solid rgba(124,58,237,0.5)" : "1px solid rgba(124,58,237,0.1)",
                  boxShadow: plan.highlight ? "0 0 40px rgba(124,58,237,0.15)" : "none",
                }}
              >
                {plan.badge && (
                  <div
                    className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full text-xs font-semibold"
                    style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}
                  >
                    {plan.badge}
                  </div>
                )}

                <div className="flex items-center gap-3 mb-4">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center"
                    style={{ backgroundColor: plan.highlight ? "rgba(124,58,237,0.2)" : "#1a1a26" }}>
                    <Icon size={20} style={{ color: plan.highlight ? "#a78bfa" : "#64748b" }} />
                  </div>
                  <div>
                    <h2 className="text-base font-bold" style={{ color: "#e2e8f0" }}>{plan.name}</h2>
                    <p className="text-xs" style={{ color: "#64748b" }}>{plan.description}</p>
                  </div>
                </div>

                <div className="mb-6">
                  <span className="text-4xl font-black" style={{ color: "#e2e8f0" }}>{plan.price}</span>
                  <span className="text-sm ml-1" style={{ color: "#64748b" }}>{t("plan_period")}</span>
                  <p className="text-xs mt-1" style={{ color: "#475569" }}>{plan.credits} videos / mo</p>
                </div>

                <ul className="space-y-2 mb-6 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm" style={{ color: "#94a3b8" }}>
                      <Check size={14} style={{ color: "#22c55e", flexShrink: 0 }} />
                      {f}
                    </li>
                  ))}
                  {plan.unavailable.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm line-through" style={{ color: "#374151" }}>
                      <Check size={14} style={{ color: "#374151", flexShrink: 0 }} />
                      {f}
                    </li>
                  ))}
                </ul>

                {plan.id === "free" ? (
                  <Link
                    href={user ? "/" : "/login"}
                    className="w-full py-3 rounded-xl text-sm font-semibold text-center block transition-all"
                    style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#64748b" }}
                  >
                    {plan.cta}
                  </Link>
                ) : (
                  <CheckoutButton
                    plan={plan.id}
                    className="w-full py-3 rounded-xl text-sm font-semibold"
                    style={
                      plan.highlight
                        ? { background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }
                        : { backgroundColor: "#1a1a26", border: "1px solid #22223a", color: "#94a3b8" }
                    }
                  >
                    {plan.cta}
                  </CheckoutButton>
                )}
              </div>
            );
          })}
        </div>

        {/* FAQ */}
        <div className="mt-16 max-w-2xl mx-auto">
          <h2 className="text-xl font-bold text-center mb-8" style={{ color: "#e2e8f0" }}>{t("pricing_faq_title")}</h2>
          {PRICING_FAQ.map(({ q, a }) => (
            <div key={q} className="border-b py-5" style={{ borderColor: "#1a1a26" }}>
              <p className="text-sm font-medium mb-1.5" style={{ color: "#e2e8f0" }}>{q}</p>
              <p className="text-sm" style={{ color: "#64748b" }}>{a}</p>
            </div>
          ))}
        </div>

        {user && <ManagePortalButton getAccessToken={getAccessToken} />}

        <div className="text-center mt-12 text-xs space-x-4" style={{ color: "#374151" }}>
          <Link href="/legal/terms" className="hover:text-purple-400">{t("pricing_legal_terms")}</Link>
          <Link href="/legal/privacy" className="hover:text-purple-400">{t("pricing_legal_privacy")}</Link>
        </div>
      </div>
    </main>
  );
}

export default function PricingPage() {
  return (
    <Suspense fallback={null}>
      <PricingContent />
    </Suspense>
  );
}
