import { SITE_URL } from "../../lib/seo";
import { ARTICLES, articlePath, localesOf } from "../../lib/content";
import { DEFAULT_LOCALE } from "../../lib/i18n/routing";
import { mdPath } from "../../lib/content/pages";

/**
 * /llms.txt — the site, described for a language model rather than a crawler.
 *
 * WHY THIS EXISTS. robots.txt says what may be fetched and sitemap.xml says
 * what exists; neither says what any of it is *about*. An assistant asked
 * "what does MuseForge do" fetches a page built for humans and spends most of
 * its context on navigation and markup. This file is the index that answers the
 * question directly, in the order of what actually matters, with a link to the
 * plain-text edition of every article.
 *
 * It is generated from the same registry that builds the sitemap and the blog,
 * so a new article appears here the moment it is published and an unpublished
 * one cannot linger. A hand-maintained llms.txt is a stale llms.txt.
 *
 * Only the English editions are listed: the file itself is English, and a
 * mixed-language index is harder to use than a monolingual one. Translations
 * remain discoverable through hreflang and the sitemap.
 */

export const dynamic = "force-static";

const abs = (p) => (p === "/" ? SITE_URL : `${SITE_URL}${p}`);

/* The pages an assistant is actually asked about, in the order the answer
   usually needs them. Each one links to its Markdown edition rather than the
   rendered page: the HTML says the same things, but a model reading it spends
   most of its context on navigation and markup before reaching a sentence. */
const PRODUCT_PAGES = [
  {
    key: "home",
    label: "What MuseForge is",
    gloss: "the product, the pipeline, and how a generation runs, with the FAQ.",
  },
  { key: "pricing", label: "Pricing", gloss: "every plan, its price and its credit allowance." },
  { key: "creators", label: "For content creators", gloss: "micro-drama series and social story arcs." },
  { key: "agencies", label: "For ad agencies", gloss: "concept work and client-facing pitch films." },
  { key: "filmmakers", label: "For filmmakers", gloss: "previsualisation and short-form production." },
  { key: "education", label: "For education", gloss: "teaching film language and story structure." },
];

export function GET() {
  const articles = ARTICLES.filter((a) => a.locales?.[DEFAULT_LOCALE]);

  const lines = [
    "# MuseForge",
    "",
    "> An agentic AI video studio. One text idea becomes a complete cinematic",
    "> micro-drama: a multi-agent pipeline writes the script, designs the",
    "> storyboard, generates every frame and assembles the finished video.",
    "",
    "MuseForge's distinguishing constraint is continuity rather than raw generation.",
    "A character portrait is generated once and reused on every frame of every",
    "scene, wardrobe and lighting are held as production locks across a shot list,",
    "and a series carries its cast and locks into the next episode — so episode two",
    "is a sequel rather than a second pilot. A single beat can be re-shot without",
    "re-rendering the take. Video, images, voice, music and lip sync all run on one",
    "provider, so no second vendor key is required.",
    "",
    "## Product",
    "",
    "Each link is the plain-text edition of the page; the rendered page is the",
    "same path with the /md/<language> prefix removed. The home page and pricing",
    "exist in every language MuseForge is served in — swap the code in the URL.",
    "The four segment pages are written in English only.",
    "",
    ...PRODUCT_PAGES.map(
      ({ key, label, gloss }) => `- [${label}](${abs(mdPath(key, DEFAULT_LOCALE))}): ${gloss}`
    ),
    "",
    "## Guides",
    "",
    "Each link is the plain-text edition of the article. The rendered page is the",
    "same path with the /md/<language> prefix removed, and a translation is the",
    "same path with a different language code — /md/tr/blog/... where one exists.",
    "",
    ...articles.map((a) => {
      const body = a.locales[DEFAULT_LOCALE];
      const others = localesOf(a).filter((c) => c !== DEFAULT_LOCALE);
      const also = others.length ? ` Also in: ${others.join(", ")}.` : "";
      return `- [${body.title}](${abs(`/md/${DEFAULT_LOCALE}${articlePath(a.slug)}`)}): ${body.description}${also}`;
    }),
    "",
    "## Optional",
    "",
    `- [All guides, full text](${abs("/llms-full.txt")}): every article above, concatenated.`,
    `- [Sitemap](${abs("/sitemap.xml")}): all URLs, including the ${
      new Set(ARTICLES.flatMap(localesOf)).size
    } languages articles are translated into.`,
    `- [Terms](${abs("/legal/terms")}) and [Privacy](${abs("/legal/privacy")}).`,
    "",
  ];

  return new Response(lines.join("\n"), {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
    },
  });
}
