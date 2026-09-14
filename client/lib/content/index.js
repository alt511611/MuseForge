/**
 * The article registry.
 *
 * Imports are static and listed by hand, for the same reason the locale
 * dictionaries are (see lib/i18n/dictionary.js): a dynamic
 * `import(`../content/blog/${slug}`)` reads better and then hides the set of
 * articles from the bundler, which responds by bundling all of them into every
 * route or none of them into any.
 *
 * TRANSLATION POLICY. An article exists in the locales it has actually been
 * written in, and nowhere else. The tempting alternative -- serve the English
 * body under all twenty prefixes -- publishes nineteen near-duplicates of every
 * post and invites Google to pick a canonical for us. So `localesOf` is the
 * authority: generateStaticParams, the hreflang cluster and the sitemap all
 * read it, and a locale that is missing simply has no URL.
 */

import characterConsistency from "../../content/blog/ai-video-character-consistency";
import shortFilm from "../../content/blog/how-to-make-an-ai-short-film";
import prompting from "../../content/blog/text-to-video-prompt-guide";
import microDrama from "../../content/blog/micro-drama-series-playbook";
import choosing from "../../content/blog/choosing-an-ai-video-generator";

import { DEFAULT_LOCALE } from "../i18n/routing";
import { withHeadingIds, readingMinutes, leadSummary } from "./blocks";

/**
 * Newest first — the order the index page and the sitemap both want.
 *
 * The comparator returns 0 for equal dates rather than a sign, so a batch of
 * articles published on the same day keeps the order written below instead of
 * being reversed by an inconsistent comparator. The array order is therefore
 * the editorial order within a day, and the one to edit when it matters.
 */
export const ARTICLES = [
  characterConsistency,
  shortFilm,
  prompting,
  microDrama,
  choosing,
].sort((a, b) => (a.published === b.published ? 0 : a.published < b.published ? 1 : -1));

export const BLOG_PATH = "/blog";

/** Site-relative path for an article, before locale prefixing. */
export const articlePath = (slug) => `${BLOG_PATH}/${slug}`;

/** The locales an article has a body for, English first. */
export function localesOf(meta) {
  const codes = Object.keys(meta.locales || {});
  return codes.sort((a, b) =>
    a === DEFAULT_LOCALE ? -1 : b === DEFAULT_LOCALE ? 1 : a.localeCompare(b)
  );
}

export function findArticle(slug) {
  return ARTICLES.find((a) => a.slug === slug) || null;
}

/** Articles written in this locale, newest first. May be empty. */
export function articlesIn(locale) {
  return ARTICLES.filter((a) => Boolean(a.locales?.[locale]));
}

/**
 * Everything a page needs to render one article, or null if this locale does
 * not have it. Heading ids are attached here so the body, the contents list and
 * the anchor links can never disagree about them.
 */
export function loadArticle(slug, locale) {
  const meta = findArticle(slug);
  const body = meta?.locales?.[locale];
  if (!meta || !body) return null;

  const blocks = withHeadingIds(body.blocks || []);
  return {
    ...meta,
    locale,
    locales: localesOf(meta),
    title: body.title,
    headline: body.headline || body.title,
    description: body.description,
    blocks,
    minutes: readingMinutes(blocks),
    summary: leadSummary(blocks) || body.description,
  };
}

/**
 * Card data for the index page: no body, no heading pass.
 * `href` is unprefixed; the caller localizes it.
 */
export function articleCard(meta, locale) {
  const body = meta.locales?.[locale] || meta.locales?.[DEFAULT_LOCALE];
  const shown = meta.locales?.[locale] ? locale : DEFAULT_LOCALE;
  return {
    slug: meta.slug,
    href: articlePath(meta.slug),
    category: meta.category,
    published: meta.published,
    updated: meta.updated || meta.published,
    tags: meta.tags || [],
    title: body.title,
    description: body.description,
    minutes: readingMinutes(body.blocks || []),
    /* The locale the card's copy is actually in. The index falls back to
       English rather than showing a gap, and says so when it does. */
    shownIn: shown,
  };
}

/** Repo-relative source files behind an article — the sitemap reads git for <lastmod>. */
export function articleSourceFiles(meta) {
  return [
    `content/blog/${meta.slug}/index.js`,
    ...localesOf(meta).map((c) => `content/blog/${meta.slug}/${c}.js`),
  ];
}
