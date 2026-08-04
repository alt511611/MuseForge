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

export const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://museforge.ai"
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
export function canonical(path = "/", locale = DEFAULT_LOCALE) {
  const languages = Object.fromEntries(
    LOCALE_CODES.map((code) => [code, withLocale(path, code)])
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
export function openGraphFor({ title, description, path = "/", locale = DEFAULT_LOCALE }) {
  return {
    type: "website",
    siteName: SITE_NAME,
    title,
    description,
    url: withLocale(path, locale),
    locale: ogLocale(locale),
    alternateLocale: LOCALE_CODES.filter((c) => c !== locale).map(ogLocale),
  };
}

/* ── JSON-LD builders ──────────────────────────────────────────────────── */

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
    sameAs: ["https://twitter.com/museforge_ai"],
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
