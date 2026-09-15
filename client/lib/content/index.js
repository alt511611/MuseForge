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

/* ── The related-articles graph ────────────────────────────────────────── */

/**
 * How many "keep reading" cards an article shows.
 *
 * Three rather than two because the third is the slot reciprocity lives in:
 * with two, both are taken by the editorial picks and a back-reference never
 * reaches the page.
 */
export const RELATED_LIMIT = 3;

/**
 * Related articles for one page — editorial intent first, and no orphans.
 *
 * WHY THIS IS COMPUTED RATHER THAN DECLARED. `related` in an article's
 * index.js says what a reader of THIS piece should read next, which is the
 * right thing for an author to write down and the wrong thing to leave as the
 * whole answer: it is a directed graph, and nothing in it guarantees that
 * anyone points back. Left alone it produced exactly that failure — the buying
 * guide declared two outbound links and received none, so the only path to it
 * was the index page, and Search Console reported it as "URL is unknown to
 * Google" with no referring page at all while its four siblings were already
 * crawled. Inbound links are how a crawler finds a page and part of how it
 * decides the page matters; an article nobody links to has neither.
 *
 * So the declared list is honoured first, then back-references (the articles
 * that named this one), then everything else — and the LAST slot is given to
 * whichever candidate has the fewest inbound links so far. That last rule is
 * the one doing the work. Symmetry alone does not survive the slice: merging
 * back-references into a list that is then cut to three drops precisely the
 * least-linked article, which is the one that needed the link.
 *
 * Assignment runs once per locale in registry order, updating the counts as it
 * goes, so the result is deterministic and the same on every build.
 *
 * PER LOCALE, because a Turkish page linking to an article that exists only in
 * English is a 404 wearing a card.
 */
function buildRelatedGraph(locale) {
  const pool = articlesIn(locale);
  const slugs = pool.map((a) => a.slug);
  const inbound = new Map(slugs.map((slug) => [slug, 0]));
  const graph = new Map();

  for (const article of pool) {
    const declared = (article.related || []).filter(
      (slug) => slug !== article.slug && slugs.includes(slug)
    );
    const backRefs = slugs.filter(
      (slug) =>
        slug !== article.slug &&
        !declared.includes(slug) &&
        (findArticle(slug)?.related || []).includes(article.slug)
    );
    const rest = slugs.filter(
      (slug) => slug !== article.slug && !declared.includes(slug) && !backRefs.includes(slug)
    );
    const candidates = [...declared, ...backRefs, ...rest];

    const chosen = candidates.slice(0, Math.max(0, RELATED_LIMIT - 1));
    const remaining = candidates.filter((slug) => !chosen.includes(slug));
    if (remaining.length && chosen.length < RELATED_LIMIT) {
      /* Ties break on candidate order, so an article never loses its editorial
         pick to a coin flip that could land either way between builds. */
      remaining.sort(
        (a, b) =>
          inbound.get(a) - inbound.get(b) ||
          candidates.indexOf(a) - candidates.indexOf(b)
      );
      chosen.push(remaining[0]);
    }

    for (const slug of chosen) inbound.set(slug, inbound.get(slug) + 1);
    graph.set(article.slug, chosen);
  }

  /* The scarcity rule makes an orphan very unlikely and does not make it
     impossible — with enough articles, one can lose every tiebreak. Rather than
     argue about when that happens, check and repair: each orphan displaces the
     last card of the article it itself names first, which is the reciprocal
     link an author would have written by hand. */
  for (const slug of slugs) {
    if (inbound.get(slug) > 0) continue;
    const host =
      (findArticle(slug)?.related || []).find((s) => slugs.includes(s)) ||
      slugs.find((s) => s !== slug);
    if (!host) continue;
    const list = graph.get(host);
    if (!list || list.includes(slug)) continue;
    const displaced = list[list.length - 1];
    list[list.length - 1] = slug;
    inbound.set(slug, inbound.get(slug) + 1);
    if (displaced) inbound.set(displaced, inbound.get(displaced) - 1);
  }

  return graph;
}

/* One graph per locale, built on first use. Article pages are prerendered, so
   this runs a handful of times at build time and never in a request. */
const relatedGraphs = new Map();

function relatedGraph(locale) {
  if (!relatedGraphs.has(locale)) relatedGraphs.set(locale, buildRelatedGraph(locale));
  return relatedGraphs.get(locale);
}

/** The articles to show under one article, as metadata, in display order. */
export function relatedTo(slug, locale) {
  return (relatedGraph(locale).get(slug) || []).map(findArticle).filter(Boolean);
}

/**
 * Inbound link count per article for this locale — what the graph actually
 * produced, not what was declared. Exported so the invariant can be checked
 * from outside rather than trusted.
 */
export function inboundLinkCounts(locale) {
  const counts = Object.fromEntries(articlesIn(locale).map((a) => [a.slug, 0]));
  for (const [, list] of relatedGraph(locale)) {
    for (const slug of list) if (slug in counts) counts[slug] += 1;
  }
  return counts;
}

/** Repo-relative source files behind an article — the sitemap reads git for <lastmod>. */
export function articleSourceFiles(meta) {
  return [
    `content/blog/${meta.slug}/index.js`,
    ...localesOf(meta).map((c) => `content/blog/${meta.slug}/${c}.js`),
  ];
}
