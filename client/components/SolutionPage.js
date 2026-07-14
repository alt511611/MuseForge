"use client";

import Link from "next/link";
import { Check, ArrowRight } from "lucide-react";

/**
 * Shared layout for all /solutions/* segment pages.
 *
 * Props:
 *   icon        — lucide component
 *   accentColor — e.g. "#7c3aed"
 *   badge       — small badge text above heading
 *   heading     — main h1 (can be JSX)
 *   subheading  — paragraph under h1
 *   useCases    — [{icon, title, desc}]
 *   differentiators — [{title, desc}]  (3-4 items)
 *   planCard    — { name, price, period, cta, ctaHref, highlight, credits, features }
 *   ctaBanner   — { title, desc, btnText, btnHref }
 */
export default function SolutionPage({
  icon: HeadlineIcon,
  accentColor = "#7c3aed",
  badge,
  heading,
  subheading,
  useCases = [],
  differentiators = [],
  planCard,
  ctaBanner,
}) {
  return (
    <main className="min-h-screen" style={{ backgroundColor: "#0a0a0f" }}>
      {/* Hero */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 pointer-events-none"
          style={{ background: `radial-gradient(ellipse 60% 40% at 50% 0%, ${accentColor}22 0%, transparent 70%)` }} />
        <div className="relative max-w-4xl mx-auto px-6 pt-20 pb-14 text-center">
          {badge && (
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium mb-6"
              style={{ backgroundColor: `${accentColor}20`, border: `1px solid ${accentColor}40`, color: accentColor }}>
              {HeadlineIcon && <HeadlineIcon size={12} />}
              {badge}
            </div>
          )}
          <h1 className="text-4xl md:text-6xl font-black tracking-tight mb-5 leading-tight">
            {heading}
          </h1>
          <p className="text-lg max-w-2xl mx-auto" style={{ color: "#64748b" }}>{subheading}</p>
        </div>
      </div>

      {/* Use case cards */}
      {useCases.length > 0 && (
        <section className="max-w-5xl mx-auto px-6 py-14">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {useCases.map(({ icon: Icon, title, desc, sample }, i) => (
              <div key={i} className="glass rounded-2xl p-6 group hover:border-purple-600/30 transition-all"
                style={{ border: "1px solid rgba(124,58,237,0.1)" }}>
                <div className="w-10 h-10 rounded-xl flex items-center justify-center mb-4"
                  style={{ backgroundColor: `${accentColor}18` }}>
                  <Icon size={20} style={{ color: accentColor }} />
                </div>
                <h3 className="text-base font-bold mb-2" style={{ color: "#e2e8f0" }}>{title}</h3>
                <p className="text-sm leading-relaxed" style={{ color: "#64748b" }}>{desc}</p>
                {sample && (
                  <div className="mt-4 rounded-xl overflow-hidden aspect-video relative"
                    style={{ backgroundColor: "#12121a", border: "1px solid #22223a" }}>
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                      <div className="w-12 h-12 rounded-full flex items-center justify-center"
                        style={{ backgroundColor: `${accentColor}25`, border: `1px solid ${accentColor}40` }}>
                        <Icon size={20} style={{ color: accentColor }} />
                      </div>
                      <span className="text-xs px-2.5 py-1 rounded-full font-medium"
                        style={{ backgroundColor: `${accentColor}20`, color: accentColor }}>
                        Example Output
                      </span>
                      <p className="text-xs text-center max-w-[180px]" style={{ color: "#475569" }}>{sample}</p>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Differentiators */}
      {differentiators.length > 0 && (
        <section className="max-w-5xl mx-auto px-6 py-8">
          <div className="glass rounded-2xl p-8" style={{ border: "1px solid rgba(124,58,237,0.12)" }}>
            <h2 className="text-2xl font-black mb-6 gradient-text">What makes MuseForge different</h2>
            <div className="space-y-4">
              {differentiators.map(({ title, desc }, i) => (
                <div key={i} className="flex items-start gap-3">
                  <Check size={16} className="mt-1 flex-shrink-0" style={{ color: "#22c55e" }} />
                  <div>
                    <p className="text-sm font-semibold" style={{ color: "#e2e8f0" }}>{title}</p>
                    <p className="text-sm" style={{ color: "#64748b" }}>{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Plan card */}
      {planCard && (
        <section className="max-w-5xl mx-auto px-6 py-10">
          <h2 className="text-xl font-bold mb-5" style={{ color: "#e2e8f0" }}>Recommended plan</h2>
          <div className="glass rounded-2xl p-7 max-w-sm"
            style={{
              border: planCard.highlight ? "1px solid rgba(124,58,237,0.4)" : "1px solid rgba(124,58,237,0.12)",
              boxShadow: planCard.highlight ? "0 0 32px rgba(124,58,237,0.12)" : "none",
            }}>
            <p className="text-xl font-black mb-1" style={{ color: "#e2e8f0" }}>{planCard.name}</p>
            {planCard.credits && (
              <p className="text-xs font-medium mb-3" style={{ color: "#7c3aed" }}>{planCard.credits} credits / mo</p>
            )}
            <div className="mb-4">
              <span className="text-3xl font-black" style={{ color: "#e2e8f0" }}>{planCard.price}</span>
              {planCard.period && <span className="text-sm ml-1" style={{ color: "#64748b" }}>{planCard.period}</span>}
            </div>
            <ul className="space-y-1.5 mb-6">
              {(planCard.features || []).map((f, i) => f && (
                <li key={i} className="flex items-center gap-2 text-sm" style={{ color: "#94a3b8" }}>
                  <Check size={13} style={{ color: "#22c55e", flexShrink: 0 }} /> {f}
                </li>
              ))}
            </ul>
            <Link href={planCard.ctaHref || "/pricing"}
              className="w-full py-2.5 rounded-xl text-sm font-semibold text-center block transition-all"
              style={
                planCard.highlight
                  ? { background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }
                  : { backgroundColor: "#1a1a26", border: "1px solid #22223a", color: "#94a3b8" }
              }>
              {planCard.cta} <ArrowRight size={14} className="inline ml-1" />
            </Link>
          </div>
        </section>
      )}

      {/* CTA banner */}
      {ctaBanner && (
        <section className="max-w-5xl mx-auto px-6 py-10 pb-20">
          <div className="rounded-2xl p-10 text-center"
            style={{ background: "linear-gradient(135deg,rgba(124,58,237,0.15),rgba(109,40,217,0.08))", border: "1px solid rgba(124,58,237,0.2)" }}>
            <h2 className="text-2xl font-black mb-3 gradient-text">{ctaBanner.title}</h2>
            <p className="text-sm mb-6" style={{ color: "#64748b" }}>{ctaBanner.desc}</p>
            <Link href={ctaBanner.btnHref || "/"}
              className="inline-flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold"
              style={{ background: "linear-gradient(135deg,#7c3aed,#6d28d9)", color: "#fff" }}>
              {ctaBanner.btnText}
              <ArrowRight size={14} />
            </Link>
          </div>
        </section>
      )}
    </main>
  );
}
