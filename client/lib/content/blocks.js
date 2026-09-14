/**
 * The block vocabulary an article body is written in, and the two things the
 * rest of the system reads off it: a table of contents, and structured data.
 *
 * WHY BLOCKS RATHER THAN MARKDOWN. Google will only show a rich result when
 * the JSON-LD matches text that is visible on the page, and the usual way a
 * site breaks that rule is by maintaining the two separately: someone edits the
 * FAQ copy and forgets the schema, and the page quietly loses eligibility. Here
 * a `faq` block IS the FAQPage markup and the rendered accordion, read twice
 * from one source. The same holds for `steps` -> HowTo. Drift is not possible.
 *
 * The second reason is the answer engines. ChatGPT and Gemini quote passages,
 * not pages, and what they quote well is a short self-contained answer sitting
 * under the question it answers. `tldr`, `keyfacts`, `faq` and `steps` exist to
 * make an article mostly composed of such passages.
 *
 * Block types
 *   { t: "tldr",     items: [string] }                       answer-first summary
 *   { t: "h2"|"h3",  text }                                  heading (id derived)
 *   { t: "p",        text }                                  paragraph
 *   { t: "ul"|"ol",  items: [string] }                       list
 *   { t: "keyfacts", items: [{ term, value }] }              definition table
 *   { t: "steps",    name, description?, totalTime?,
 *                    items: [{ name, text }] }               -> HowTo
 *   { t: "faq",      items: [{ q, a }] }                     -> FAQPage
 *   { t: "table",    caption?, head: [string],
 *                    rows: [[string]] }                      comparison grid
 *   { t: "callout",  tone?: "note"|"warn"|"tip", title?, text }
 *   { t: "quote",    text, cite? }
 *   { t: "cta",      title, text, button, href }
 */

import { plain } from "./inline";

/** Stable, readable anchor for a heading. Diacritics fold; everything else goes. */
export function slugifyHeading(text) {
  return plain(text)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 60);
}

/**
 * Heading ids, made unique in document order.
 *
 * Two sections legitimately called "Cost" would otherwise share an anchor and
 * the second one would be unreachable, so a counter disambiguates.
 */
export function withHeadingIds(blocks = []) {
  const seen = new Map();
  return blocks.map((b) => {
    if (b.t !== "h2" && b.t !== "h3") return b;
    const base = slugifyHeading(b.text) || "section";
    const n = (seen.get(base) ?? 0) + 1;
    seen.set(base, n);
    return { ...b, id: n === 1 ? base : `${base}-${n}` };
  });
}

/** h2s only: an in-page contents list that nests three levels helps nobody. */
export function tableOfContents(blocks = []) {
  return withHeadingIds(blocks)
    .filter((b) => b.t === "h2")
    .map(({ id, text }) => ({ id, text: plain(text) }));
}

/**
 * Word count over the text-bearing blocks, turned into minutes at 220 wpm.
 * Tables and key-fact rows are scanned, not read, so they are left out.
 */
export function readingMinutes(blocks = []) {
  let words = 0;
  const add = (s) => { words += plain(s).split(/\s+/).filter(Boolean).length; };

  for (const b of blocks) {
    switch (b.t) {
      case "p": case "h2": case "h3": case "quote": add(b.text); break;
      case "ul": case "ol": case "tldr": (b.items || []).forEach(add); break;
      case "steps": (b.items || []).forEach((i) => { add(i.name); add(i.text); }); break;
      case "faq": (b.items || []).forEach((i) => { add(i.q); add(i.a); }); break;
      case "callout": add(b.text); break;
      default: break;
    }
  }
  return Math.max(1, Math.round(words / 220));
}

/** Every `faq` block's items, flattened — one FAQPage node per article, not per block. */
export function faqItems(blocks = []) {
  return blocks
    .filter((b) => b.t === "faq")
    .flatMap((b) => b.items || [])
    .map(({ q, a }) => ({ q: plain(q), a: plain(a) }));
}

/** Every `steps` block, as HowTo-shaped input. */
export function howToBlocks(blocks = []) {
  return blocks
    .filter((b) => b.t === "steps" && (b.items || []).length)
    .map((b) => ({
      name: plain(b.name),
      description: b.description ? plain(b.description) : undefined,
      totalTime: b.totalTime,
      steps: b.items.map((i) => ({ name: plain(i.name), text: plain(i.text) })),
    }));
}

/**
 * The passage an answer engine should lift if it only lifts one.
 *
 * The tldr block if the article has one, otherwise the first paragraph. Fed to
 * `speakable` and used as the meta description fallback.
 */
export function leadSummary(blocks = []) {
  const tldr = blocks.find((b) => b.t === "tldr");
  if (tldr) return (tldr.items || []).map(plain).join(" ");
  const p = blocks.find((b) => b.t === "p");
  return p ? plain(p.text) : "";
}
