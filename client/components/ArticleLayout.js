/**
 * Page chrome for one article: header, contents, body, footer links.
 *
 * Server component, like ArticleBody — see the note there. `labels` carries the
 * already-translated chrome strings so this file never imports the server-only
 * dictionary itself.
 */

import Link from "next/link";
import { Clock, CalendarDays, ArrowLeft, ArrowRight } from "lucide-react";
import ArticleBody from "./ArticleBody";
import { tableOfContents } from "../lib/content/blocks";
import { withLocale } from "../lib/i18n/routing";
import { BLOG_PATH } from "../lib/content";

/** Written out in the reader's own language, with the machine-readable form in datetime. */
function PostDate({ iso, locale, icon: Icon, label }) {
  const text = new Intl.DateTimeFormat(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(iso));
  return (
    <span className="inline-flex items-center gap-1.5" title={label}>
      <Icon size={13} aria-hidden="true" />
      <time dateTime={iso}>{text}</time>
    </span>
  );
}

export default function ArticleLayout({ article, related = [], labels = {}, breadcrumbs }) {
  const { locale, title, description, blocks, minutes, published, updated, category, tags } = article;
  const toc = tableOfContents(blocks);
  const changed = updated && updated !== published;

  return (
    <main className="min-h-screen" style={{ backgroundColor: "var(--mf-stage)" }}>
      <div className="relative overflow-hidden">
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: "radial-gradient(ellipse 60% 40% at 50% 0%, rgba(139,92,246,0.13) 0%, transparent 70%)" }}
        />
        {breadcrumbs && <div className="relative pt-4">{breadcrumbs}</div>}

        <header className="relative max-w-3xl mx-auto px-6 pt-8 pb-10">
          {category && (
            <p className="slate-label mb-4" style={{ color: "var(--mf-violet-soft)" }}>
              {labels.categories?.[category] || category}
            </p>
          )}
          <h1 className="text-3xl md:text-5xl font-black tracking-tight leading-[1.08] mb-5" style={{ color: "var(--mf-ink)" }}>
            {title}
          </h1>
          {/* The subtitle repeats the meta description on purpose: it is the
              sentence a search result shows, and a reader who clicked it should
              land on the same sentence rather than wonder if they misread. */}
          <p className="text-lg leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>{description}</p>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 mt-6 text-xs" style={{ color: "var(--mf-ink-4)" }}>
            <PostDate iso={published} locale={locale} icon={CalendarDays} label={labels.published} />
            {changed && (
              <span className="inline-flex items-center gap-1.5">
                {labels.updated || "Updated"}{" "}
                <time dateTime={updated}>
                  {new Intl.DateTimeFormat(locale, { year: "numeric", month: "long", day: "numeric" }).format(new Date(updated))}
                </time>
              </span>
            )}
            <span className="inline-flex items-center gap-1.5">
              <Clock size={13} aria-hidden="true" />
              {(labels.minutes || "{n} min read").replace("{n}", minutes)}
            </span>
          </div>
        </header>
      </div>

      <div className="max-w-3xl mx-auto px-6 pb-16">
        {/* Contents sits above the body rather than in a sticky rail: the rail
            costs a client component and a breakpoint's worth of layout, and on
            an article this length the reader scrolls past it once. */}
        {toc.length > 2 && (
          <nav
            aria-label={labels.contents || "Contents"}
            className="rounded-2xl p-5 mb-12"
            style={{ backgroundColor: "var(--mf-panel)", border: "1px solid var(--mf-line)" }}
          >
            <p className="slate-label mb-3">{labels.contents || "Contents"}</p>
            <ol className="space-y-1.5 text-sm">
              {toc.map(({ id, text }, i) => (
                <li key={id} className="flex gap-2.5">
                  <span style={{ color: "var(--mf-ink-4)" }}>{String(i + 1).padStart(2, "0")}</span>
                  <a href={`#${id}`} className="hover:text-violet-soft transition-colors" style={{ color: "var(--mf-ink-2)" }}>
                    {text}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        )}

        <article>
          <ArticleBody blocks={blocks} locale={locale} labels={labels} />
        </article>

        {tags?.length > 0 && (
          <ul className="flex flex-wrap gap-2 mt-12 pt-8" style={{ borderTop: "1px solid var(--mf-line)" }}>
            {tags.map((tag) => (
              <li
                key={tag}
                className="px-2.5 py-1 rounded-lg text-xs"
                style={{ backgroundColor: "var(--mf-panel-2)", color: "var(--mf-ink-4)" }}
              >
                {tag}
              </li>
            ))}
          </ul>
        )}

        {related.length > 0 && (
          <section className="mt-14">
            <h2 className="text-xl font-black mb-5" style={{ color: "var(--mf-ink)" }}>
              {labels.related || "Keep reading"}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {related.map((r) => (
                <Link
                  key={r.slug}
                  href={withLocale(r.href, locale)}
                  className="glass rounded-2xl p-5 block transition-all hover:border-purple-600/30"
                  style={{ border: "1px solid rgba(139,92,246,0.1)" }}
                >
                  <p className="slate-label mb-2" style={{ color: "var(--mf-violet-soft)" }}>
                    {labels.categories?.[r.category] || r.category}
                  </p>
                  <p className="font-bold text-sm mb-1.5" style={{ color: "var(--mf-ink)" }}>{r.title}</p>
                  <p className="text-xs leading-relaxed line-clamp-2" style={{ color: "var(--mf-ink-3)" }}>
                    {r.description}
                  </p>
                  <span className="inline-flex items-center gap-1 text-xs mt-3" style={{ color: "var(--mf-violet-soft)" }}>
                    {labels.read_more || "Read"} <ArrowRight size={12} />
                  </span>
                </Link>
              ))}
            </div>
          </section>
        )}

        <Link
          href={withLocale(BLOG_PATH, locale)}
          className="inline-flex items-center gap-2 text-sm mt-12"
          style={{ color: "var(--mf-ink-3)" }}
        >
          <ArrowLeft size={14} />
          {labels.all_articles || "All guides"}
        </Link>
      </div>
    </main>
  );
}
