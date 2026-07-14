"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { Check, Zap, Film, Crown, Building2, Loader2, Settings, CreditCard, X, Sparkles, Users, BookOpen, Clapperboard } from "lucide-react";
import CheckoutButton from "../../components/CheckoutButton";
import { useAuth } from "../../contexts/AuthContext";
import { useLanguage } from "../../contexts/LanguageContext";
import Confetti from "../../components/Confetti";

// ── Credit package buy button ─────────────────────────────────────────────────
function BuyCreditsButton({ pkg, label, price, credits, highlight }) {
  const { user, getAccessToken } = useAuth();
  const { t } = useLanguage();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const handle = async () => {
    if (!user) { router.push("/login?next=/pricing"); return; }
    setLoading(true); setErr(null);
    try {
      const token = await getAccessToken();
      const base = process.env.NEXT_PUBLIC_API_URL || "";
      const res = await fetch(`${base}/api/buy-credits`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({
          package: pkg,
          success_url: `${window.location.origin}/pricing?success=1&credits=${credits}`,
          cancel_url: `${window.location.origin}/pricing`,
        }),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Error"); }
      const { url } = await res.json();
      window.location.href = url;
    } catch (e) { setErr(e.message); setLoading(false); }
  };

  return (
    <div className="flex flex-col gap-1">
      <button
        onClick={handle}
        disabled={loading}
        className="px-4 py-2 rounded-xl text-sm font-semibold transition-all"
        style={
          highlight
            ? { background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff", opacity: loading ? 0.7 : 1 }
            : { backgroundColor: "#1a1a26", border: "1px solid #22223a", color: "#94a3b8", opacity: loading ? 0.7 : 1 }
        }
      >
        {loading ? <Loader2 size={14} className="animate-spin inline mr-1" /> : null}
        {t("pricing_credits_buy")}
      </button>
      {err && <p className="text-[11px] text-red-400">{err}</p>}
    </div>
  );
}

// ── Stripe portal button ──────────────────────────────────────────────────────
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

// ── Main content ──────────────────────────────────────────────────────────────
function PricingContent() {
  const { user, getAccessToken } = useAuth();
  const { t } = useLanguage();
  const searchParams = useSearchParams();
  const success = searchParams.get("success");
  const creditsBought = searchParams.get("credits");
  const successPlan = searchParams.get("plan");
  const [confetti, setConfetti] = useState(false);

  useEffect(() => {
    if (success) { setConfetti(true); setTimeout(() => setConfetti(false), 5000); }
  }, [success]);

  const SEGMENT_LINKS = [
    { icon: Building2, label: t("sol_agencies"),   href: "/solutions/agencies" },
    { icon: Users,     label: t("sol_creators"),   href: "/solutions/creators" },
    { icon: Clapperboard, label: t("sol_filmmakers"), href: "/solutions/filmmakers" },
    { icon: BookOpen,  label: t("sol_education"),  href: "/solutions/education" },
  ];

  const PLANS = [
    {
      id: "creator",
      name: t("plan_creator_name"),
      icon: Zap,
      price: "$49",
      description: t("plan_creator_desc"),
      forWho: "Content creators, small businesses & educators",
      segHref: "/solutions/creators",
      segIcon: Users,
      credits: 120,
      features: t("plan_creator_features").split(","),
      unavailable: t("plan_creator_unavailable").split(",").filter(Boolean),
      cta: t("plan_creator_cta"),
      highlight: false,
    },
    {
      id: "pro",
      name: t("plan_pro_name"),
      icon: Crown,
      price: "$99",
      description: t("plan_pro_desc"),
      forWho: "Agencies & corporate communications teams",
      segHref: "/solutions/agencies",
      segIcon: Building2,
      credits: 300,
      features: t("plan_pro_features").split(","),
      unavailable: t("plan_pro_unavailable").split(",").filter(Boolean),
      cta: t("plan_pro_cta"),
      highlight: true,
      badge: t("plan_popular"),
    },
    {
      id: "enterprise",
      name: t("pricing_enterprise_name"),
      icon: Building2,
      price: t("pricing_enterprise_price"),
      description: t("pricing_enterprise_desc"),
      forWho: "Large institutions & enterprise-wide licences",
      segHref: "/solutions/education",
      segIcon: BookOpen,
      credits: null,
      features: ["Custom credit volume", "Dedicated support", "SLA & uptime guarantee", "SSO / team admin", "Custom onboarding"],
      unavailable: [],
      cta: t("pricing_enterprise_cta"),
      highlight: false,
      isEnterprise: true,
    },
  ];

  const CREDIT_PACKAGES = [
    { key: "SMALL",  label: t("pricing_credits_small"),  price: "$9",  credits: 20,  highlight: false },
    { key: "MEDIUM", label: t("pricing_credits_medium"), price: "$19", credits: 60,  highlight: true },
    { key: "LARGE",  label: t("pricing_credits_large"),  price: "$39", credits: 150, highlight: false },
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
        <div className="py-3 text-center text-sm font-medium animate-fade-in"
          style={{ background: "linear-gradient(90deg,rgba(34,197,94,0.2),rgba(34,197,94,0.1))", color: "#86efac", borderBottom: "1px solid rgba(34,197,94,0.2)" }}>
          🎉 {creditsBought
            ? `${creditsBought} credits added to your account!`
            : successPlan
              ? `Welcome to ${successPlan.charAt(0).toUpperCase() + successPlan.slice(1)}!`
              : t("pricing_success")}
        </div>
      )}

      <div className="max-w-6xl mx-auto px-6 py-16">
        {/* Header */}
        <div className="text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mb-5"
            style={{ backgroundColor: "rgba(124,58,237,0.15)", border: "1px solid rgba(124,58,237,0.3)", color: "#a78bfa" }}>
            <Zap size={12} /> {t("pricing_badge")}
          </div>
          <h1 className="text-4xl md:text-5xl font-black tracking-tight mb-4">
            <span className="gradient-text">{t("pricing_header")}</span>
          </h1>
          <p className="text-base max-w-xl mx-auto mb-8" style={{ color: "#64748b" }}>{t("pricing_sub")}</p>

          {/* Segment links */}
          <div className="flex flex-wrap justify-center gap-2">
            {SEGMENT_LINKS.map(({ icon: Icon, label, href }) => (
              <Link key={href} href={href}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all hover:border-purple-500/50"
                style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#64748b" }}>
                <Icon size={12} style={{ color: "#7c3aed" }} />
                {label}
              </Link>
            ))}
          </div>
        </div>

        {/* Plans grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-16">
          {PLANS.map((plan) => {
            const Icon = plan.icon;
            const SegIcon = plan.segIcon;
            return (
              <div key={plan.id} className="relative glass rounded-2xl p-7 flex flex-col transition-all hover:scale-[1.01]"
                style={{
                  border: plan.highlight ? "1px solid rgba(124,58,237,0.5)" : "1px solid rgba(124,58,237,0.1)",
                  boxShadow: plan.highlight ? "0 0 40px rgba(124,58,237,0.12)" : "none",
                }}>
                {plan.badge && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full text-xs font-semibold whitespace-nowrap"
                    style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
                    {plan.badge}
                  </div>
                )}

                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ backgroundColor: plan.highlight ? "rgba(124,58,237,0.2)" : "#1a1a26" }}>
                    <Icon size={20} style={{ color: plan.highlight ? "#a78bfa" : "#64748b" }} />
                  </div>
                  <div>
                    <h2 className="text-base font-bold" style={{ color: "#e2e8f0" }}>{plan.name}</h2>
                    <p className="text-xs" style={{ color: "#64748b" }}>{plan.description}</p>
                  </div>
                </div>

                {/* For who */}
                <Link href={plan.segHref}
                  className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg mb-4 transition-colors hover:bg-white/5"
                  style={{ backgroundColor: "rgba(124,58,237,0.06)", color: "#a78bfa", border: "1px solid rgba(124,58,237,0.15)" }}>
                  <SegIcon size={11} />
                  {plan.forWho}
                </Link>

                <div className="mb-6">
                  <span className="text-4xl font-black" style={{ color: "#e2e8f0" }}>{plan.price}</span>
                  {!plan.isEnterprise && <span className="text-sm ml-1" style={{ color: "#64748b" }}>{t("plan_period")}</span>}
                  {plan.credits && (
                    <p className="text-xs mt-1 font-medium" style={{ color: "#7c3aed" }}>
                      <Sparkles size={10} className="inline mr-1" />
                      {plan.credits} credits / mo
                    </p>
                  )}
                </div>

                <ul className="space-y-2 mb-6 flex-1">
                  {plan.features.map((f) => f && (
                    <li key={f} className="flex items-start gap-2 text-sm" style={{ color: "#94a3b8" }}>
                      <Check size={13} className="mt-0.5 flex-shrink-0" style={{ color: "#22c55e" }} />
                      {f}
                    </li>
                  ))}
                  {plan.unavailable.map((f) => f && (
                    <li key={f} className="flex items-center gap-2 text-sm line-through" style={{ color: "#374151" }}>
                      <X size={13} className="flex-shrink-0" style={{ color: "#374151" }} />
                      {f}
                    </li>
                  ))}
                </ul>

                {plan.isEnterprise ? (
                  <Link href="mailto:enterprise@museforge.ai"
                    className="w-full py-3 rounded-xl text-sm font-semibold text-center block transition-all"
                    style={{ backgroundColor: "#1a1a26", border: "1px solid #22223a", color: "#94a3b8" }}>
                    {plan.cta}
                  </Link>
                ) : plan.id === "free" ? (
                  <Link href={user ? "/" : "/login"}
                    className="w-full py-3 rounded-xl text-sm font-semibold text-center block transition-all"
                    style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#64748b" }}>
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

        {/* Credit Packages strip */}
        <div className="glass rounded-2xl p-8 mb-16" style={{ border: "1px solid rgba(124,58,237,0.15)" }}>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
            <div>
              <h2 className="text-xl font-bold" style={{ color: "#e2e8f0" }}>
                <CreditCard size={18} className="inline mr-2" style={{ color: "#7c3aed" }} />
                {t("pricing_credits_title")}
              </h2>
              <p className="text-sm mt-1" style={{ color: "#64748b" }}>{t("pricing_credits_sub")}</p>
            </div>
            <Link href="/solutions/filmmakers"
              className="text-xs px-3 py-1.5 rounded-xl transition-colors hover:border-purple-500/40"
              style={{ backgroundColor: "#12121a", border: "1px solid #22223a", color: "#a78bfa" }}>
              {t("sol_filmmakers")} →
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {CREDIT_PACKAGES.map((pkg) => (
              <div key={pkg.key}
                className="flex items-center justify-between p-4 rounded-xl"
                style={{
                  backgroundColor: pkg.highlight ? "rgba(124,58,237,0.08)" : "#0d0d14",
                  border: pkg.highlight ? "1px solid rgba(124,58,237,0.35)" : "1px solid #1a1a26",
                }}>
                <div>
                  <p className="text-sm font-bold" style={{ color: "#e2e8f0" }}>{pkg.label}</p>
                  <p className="text-2xl font-black mt-0.5" style={{ color: pkg.highlight ? "#a78bfa" : "#64748b" }}>{pkg.price}</p>
                  <p className="text-xs mt-0.5" style={{ color: "#475569" }}>${(parseFloat(pkg.price.replace("$","")) / pkg.credits).toFixed(2)}/credit</p>
                </div>
                <BuyCreditsButton
                  pkg={pkg.key}
                  credits={pkg.credits}
                  highlight={pkg.highlight}
                />
              </div>
            ))}
          </div>
        </div>

        {/* FAQ */}
        <div className="max-w-2xl mx-auto mb-12">
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
