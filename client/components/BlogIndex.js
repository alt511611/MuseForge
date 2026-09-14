/**
 * The guides index. Server component — see the note in ArticleBody.
 */

import Link from "next/link";
import { ArrowRight, Clock } from "lucide-react";
import { withLocale } from "../lib/i18n/routing";

export default function BlogIndex({ locale, heading, tagline, intro, cards, labels = {}, notice, breadcrumbs }) {
  return (
    <main className="min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
      <div className="relative overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: "radial-gradient(ellipse 60% 40% at 50% 0%, rgba(139,92,246,0.13) 0%, transparent 70%)" }}
        />
        {breadcrumbs && <div className="relative pt-4">{breadcrumbs}</div>}
        <header className="relative max-w-3xl mx-auto px-6 pt-10 pb-12 text-center">
          <p className="slate-label mb-4" style={{ color: "var(--mf-violet-soft)" }}>{tagline}</p>
          <h1 className="text-4xl md:text-6xl font-black tracking-tight mb-5">
            <span className="gradient-text">{heading}</span>
          </h1>
          <p className="text-lg max-w-2xl mx-auto" style={{ color: "var(--mf-ink-3)" }}>{intro}</p>
        </header>
      </div>

      <div className="max-w-3xl mx-auto px-6 pb-20">
        {notice && (
          <p
            className="rounded-xl px-5 py-3.5 mb-8 text-sm"
            style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line)", color: "var(--mf-ink-3)" }}
          >
            {notice}
          </p>
        )}

        <ul className="space-y-4">
          {cards.map((c) => (
            <li key={c.slug}>
              <Link
                href={withLocale(c.href, c.shownIn)}
                className="glass rounded-2xl p-6 block transition-all hover:border-purple-600/30"
                style={{ border: "1px solid rgba(139,92,246,0.1)" }}
              >
                <div className="flex flex-wrap items-center gap-3 mb-3">
                  <span
                    className="px-2.5 py-1 rounded-lg text-[11px] font-semibold uppercase tracking-wide"
                    style={{ backgroundColor: "rgba(139,92,246,0.15)", color: "var(--mf-violet-soft)" }}
                  >
                    {labels.categories?.[c.category] || c.category}
                  </span>
                  <span className="inline-flex items-center gap-1.5 text-xs" style={{ color: "var(--mf-ink-4)" }}>
                    <Clock size={12} aria-hidden="true" />
                    {(labels.minutes || "{n} min read").replace("{n}", c.minutes)}
                  </span>
                  <time className="text-xs" dateTime={c.published} style={{ color: "var(--mf-ink-4)" }}>
                    {new Intl.DateTimeFormat(c.shownIn, { year: "numeric", month: "short", day: "numeric" }).format(
                      new Date(c.published)
                    )}
                  </time>
                </div>
                <h2 className="text-xl font-bold mb-2 leading-snug" style={{ color: "var(--mf-ink)" }}>{c.title}</h2>
                <p className="text-sm leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>{c.description}</p>
                <span className="inline-flex items-center gap-1.5 text-sm mt-4" style={{ color: "var(--mf-violet-soft)" }}>
                  {labels.read_more || "Read"} <ArrowRight size={13} />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}
