/**
 * Shared SEO helpers — canonical URLs and JSON-LD structured data.
 *
 * Everything here runs on the server (no "use client"), so the resulting
 * markup is present in the initial HTML that crawlers read.
 */

import {
  LOCALE_CODES,
  DEFAULT_LOCALE,
  withLocale,
  ogLocale,
} from "./i18n/routing";

/* The fallback is the REAL production origin, not a placeholder.
   It used to be museforge.ai -- a different, parked domain -- and because
   NEXT_PUBLIC_SITE_URL was unset on the host, every canonical tag, every
   hreflang annotation and all 169 sitemap entries pointed at it. Google was
   being told, on every page, that the real copy lived somewhere else; the
   somewhere else was an empty page, so nothing on this site was indexed.
   A fallback that is wrong in production is not a fallback. */
export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://www.museforge.studio"
).replace(/\/$/, "");

export const SITE_NAME = "MuseForge";

/** Absolute URL for a site-relative path. */
export function absoluteUrl(path = "/") {
  return path === "/" ? SITE_URL : `${SITE_URL}${path}`;
}

/**
 * `alternates` block for a localized page.
 *
 * Emits the self-referencing canonical plus a full hreflang cluster: every
 * locale points at every other locale, which is what Google requires before it
 * will treat the set as translations of one page rather than duplicates.
 * `x-default` points at the unprefixed English URL.
 *
 * @param {string} path    unprefixed route, e.g. "/pricing"
 * @param {string} locale  the locale this page is being rendered for
 */
export function canonical(path = "/", locale = DEFAULT_LOCALE, available = LOCALE_CODES) {
  /* `available` narrows the cluster for pages that do not exist in every
     language -- an article written in English and Turkish must not advertise
     eighteen hreflang targets that 404. x-default stays on the English URL,
     which every such page has by construction. */
  const codes = available.length ? available : LOCALE_CODES;
  const languages = Object.fromEntries(
    codes.map((code) => [code, withLocale(path, code)])
  );
  return {
    canonical: withLocale(path, locale),
    languages: { ...languages, "x-default": path },
  };
}

/**
 * openGraph block for a localized page.
 *
 * A page-level `openGraph` replaces the layout's wholesale rather than merging
 * into it, so og:locale and og:locale:alternate have to be restated here or
 * every page below the root would lose them.
 */
export function openGraphFor({
  title,
  description,
  path = "/",
  locale = DEFAULT_LOCALE,
  type = "website",
  available = LOCALE_CODES,
  article,
}) {
  const codes = available.length ? available : LOCALE_CODES;
  return {
    type,
    siteName: SITE_NAME,
    title,
    description,
    url: withLocale(path, locale),
    locale: ogLocale(locale),
    alternateLocale: codes.filter((c) => c !== locale).map(ogLocale),
    /* og:article:* is only meaningful when type is "article"; Facebook ignores
       the keys otherwise but validators complain about them. */
    ...(type === "article" && article ? article : {}),
  };
}

/* ── JSON-LD builders ──────────────────────────────────────────────────── */

/**
 * The profiles that are the SAME entity as this organization.
 *
 * `sameAs` is not a link list and it is not marketing. It is the claim "the
 * thing at this URL and the thing at that URL are one organization", and it is
 * how a search engine or an assistant corroborates that MuseForge is a real
 * entity rather than one unverifiable website asserting things about itself.
 * One entry, as this has, is about as thin as that claim gets.
 *
 * THE RULE FOR ADDING ONE: the URL must resolve to a profile that is actually
 * MuseForge's, and that profile should link back here. Nothing else. A
 * plausible-looking URL for a profile that does not exist is worse than an
 * absent one — it either gets ignored, or it binds this organization to
 * whoever really holds that handle, and the second outcome is not something
 * you notice from inside your own site.
 *
 * Likely candidates when they exist, strongest first: the LinkedIn company
 * page, a GitHub organization, the YouTube channel, Crunchbase, Product Hunt.
 */
const PROFILES = [
  "https://twitter.com/museforge_ai",
];

export function organizationSchema() {
  return {
    "@type": "Organization",
    "@id": `${SITE_URL}/#organization`,
    name: SITE_NAME,
    url: SITE_URL,
    logo: {
      "@type": "ImageObject",
      url: absoluteUrl("/icon-512.png"),
      width: 512,
      height: 512,
    },
    description:
      "MuseForge is an agentic AI video studio that turns a single text idea into a complete cinematic micro-drama.",
    sameAs: PROFILES,
  };
}

/* @id values stay locale-independent on purpose: /tr and / describe the same
   organization and the same product, just in different languages. */
export function websiteSchema(locale = DEFAULT_LOCALE) {
  return {
    "@type": "WebSite",
    "@id": `${SITE_URL}/#website`,
    url: SITE_URL,
    name: SITE_NAME,
    publisher: { "@id": `${SITE_URL}/#organization` },
    inLanguage: LOCALE_CODES.includes(locale) ? locale : DEFAULT_LOCALE,
  };
}

export function softwareApplicationSchema(locale = DEFAULT_LOCALE) {
  return {
    inLanguage: LOCALE_CODES.includes(locale) ? locale : DEFAULT_LOCALE,
    "@type": "SoftwareApplication",
    "@id": `${SITE_URL}/#software`,
    name: SITE_NAME,
    url: SITE_URL,
    applicationCategory: "MultimediaApplication",
    applicationSubCategory: "AI Video Generation",
    operatingSystem: "Web browser",
    description:
      "Turn a text idea into a cinematic micro-drama. MuseForge's multi-agent AI pipeline writes the script, designs the storyboard, generates every frame, and assembles the final video.",
    featureList: [
      "Text to video generation",
      "Character consistency lock across scenes",
      "Six cinematic director style presets",
      "Live storyboard preview",
      "In-browser player and download",
    ],
    publisher: { "@id": `${SITE_URL}/#organization` },
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
      description: "Free plan with demo mode — no API key required.",
      url: absoluteUrl("/pricing"),
    },
  };
}

export function faqSchema(items) {
  return {
    "@type": "FAQPage",
    mainEntity: items.map(({ q, a }) => ({
      "@type": "Question",
      name: q,
      acceptedAnswer: { "@type": "Answer", text: a },
    })),
  };
}

export function breadcrumbSchema(trail) {
  return {
    "@type": "BreadcrumbList",
    itemListElement: trail.map(({ name, path }, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name,
      item: absoluteUrl(path),
    })),
  };
}

/**
 * Renders one `@graph` script tag. Passing every node for a page in a single
 * graph lets the nodes cross-reference each other by @id.
 */
export function JsonLd({ graph }) {
  const payload = { "@context": "https://schema.org", "@graph": graph };
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(payload) }}
    />
  );
}

/* ── Editorial schema ──────────────────────────────────────────────────── */

/**
 * The Blog node every article hangs off.
 *
 * One @id for the collection across all locales, matching how @id is handled
 * for the organization and the product above: /tr/blog is the Turkish view of
 * the same publication, not a second one.
 */
export function blogSchema(locale = DEFAULT_LOCALE) {
  return {
    "@type": "Blog",
    "@id": `${SITE_URL}/blog/#blog`,
    url: absoluteUrl(withLocale("/blog", locale)),
    name: `${SITE_NAME} Guides`,
    description:
      "Practical guides to AI filmmaking: character consistency, prompting, shot design, and shipping a series.",
    publisher: { "@id": `${SITE_URL}/#organization` },
    inLanguage: LOCALE_CODES.includes(locale) ? locale : DEFAULT_LOCALE,
  };
}

/**
 * BlogPosting for one article.
 *
 * `headline` is capped at 110 characters because Google drops the rich result
 * above that rather than truncating it. `speakable` points at the summary and
 * the h1 — the two selectors on the page that answer the query on their own,
 * which is also what an answer engine lifts when it quotes the article.
 */
export function articleSchema({
  path,
  locale = DEFAULT_LOCALE,
  headline,
  description,
  published,
  updated,
  section,
  keywords = [],
  wordCount,
  summary,
}) {
  const url = absoluteUrl(withLocale(path, locale));
  return {
    "@type": "BlogPosting",
    "@id": `${url}#article`,
    isPartOf: { "@id": `${SITE_URL}/blog/#blog` },
    mainEntityOfPage: { "@type": "WebPage", "@id": url },
    url,
    headline: String(headline).slice(0, 110),
    description,
    abstract: summary || description,
    datePublished: published,
    dateModified: updated || published,
    inLanguage: LOCALE_CODES.includes(locale) ? locale : DEFAULT_LOCALE,
    author: { "@id": `${SITE_URL}/#organization` },
    publisher: { "@id": `${SITE_URL}/#organization` },
    image: [absoluteUrl("/icon-512.png")],
    ...(section ? { articleSection: section } : {}),
    ...(keywords.length ? { keywords: keywords.join(", ") } : {}),
    ...(wordCount ? { wordCount } : {}),
    /* No `about: /#software` here. That node is only emitted on the home page,
       and a reference to an @id that is absent from this page's graph is a
       dangling pointer, not an association -- the same mistake /pricing's
       `brand` was making. Shipping the full SoftwareApplication node on every
       article to fix it would cost more than the association is worth. */
    speakable: {
      "@type": "SpeakableSpecification",
      cssSelector: ["h1", "[data-speakable]"],
    },
  };
}

/**
 * HowTo for a `steps` block.
 *
 * Emitted only when the steps are genuinely a procedure someone performs.
 * A HowTo whose steps are really a list of features is the fastest way to a
 * structured-data manual action, so the block type is the gate: authors opt in
 * by writing `steps`, not by writing an ordered list.
 */
export function howToSchema({ path, locale = DEFAULT_LOCALE, name, description, totalTime, steps }) {
  const url = absoluteUrl(withLocale(path, locale));
  return {
    "@type": "HowTo",
    "@id": `${url}#howto-${slugId(name)}`,
    name,
    ...(description ? { description } : {}),
    ...(totalTime ? { totalTime } : {}),
    inLanguage: LOCALE_CODES.includes(locale) ? locale : DEFAULT_LOCALE,
    step: steps.map((s, i) => ({
      "@type": "HowToStep",
      position: i + 1,
      name: s.name,
      text: s.text,
      url: `${url}#${slugId(s.name)}`,
    })),
  };
}

/** ItemList for the index page — tells Google the collection's order and size. */
export function itemListSchema({ path, locale = DEFAULT_LOCALE, items }) {
  return {
    "@type": "ItemList",
    "@id": `${absoluteUrl(withLocale(path, locale))}#list`,
    itemListOrder: "https://schema.org/ItemListOrderDescending",
    numberOfItems: items.length,
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      url: absoluteUrl(withLocale(it.href, locale)),
      name: it.title,
    })),
  };
}

/* Local to this module: @id fragments must be URL-safe and stable. */
function slugId(text = "") {
  return String(text)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 60);
}

/* ── Share pages ───────────────────────────────────────────────────────────── */

/**
 * VideoObject for one published share.
 *
 * `uploadDate`, `name`, `description` and `thumbnailUrl` are the four Google
 * treats as required for a video rich result, and a share is missing exactly
 * one of them often enough to matter: a film whose every shot failed to record
 * a frame has no thumbnail. The node is emitted without it rather than with a
 * placeholder — an invented thumbnail is a wrong answer to a crawler, and the
 * page is still a valid VideoObject without the rich result.
 *
 * `contentUrl` points at /api/share/{slug}/video, which re-signs on every
 * request. The signed Storage URL the job finished with expires in seven days;
 * a URL in structured data has to still resolve months later.
 */
export function videoObjectSchema({
  slug,
  name,
  description,
  thumbnailUrl,
  contentUrl,
  embedUrl,
  uploadDate,
  duration,
  inLanguage,
}) {
  const url = absoluteUrl(`/s/${slug}`);
  return {
    "@type": "VideoObject",
    "@id": `${url}#video`,
    url,
    name,
    description,
    ...(thumbnailUrl ? { thumbnailUrl: [thumbnailUrl] } : {}),
    ...(contentUrl ? { contentUrl } : {}),
    ...(embedUrl ? { embedUrl } : {}),
    ...(uploadDate ? { uploadDate } : {}),
    ...(duration ? { duration } : {}),
    ...(inLanguage ? { inLanguage } : {}),
    isFamilyFriendly: true,
    publisher: { "@id": `${SITE_URL}/#organization` },
    /* Not `author`. The person who generated the film is deliberately absent
       from the payload this page is built from (see server/sharing.py), and
       naming MuseForge as the author of someone else's work would be a claim
       the product is not entitled to make. Publisher is what it actually is. */
    creativeWorkStatus: "Published",
  };
}
