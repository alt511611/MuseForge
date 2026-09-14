/**
 * Renders an article body from its blocks.
 *
 * SERVER COMPONENT ON PURPOSE. Everything here has to be in the HTML that
 * arrives before any JavaScript runs: that is what Googlebot indexes cheaply,
 * and it is the only thing most answer-engine crawlers read at all. The one
 * interactive affordance -- collapsing an FAQ entry -- is <details>/<summary>,
 * which needs no client bundle and keeps the answer text in the document even
 * while collapsed.
 *
 * Block semantics live in lib/content/blocks.js; this file is only their
 * appearance.
 */

import Link from "next/link";
import { ArrowRight, Check, Info, Lightbulb, AlertTriangle } from "lucide-react";
import { inline } from "../lib/content/inline";
import { slugifyHeading } from "../lib/content/blocks";
import { withLocale } from "../lib/i18n/routing";

const CALLOUT = {
  note: { Icon: Info, color: "var(--mf-violet-soft)" },
  tip: { Icon: Lightbulb, color: "var(--mf-gold)" },
  warn: { Icon: AlertTriangle, color: "var(--mf-gold-soft)" },
};

function Heading({ block, level }) {
  const Tag = level === 2 ? "h2" : "h3";
  const id = block.id || slugifyHeading(block.text);
  return (
    <Tag
      id={id}
      className={
        level === 2
          ? "scroll-mt-24 text-2xl md:text-3xl font-black tracking-tight mt-14 mb-4"
          : "scroll-mt-24 text-lg font-bold mt-9 mb-3"
      }
      style={{ color: "var(--mf-ink)" }}
    >
      {/* The anchor is a real link so a reader can cite a section, and so an
          answer engine that quotes one can link back to the exact passage. */}
      <a href={`#${id}`} className="group no-underline">
        {block.text}
        <span
          aria-hidden="true"
          className="opacity-0 group-hover:opacity-60 transition-opacity ml-2 text-base font-normal"
          style={{ color: "var(--mf-violet)" }}
        >
          #
        </span>
      </a>
    </Tag>
  );
}

export default function ArticleBody({ blocks = [], locale, labels = {} }) {
  const md = (text) => inline(text, locale);

  return (
    <div className="text-[15px] leading-[1.75]" style={{ color: "var(--mf-ink-2)" }}>
      {blocks.map((b, i) => {
        switch (b.t) {
          /* The answer-first summary. `data-speakable` marks it for the
             SpeakableSpecification in the page's JSON-LD: if something is going
             to quote one passage of this article, it should be this one. */
          case "tldr":
            return (
              <aside
                key={i}
                data-speakable
                className="glass rounded-2xl p-6 mb-10"
                style={{ border: "1px solid rgba(139,92,246,0.22)" }}
              >
                <p className="slate-label mb-3">{labels.tldr || "The short answer"}</p>
                <ul className="space-y-2">
                  {b.items.map((it, j) => (
                    <li key={j} className="flex items-start gap-2.5 text-[15px]">
                      <Check size={15} className="mt-1 flex-shrink-0" style={{ color: "var(--mf-ok)" }} />
                      <span style={{ color: "var(--mf-ink-2)" }}>{md(it)}</span>
                    </li>
                  ))}
                </ul>
              </aside>
            );

          case "h2":
            return <Heading key={i} block={b} level={2} />;
          case "h3":
            return <Heading key={i} block={b} level={3} />;

          case "p":
            return (
              <p key={i} className="my-4">
                {md(b.text)}
              </p>
            );

          case "ul":
            return (
              <ul key={i} className="my-5 space-y-2.5">
                {b.items.map((it, j) => (
                  <li key={j} className="flex items-start gap-2.5">
                    <span
                      aria-hidden="true"
                      className="mt-2.5 w-1.5 h-1.5 rounded-full flex-shrink-0"
                      style={{ backgroundColor: "var(--mf-violet)" }}
                    />
                    <span>{md(it)}</span>
                  </li>
                ))}
              </ul>
            );

          case "ol":
            return (
              <ol key={i} className="my-5 space-y-2.5 list-decimal pl-5 marker:text-violet marker:font-bold">
                {b.items.map((it, j) => (
                  <li key={j} className="pl-1.5">{md(it)}</li>
                ))}
              </ol>
            );

          /* A definition table. Short term/value pairs are the shape an answer
             engine reproduces most faithfully — it can lift one row and still
             be correct, which is not true of a paragraph. */
          case "keyfacts":
            return (
              <dl
                key={i}
                data-speakable
                className="my-8 rounded-2xl overflow-hidden"
                style={{ border: "1px solid var(--mf-line-strong)" }}
              >
                {b.items.map(({ term, value }, j) => (
                  <div
                    key={j}
                    className="grid grid-cols-1 sm:grid-cols-[minmax(0,10rem)_1fr] gap-1 sm:gap-4 px-5 py-3.5"
                    style={{
                      borderTop: j ? "1px solid var(--mf-line)" : "none",
                      backgroundColor: j % 2 ? "transparent" : "var(--mf-panel)",
                    }}
                  >
                    <dt className="text-xs font-semibold uppercase tracking-wide pt-0.5" style={{ color: "var(--mf-ink-4)" }}>
                      {md(term)}
                    </dt>
                    <dd style={{ color: "var(--mf-ink-2)" }}>{md(value)}</dd>
                  </div>
                ))}
              </dl>
            );

          case "steps":
            return (
              <section key={i} className="my-9">
                <ol className="space-y-4">
                  {b.items.map(({ name, text }, j) => (
                    <li
                      key={j}
                      id={slugifyHeading(name)}
                      className="scroll-mt-24 glass rounded-2xl p-5 flex items-start gap-4"
                      style={{ border: "1px solid rgba(139,92,246,0.12)" }}
                    >
                      <span
                        aria-hidden="true"
                        className="w-7 h-7 rounded-lg flex items-center justify-center text-xs font-black flex-shrink-0"
                        style={{ backgroundColor: "rgba(139,92,246,0.18)", color: "var(--mf-violet-soft)" }}
                      >
                        {j + 1}
                      </span>
                      <div>
                        <p className="font-bold mb-1.5" style={{ color: "var(--mf-ink)" }}>{md(name)}</p>
                        <p className="text-sm leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>{md(text)}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
            );

          case "faq":
            return (
              <section key={i} className="my-10">
                <div className="space-y-2.5">
                  {b.items.map(({ q, a }, j) => (
                    <details
                      key={j}
                      /* Open by default: a collapsed answer is still in the DOM,
                         but a reader who arrived from a search for that exact
                         question should not have to click to see it. */
                      open
                      className="glass rounded-xl px-5 py-4"
                      style={{ border: "1px solid rgba(139,92,246,0.12)" }}
                    >
                      <summary
                        className="font-semibold cursor-pointer marker:hidden list-none"
                        style={{ color: "var(--mf-ink)" }}
                      >
                        {md(q)}
                      </summary>
                      <p className="mt-2.5 text-sm leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>
                        {md(a)}
                      </p>
                    </details>
                  ))}
                </div>
              </section>
            );

          case "table":
            return (
              <figure key={i} className="my-8">
                <div className="overflow-x-auto rounded-2xl" style={{ border: "1px solid var(--mf-line-strong)" }}>
                  <table className="w-full text-sm border-collapse min-w-[34rem]">
                    <thead>
                      <tr style={{ backgroundColor: "var(--mf-panel)" }}>
                        {b.head.map((h, j) => (
                          <th
                            key={j}
                            scope="col"
                            className="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wide"
                            style={{ color: "var(--mf-ink-4)" }}
                          >
                            {md(h)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {b.rows.map((row, j) => (
                        <tr key={j} style={{ borderTop: "1px solid var(--mf-line)" }}>
                          {row.map((cell, k) => (
                            <td
                              key={k}
                              className={k === 0 ? "px-4 py-3 font-medium" : "px-4 py-3"}
                              style={{ color: k === 0 ? "var(--mf-ink)" : "var(--mf-ink-3)" }}
                            >
                              {md(cell)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {b.caption && (
                  <figcaption className="mt-2.5 text-xs" style={{ color: "var(--mf-ink-4)" }}>
                    {md(b.caption)}
                  </figcaption>
                )}
              </figure>
            );

          case "callout": {
            const { Icon, color } = CALLOUT[b.tone] || CALLOUT.note;
            return (
              <aside
                key={i}
                className="my-7 rounded-2xl p-5 flex items-start gap-3.5"
                style={{ backgroundColor: "var(--mf-panel)", borderLeft: `3px solid ${color}` }}
              >
                <Icon size={17} className="mt-0.5 flex-shrink-0" style={{ color }} />
                <div>
                  {b.title && (
                    <p className="font-semibold mb-1 text-sm" style={{ color: "var(--mf-ink)" }}>{b.title}</p>
                  )}
                  <p className="text-sm leading-relaxed" style={{ color: "var(--mf-ink-3)" }}>{md(b.text)}</p>
                </div>
              </aside>
            );
          }

          case "quote":
            return (
              <blockquote
                key={i}
                className="my-8 pl-5 italic text-lg leading-relaxed"
                style={{ borderLeft: "3px solid var(--mf-violet)", color: "var(--mf-ink-2)" }}
              >
                {md(b.text)}
                {b.cite && (
                  <footer className="mt-2 text-xs not-italic" style={{ color: "var(--mf-ink-4)" }}>
                    — {md(b.cite)}
                  </footer>
                )}
              </blockquote>
            );

          case "cta":
            return (
              <aside
                key={i}
                className="my-10 rounded-2xl p-7 text-center"
                style={{
                  background: "linear-gradient(135deg,rgba(139,92,246,0.15),rgba(109,40,217,0.08))",
                  border: "1px solid rgba(139,92,246,0.2)",
                }}
              >
                <p className="text-xl font-black mb-2 gradient-text">{b.title}</p>
                <p className="text-sm mb-5" style={{ color: "var(--mf-ink-3)" }}>{md(b.text)}</p>
                <Link
                  href={withLocale(b.href || "/", locale)}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold"
                  style={{ background: "linear-gradient(135deg,var(--mf-violet),var(--mf-violet-deep))", color: "#fff" }}
                >
                  {b.button}
                  <ArrowRight size={14} />
                </Link>
              </aside>
            );

          default:
            return null;
        }
      })}
    </div>
  );
}
