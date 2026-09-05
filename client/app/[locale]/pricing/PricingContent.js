"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Link from "../../../components/LocaleLink";
import { Check, Zap, Film, Crown, Building2, Loader2, Settings, CreditCard, X, Sparkles, Users, BookOpen, Clapperboard, Plus } from "lucide-react";
import CheckoutButton from "../../../components/CheckoutButton";
import { useAuth } from "../../../contexts/AuthContext";
import { useLanguage } from "../../../contexts/LanguageContext";
import Confetti from "../../../components/Confetti";
import { API_BASE } from "../../../lib/apiBase";
import { friendlyError } from "../../../utils/errorMessages";
import { tr } from "../../../lib/tr";

// ── Credit package buy button ─────────────────────────────────────────────────
function BuyCreditsButton({ pkg, label, price, credits, highlight }) {
  const { user, getAccessToken } = useAuth();
  const { t, localeHref } = useLanguage();
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const handle = async () => {
    if (!user) { router.push(localeHref("/login?next=/pricing")); return; }
    setLoading(true); setErr(null);
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/buy-credits`, {
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
    } catch (e) { setErr(friendlyError(e.message)); setLoading(false); }
  };

  return (
    <div className="flex flex-col gap-1">
      <button
        onClick={handle}
        disabled={loading}
        className={`px-4 py-2 rounded-xl text-sm font-semibold ${highlight ? "mf-btn-primary" : "mf-btn-ghost"}`}
        style={{ opacity: loading ? 0.7 : 1 }}
      >
        {loading ? <Loader2 size={14} className="animate-spin inline mr-1" /> : null}
        {t("pricing_credits_buy")}
      </button>
      {err && <p className="text-[11px]" style={{ color: "var(--mf-err-soft)" }}>{err}</p>}
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
      const res = await fetch(`${API_BASE}/api/stripe-portal`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ return_url: window.location.href }),
      });
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail || "Error"); }
      const { url } = await res.json();
      window.location.href = url;
    } catch (e) { setErr(friendlyError(e.message)); setLoading(false); }
  };
  return (
    <div className="text-center mt-8">
      <button onClick={handle} disabled={loading}
        className="mf-btn-ghost inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium"
        style={{ opacity: loading ? 0.6 : 1 }}>
        {loading ? <Loader2 size={14} className="animate-spin" /> : <Settings size={14} />}
        {t("pricing_manage")}
      </button>
      {err && <p className="text-xs mt-2 text-center" style={{ color: "var(--mf-err-soft)" }}>{err}</p>}
      <p className="text-xs mt-2" style={{ color: "var(--mf-ink-4)" }}>{t("pricing_portal_hint")}</p>
    </div>
  );
}

// ── Billing interval ──────────────────────────────────────────────────────────

/** Discount on annual. Must match the annual Stripe Prices; the page only
 *  quotes it. Server side: stripe_integration.ANNUAL_DISCOUNT_PERCENT. */
const ANNUAL_DISCOUNT_PERCENT = 10;

/** What one credit buys, in seconds of finished film. Mirrors
 *  server/interfaces/second_budget.SECONDS_PER_CREDIT — the single number that
 *  makes our credit comparable to a competitor's metered one. Raised 8 → 10
 *  when we learned the video provider bills per clip rather than per second,
 *  so the extra seconds cost nothing; test_pricing_coherence pins the two
 *  sides together. */
const SECONDS_PER_CREDIT = 10;

/** Rate shown on the card. Annual is quoted PER MONTH because that is the
 *  number buyers compare across products; the yearly total is spelled out
 *  right underneath so the actual charge is never a surprise. */
function monthlyRate(monthly, annual) {
  if (!monthly) return 0;
  return annual ? Math.round(monthly * (1 - ANNUAL_DISCOUNT_PERCENT / 100)) : monthly;
}

/** What the card is actually charged on an annual plan. Derived from the
 *  undiscounted monthly price, NOT from the rounded monthly rate above —
 *  rounding twice would quote a total that does not match Stripe's Price. */
function annualTotal(monthly) {
  return Math.round(monthly * 12 * (1 - ANNUAL_DISCOUNT_PERCENT / 100));
}

function IntervalToggle({ interval, onChange }) {
  const { t } = useLanguage();
  const options = [
    {
      id: "annual",
      label: tr(t, "pricing_annual", "Yıllık"),
      // One key for the whole badge, not a number glued to a translated word:
      // "%10 indirim" and "10% off" put the sign on opposite sides, so a
      // template built here can only ever be right in one language.
      badge: tr(t, "pricing_off_badge", "%{percent} indirim").replace(
        "{percent}",
        String(ANNUAL_DISCOUNT_PERCENT)
      ),
    },
    { id: "monthly", label: tr(t, "pricing_monthly", "Aylık"), badge: null },
  ];

  return (
    <div
      className="inline-flex items-center p-1 rounded-full mb-8"
      style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line-strong)" }}
      role="group"
      aria-label={tr(t, "pricing_interval", "Faturalama dönemi")}
    >
      {options.map((option) => {
        const active = interval === option.id;
        return (
          <button
            key={option.id}
            type="button"
            onClick={() => onChange(option.id)}
            aria-pressed={active}
            className="inline-flex items-center gap-2 px-5 py-2 rounded-full text-sm font-medium transition-all"
            style={{
              background: active
                ? "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))"
                : "transparent",
              color: active ? "#fff" : "var(--mf-ink-3)",
            }}
          >
            {option.label}
            {option.badge && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded-full font-semibold"
                style={{
                  backgroundColor: active ? "rgba(255,255,255,0.18)" : "rgba(52,211,153,0.15)",
                  color: active ? "#fff" : "var(--mf-ok)",
                }}
              >
                {option.badge}
              </span>
            )}
          </button>
        );
      })}
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
  // Annual first: it is the cheaper offer, so it is the one that should be on
  // screen before anyone touches anything.
  const [interval, setInterval] = useState("annual");

  useEffect(() => {
    if (success) { setConfetti(true); setTimeout(() => setConfetti(false), 5000); }
  }, [success]);

  const SEGMENT_LINKS = [
    { icon: Building2, label: t("sol_agencies"),   href: "/solutions/agencies" },
    { icon: Users,     label: t("sol_creators"),   href: "/solutions/creators" },
    { icon: Clapperboard, label: t("sol_filmmakers"), href: "/solutions/filmmakers" },
    { icon: BookOpen,  label: t("sol_education"),  href: "/solutions/education" },
  ];

  const annual = interval === "annual";

  const PLANS = [
    {
      id: "free",
      name: t("plan_free_name"),
      icon: Film,
      monthly: 0,
      description: t("plan_free_desc"),
      forWho: t("plan_free_forwho"),
      segHref: "/",
      segIcon: Sparkles,
      credits: 3,
      features: t("plan_free_features").split(","),
      unavailable: t("plan_free_unavailable").split(",").filter(Boolean),
      cta: user ? t("plan_free_cta") : t("plan_free_cta_anon"),
      highlight: false,
    },
    {
      id: "creator",
      name: t("plan_creator_name"),
      icon: Zap,
      monthly: 59,
      description: t("plan_creator_desc"),
      forWho: "Content creators, small businesses & educators",
      segHref: "/solutions/creators",
      segIcon: Users,
      credits: 16,
      features: t("plan_creator_features").split(","),
      unavailable: t("plan_creator_unavailable").split(",").filter(Boolean),
      cta: t("plan_creator_cta"),
      highlight: false,
    },
    {
      id: "pro",
      name: t("plan_pro_name"),
      icon: Crown,
      monthly: 129,
      description: t("plan_pro_desc"),
      forWho: "Agencies & corporate communications teams",
      segHref: "/solutions/agencies",
      segIcon: Building2,
      credits: 36,
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
      features: ["Custom credit volume", "Commercial use rights", "Dedicated support", "SLA & uptime guarantee", "SSO / team admin", "Cancel anytime"],
      unavailable: [],
      cta: t("pricing_enterprise_cta"),
      highlight: false,
      isEnterprise: true,
    },
  ];

  const CREDIT_PACKAGES = [
    { key: "SMALL",  label: t("pricing_credits_small"),  price: "$19", credits: 4,  highlight: false },
    { key: "MEDIUM", label: t("pricing_credits_medium"), price: "$49", credits: 12, highlight: true },
    { key: "LARGE",  label: t("pricing_credits_large"),  price: "$99", credits: 26, highlight: false },
  ];

  const PRICING_FAQ = [
    { q: t("pricing_faq_1_q"), a: t("pricing_faq_1_a") },
    { q: t("pricing_faq_2_q"), a: t("pricing_faq_2_a") },
    { q: t("pricing_faq_3_q"), a: t("pricing_faq_3_a") },
    { q: t("pricing_faq_4_q"), a: t("pricing_faq_4_a") },
  ];

  return (
    <main className="min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
      <Confetti active={confetti} />

      {success && (
        <div className="py-3 text-center text-sm font-medium animate-fade-in"
          style={{ background: "linear-gradient(90deg,rgba(52,211,153,0.18),rgba(52,211,153,0.08))", color: "var(--mf-ok)", borderBottom: "1px solid rgba(52,211,153,0.25)" }}>
          🎉 {creditsBought
            ? `${creditsBought} credits added to your account!`
            : successPlan
              ? `Welcome to ${successPlan.charAt(0).toUpperCase() + successPlan.slice(1)}!`
              : t("pricing_success")}
        </div>
      )}

      {/* Stage lighting, matching the landing hero so the two pages read as
          one product rather than two templates. */}
      <div className="relative overflow-hidden film-grain">
        <div className="absolute inset-0 pointer-events-none" aria-hidden="true">
          <div
            className="absolute -top-40 left-1/2 -translate-x-1/2 w-[900px] h-[500px] rounded-full"
            style={{ background: "radial-gradient(ellipse at center, rgba(139,92,246,0.26) 0%, transparent 68%)", filter: "blur(90px)" }}
          />
        </div>

        <div className="relative max-w-6xl mx-auto px-6 pt-16 pb-10 text-center animate-rise">
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium mb-6"
            style={{ backgroundColor: "rgba(139,92,246,0.12)", border: "1px solid rgba(139,92,246,0.32)", color: "var(--mf-violet-soft)" }}>
            <Zap size={12} /> {t("pricing_badge")}
          </div>
          <h1 className="display text-display-sm md:text-display-md mb-5" style={{ color: "var(--mf-ink)" }}>
            {t("pricing_header")}
          </h1>
          <p className="text-base md:text-lg max-w-xl mx-auto mb-3" style={{ color: "var(--mf-ink-2)" }}>{t("pricing_sub")}</p>
          <p className="slate-label mb-6" style={{ color: "var(--mf-gold)" }}>{t("pricing_cancel_anytime")}</p>

          <div>
            <IntervalToggle interval={interval} onChange={setInterval} />
          </div>

          {/* Segment links */}
          <div className="flex flex-wrap justify-center gap-2">
            {SEGMENT_LINKS.map(({ icon: Icon, label, href }) => (
              <Link key={href} href={href}
                className="mf-btn-ghost inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-medium">
                <Icon size={12} style={{ color: "var(--mf-violet)" }} />
                {label}
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 pb-16">

        {/* Plans grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-6 mb-16">
          {PLANS.map((plan) => {
            const Icon = plan.icon;
            const SegIcon = plan.segIcon;
            return (
              <div key={plan.id} className="relative mf-card mf-card-hover p-7 flex flex-col"
                style={{
                  borderColor: plan.highlight ? "rgba(139,92,246,0.5)" : "var(--mf-line)",
                  boxShadow: plan.highlight ? "var(--mf-glow)" : "none",
                }}>
                {plan.badge && (
                  <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-4 py-1 rounded-full text-xs font-semibold whitespace-nowrap"
                    style={{ background: "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))", color: "#fff" }}>
                    {plan.badge}
                  </div>
                )}

                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ backgroundColor: plan.highlight ? "rgba(139,92,246,0.2)" : "var(--mf-line)" }}>
                    <Icon size={20} style={{ color: plan.highlight ? "var(--mf-violet-soft)" : "var(--mf-ink-3)" }} />
                  </div>
                  <div>
                    <h2 className="text-base font-bold" style={{ color: "var(--mf-ink)" }}>{plan.name}</h2>
                    <p className="text-xs" style={{ color: "var(--mf-ink-3)" }}>{plan.description}</p>
                  </div>
                </div>

                {/* For who */}
                <Link href={plan.segHref}
                  className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg mb-4 transition-colors hover:bg-white/5"
                  style={{ backgroundColor: "rgba(139,92,246,0.06)", color: "var(--mf-violet-soft)", border: "1px solid rgba(139,92,246,0.15)" }}>
                  <SegIcon size={11} />
                  {plan.forWho}
                </Link>

                <div className="mb-6">
                  <span className="display text-4xl" style={{ color: "var(--mf-ink)" }}>
                    {plan.isEnterprise ? t("pricing_enterprise_price") : `$${monthlyRate(plan.monthly, annual)}`}
                  </span>
                  {!plan.isEnterprise && <span className="text-sm ml-1.5" style={{ color: "var(--mf-ink-3)" }}>{t("plan_period")}</span>}
                  {/* Annual is quoted as a monthly rate with the real charge
                      spelled out underneath: the number people compare is the
                      monthly one, and the number their card is charged must
                      not be a surprise. */}
                  {!plan.isEnterprise && plan.monthly > 0 && (
                    <p className="text-xs mt-1.5" style={{ color: annual ? "var(--mf-gold)" : "var(--mf-ink-4)" }}>
                      {annual
                        ? tr(t, "pricing_billed_yearly", "yılda ${total} olarak faturalanır")
                            .replace("{total}", annualTotal(plan.monthly))
                        : tr(t, "pricing_billed_monthly", "aylık faturalanır · yıllıkta %{off} indirim")
                            .replace("{off}", String(ANNUAL_DISCOUNT_PERCENT))}
                    </p>
                  )}
                  {plan.credits && (
                    <p className="slate-label mt-2 flex items-center gap-1.5" style={{ color: "var(--mf-violet-soft)" }}>
                      <Sparkles size={10} />
                      {tr(t, "pricing_credits_per_month", "{credits} kredi / ay").replace(
                        "{credits}",
                        String(plan.credits)
                      )}
                    </p>
                  )}
                  {plan.credits && (
                    <p className="text-xs mt-1" style={{ color: "var(--mf-ink-4)" }}>
                      {tr(t, "pricing_credits_as_seconds", "≈ {seconds} sn bitmiş film / ay")
                        .replace("{seconds}", String(plan.credits * SECONDS_PER_CREDIT))}
                    </p>
                  )}
                </div>

                <ul className="space-y-2 mb-6 flex-1">
                  {plan.features.map((f) => f && (
                    <li key={f} className="flex items-start gap-2 text-sm" style={{ color: "var(--mf-ink-2)" }}>
                      <Check size={13} className="mt-0.5 flex-shrink-0" style={{ color: "var(--mf-ok)" }} />
                      {f}
                    </li>
                  ))}
                  {plan.unavailable.map((f) => f && (
                    <li key={f} className="flex items-center gap-2 text-sm line-through" style={{ color: "var(--mf-ink-4)" }}>
                      <X size={13} className="flex-shrink-0" style={{ color: "var(--mf-ink-4)" }} />
                      {f}
                    </li>
                  ))}
                </ul>

                {plan.isEnterprise ? (
                  <Link href="mailto:enterprise@museforge.ai"
                    className="mf-btn-ghost w-full py-3 rounded-xl text-sm font-semibold text-center block">
                    {plan.cta}
                  </Link>
                ) : plan.id === "free" ? (
                  <Link href={user ? "/" : "/login"}
                    className="mf-btn-ghost w-full py-3 rounded-xl text-sm font-semibold text-center block">
                    {plan.cta}
                  </Link>
                ) : (
                  <CheckoutButton
                    plan={plan.id}
                    interval={interval}
                    className={`w-full py-3 rounded-xl text-sm font-semibold ${plan.highlight ? "mf-btn-primary" : "mf-btn-ghost"}`}
                  >
                    {plan.cta}
                  </CheckoutButton>
                )}
              </div>
            );
          })}
        </div>

        {/* What a credit actually buys.
            Competitors meter raw model compute, so their credit counts are an
            order of magnitude larger for the same money. Without this block a
            visitor compares "36 credits" against "800 credits" and draws the
            obvious, wrong conclusion. */}
        <div className="mf-card p-8 mb-16" style={{ borderColor: "rgba(139,92,246,0.2)" }}>
          <h2 className="text-xl font-bold flex items-center gap-2 mb-2" style={{ color: "var(--mf-ink)" }}>
            <Sparkles size={18} style={{ color: "var(--mf-violet)" }} />
            {tr(t, "pricing_credit_meaning_title", "1 kredi ne satın alır?")}
          </h2>
          <p className="text-sm mb-6" style={{ color: "var(--mf-ink-3)" }}>
            {tr(
              t,
              "pricing_credit_meaning_sub",
              "Bizim kredimiz ham model hesabı değil, bitmiş bir sahne. Senaryo, storyboard, karakter kilidi, kare üretimi, video, kurgu ve mastering dahil."
            )}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {[
              {
                head: `${SECONDS_PER_CREDIT} ${tr(t, "pricing_credit_seconds", "saniye")}`,
                body: tr(t, "pricing_credit_seconds_desc", "kredi başına bitmiş, izlenebilir film"),
              },
              {
                head: tr(t, "pricing_credit_included_head", "Her şey dahil"),
                body: tr(
                  t,
                  "pricing_credit_included_desc",
                  "Senaryo, storyboard, karakter tutarlılığı, renk, müzik ve mastering ayrı ücretlendirilmez"
                ),
              },
              {
                head: tr(t, "pricing_credit_free_head", "Kurgu ücretsiz"),
                body: tr(
                  t,
                  "pricing_credit_free_desc",
                  "Sahne sıralama, kırpma ve çıkarma kredi harcamaz — klipler zaten sizin"
                ),
              },
            ].map((item) => (
              <div key={item.head} className="p-4 rounded-xl" style={{ backgroundColor: "var(--mf-bg)", border: "1px solid var(--mf-line)" }}>
                <p className="display text-2xl" style={{ color: "var(--mf-violet-soft)" }}>{item.head}</p>
                <p className="text-xs mt-1.5 leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>{item.body}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Credit Packages strip */}
        <div className="mf-card p-8 mb-16" style={{ borderColor: "rgba(139,92,246,0.2)" }}>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-6">
            <div>
              <h2 className="text-xl font-bold flex items-center gap-2" style={{ color: "var(--mf-ink)" }}>
                <CreditCard size={18} style={{ color: "var(--mf-violet)" }} />
                {t("pricing_credits_title")}
              </h2>
              <p className="text-sm mt-1" style={{ color: "var(--mf-ink-3)" }}>{t("pricing_credits_sub")}</p>
            </div>
            <Link href="/solutions/filmmakers"
              className="mf-btn-ghost text-xs px-3.5 py-2 rounded-xl">
              {t("sol_filmmakers")} →
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {CREDIT_PACKAGES.map((pkg) => (
              <div key={pkg.key}
                className="flex items-center justify-between p-4 rounded-xl"
                style={{
                  backgroundColor: pkg.highlight ? "rgba(139,92,246,0.08)" : "var(--mf-bg)",
                  border: pkg.highlight ? "1px solid rgba(139,92,246,0.35)" : "1px solid var(--mf-line)",
                }}>
                <div>
                  <p className="slate-label" style={{ fontSize: "10px" }}>{pkg.label}</p>
                  <p className="display text-2xl mt-1.5" style={{ color: pkg.highlight ? "var(--mf-violet-soft)" : "var(--mf-ink)" }}>{pkg.price}</p>
                  <p className="text-xs mt-1" style={{ color: "var(--mf-ink-4)" }}>${(parseFloat(pkg.price.replace("$","")) / pkg.credits).toFixed(2)}/credit</p>
                  {/* Packs were bought outright, so they get a year — unlike
                      the monthly allowance, which is rented and lapses with
                      the month. Server side: PACK_CREDIT_VALIDITY_DAYS. */}
                  <p className="text-[11px] mt-1" style={{ color: "var(--mf-ok)" }}>
                    {tr(t, "pricing_pack_validity", "12 ay geçerli")}
                  </p>
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

        {/* FAQ — same accordion pattern as the landing page */}
        <div className="max-w-2xl mx-auto mb-12">
          <p className="slate-label text-center">Questions</p>
          <h2 className="display text-3xl text-center mt-3 mb-8" style={{ color: "var(--mf-ink)" }}>{t("pricing_faq_title")}</h2>
          <div className="mf-card overflow-hidden">
            {PRICING_FAQ.map(({ q, a }, i, arr) => (
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
                <p className="text-sm leading-relaxed pb-5 -mt-1" style={{ color: "var(--mf-ink-3)" }}>{a}</p>
              </details>
            ))}
          </div>
        </div>

        {user && <ManagePortalButton getAccessToken={getAccessToken} />}

        <div className="text-center mt-12 text-xs space-x-4" style={{ color: "var(--mf-ink-4)" }}>
          <Link href="/legal/terms" className="hover:text-violet-soft">{t("pricing_legal_terms")}</Link>
          <Link href="/legal/privacy" className="hover:text-violet-soft">{t("pricing_legal_privacy")}</Link>
        </div>
      </div>
    </main>
  );
}

export default function PricingPageContent() {
  return (
    <Suspense fallback={null}>
      <PricingContent />
    </Suspense>
  );
}
