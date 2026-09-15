/**
 * The marketing pages, as block documents.
 *
 * WHY. /llms.txt and the /md editions made the GUIDES cheap for a language
 * model to read, and left the three pages an assistant is actually asked about
 * — "what is MuseForge", "what does it cost", "who is it for" — available only
 * as rendered HTML. A model answering those questions was parsing a React page
 * and spending most of its context on navigation, a cookie banner and class
 * names. These documents are the same pages without any of that.
 *
 * WHERE THE WORDS COME FROM. Nothing here is retyped. The home page and
 * /pricing read the locale dictionaries — the same `t(locale, key)` calls the
 * components render, so the Markdown edition of /tr is Turkish and says what
 * the Turkish page says. The four segment pages read their `content.js`, which
 * is the object their page.js renders from. Prices come from `PLAN_OFFERS`,
 * the same constant the pricing page's JSON-LD is built from and that
 * `test_pricing_coherence` pins against what Stripe actually charges.
 *
 * That constraint is the whole design. A plain-text edition assembled from its
 * own copy of the copy is not a machine-readable version of the page, it is a
 * second page that search engines and assistants are shown instead — which is
 * cloaking, and it is also simply how the numbers end up disagreeing.
 */

import { t } from "../i18n/index";
import { DEFAULT_LOCALE, LOCALE_CODES } from "../i18n/routing";
import { blocksToMarkdown } from "./markdown";
import { PLAN_OFFERS } from "../pricing";
import { CONTENT as AGENCIES } from "../../app/[locale]/solutions/agencies/content";
import { CONTENT as CREATORS } from "../../app/[locale]/solutions/creators/content";
import { CONTENT as EDUCATION } from "../../app/[locale]/solutions/education/content";
import { CONTENT as FILMMAKERS } from "../../app/[locale]/solutions/filmmakers/content";

const SEGMENTS = {
  agencies: AGENCIES,
  creators: CREATORS,
  education: EDUCATION,
  filmmakers: FILMMAKERS,
};

export const SEGMENT_KEYS = Object.keys(SEGMENTS).sort();

/** The numbered key families the pages render, as `t()` reads them. */
const numbered = (locale, prefix, count, fields) =>
  Array.from({ length: count }, (_, i) =>
    Object.fromEntries(
      Object.entries(fields).map(([out, suffix]) => [
        out,
        t(locale, `${prefix}_${i + 1}_${suffix}`),
      ])
    )
  );

/* ── Home ─────────────────────────────────────────────────────────────────── */

function homeDoc(locale) {
  const steps = numbered(locale, "how", 4, { name: "title", text: "desc" });
  const features = numbered(locale, "feat", 4, { term: "title", value: "desc" });
  const faq = numbered(locale, "faq", 4, { q: "q", a: "a" });

  return {
    path: "/",
    title: `MuseForge — ${t(locale, "hero_sub")}`,
    description: t(locale, "hero_desc"),
    /* No opening paragraph repeating hero_desc: it is already the document's
       description, two lines above, and a model reading this twice learns
       nothing the second time. */
    blocks: [
      { t: "h2", text: t(locale, "how_title") },
      /* `ol`, not `steps`. A `steps` block is the HowTo vocabulary, and the
         home page deliberately emits no HowTo: steps two and three are things
         the pipeline does, not things the reader performs, and seo.js is
         explicit that a HowTo whose steps are really a feature list is the
         fastest route to a structured-data manual action. An ordered list is
         what the page actually shows. */
      {
        t: "ol",
        items: steps.map((s) => `**${s.name}** — ${s.text}`),
      },
      { t: "h2", text: t(locale, "sec_different") },
      { t: "keyfacts", items: features },
      { t: "h2", text: t(locale, "faq_title") },
      { t: "faq", items: faq },
    ],
  };
}

/* ── Pricing ──────────────────────────────────────────────────────────────── */

function pricingDoc(locale) {
  const faq = numbered(locale, "pricing_faq", 4, { q: "q", a: "a" });

  return {
    path: "/pricing",
    title: `${t(locale, "nav_pricing")} — MuseForge`,
    description: t(locale, "pricing_sub"),
    blocks: [
      { t: "h2", text: t(locale, "nav_pricing") },
      /* The offer table stays English at every locale, and that is a
         limitation rather than a decision to be proud of. PLAN_OFFERS is the
         JSON-LD mirror: five rows splitting each plan into annual and monthly,
         where the dictionary has three plans and no split, so the two cannot
         be joined without inventing a mapping. The PRICES -- the part a wrong
         answer actually costs somebody -- are identical to the page in every
         language, and they are what `test_pricing_coherence` pins. Translating
         the blurbs would mean a new copy of them in twenty dictionaries with
         nothing checking it, which is the trade that makes this the better
         end. */
      {
        t: "table",
        head: ["Plan", "USD / month", "What it includes"],
        rows: PLAN_OFFERS.map((p) => [p.name, `$${p.price}`, p.desc]),
      },
      { t: "h2", text: t(locale, "faq_title") },
      { t: "faq", items: faq },
    ],
  };
}

/* ── Solutions ────────────────────────────────────────────────────────────── */

function segmentDoc(segment) {
  const c = SEGMENTS[segment];
  if (!c) return null;

  return {
    path: `/solutions/${segment}`,
    /* The page's VISIBLE h1, not `c.title`. `c.title` is the <title> tag, which
       is written for a search result and differs from the heading on the page
       ("AI Video for Schools & Universities" against "AI Video for Classrooms &
       Campuses"). A plain-text edition whose h1 is not the page's h1 is saying
       something the page does not, which is the one thing these documents are
       not allowed to do. */
    title: c.headingText,
    description: c.description,
    /* English at every locale, because the pages are. See the note in each
       content.js: these four were written in English and never translated, and
       a Markdown edition that invented translations would be saying something
       the page does not. */
    forcedLocale: DEFAULT_LOCALE,
    blocks: [
      { t: "p", text: c.subheading },
      { t: "h2", text: "Use cases" },
      ...c.useCases.flatMap((u) => [
        { t: "h3", text: u.title },
        { t: "p", text: u.desc },
        ...(u.sample ? [{ t: "callout", title: "Example", text: u.sample }] : []),
      ]),
      { t: "h2", text: "What makes it different" },
      {
        t: "keyfacts",
        items: c.differentiators.map((d) => ({ term: d.title, value: d.desc })),
      },
      { t: "h2", text: "Plan" },
      {
        t: "keyfacts",
        items: [
          { term: "Plan", value: c.planCard.name },
          { term: "Price", value: `${c.planCard.price}${c.planCard.period || ""}` },
          ...(c.planCard.credits
            ? [{ term: "Credits", value: `${c.planCard.credits} per month` }]
            : []),
          { term: "Includes", value: c.planCard.features.join(", ") },
        ],
      },
    ],
  };
}

/* ── The registry ─────────────────────────────────────────────────────────── */

/**
 * One page document, or null when nothing lives at that key.
 *
 * @param {string} key      "home" | "pricing" | a segment name
 * @param {string} locale
 */
export function pageDoc(key, locale) {
  if (!LOCALE_CODES.includes(locale)) return null;
  if (key === "home") return homeDoc(locale);
  if (key === "pricing") return pricingDoc(locale);
  return segmentDoc(key);
}

/** Every page that has a Markdown edition, for llms.txt and the sitemap. */
export const PAGE_KEYS = ["home", "pricing", ...SEGMENT_KEYS];

/** Site-relative path of a page's Markdown edition. */
export function mdPath(key, locale) {
  const doc = pageDoc(key, locale);
  if (!doc) return null;
  const code = doc.forcedLocale || locale;
  return doc.path === "/" ? `/md/${code}` : `/md/${code}${doc.path}`;
}

/** One page as a standalone Markdown document, front matter included. */
export function pageToMarkdown(doc, url, labels = {}) {
  const head = [
    `# ${doc.title}`,
    "",
    `> ${doc.description}`,
    "",
    `Source: ${url}`,
  ].join("\n");
  return `${head}\n\n${blocksToMarkdown(doc.blocks, labels)}\n`;
}
