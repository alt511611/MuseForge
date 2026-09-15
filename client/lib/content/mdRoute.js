/**
 * The three Markdown page routes, minus the three copies of the same handler.
 *
 * Each route under /md is a separate file because Next resolves routes by
 * path, not by parameter — but what they DO is identical: resolve the document,
 * 404 if there is none, serve it as text. That belongs in one place, where the
 * cache header and the 404 body cannot drift between them.
 */

import { SITE_URL } from "../seo";
import { DEFAULT_LOCALE, LOCALE_CODES, withLocale } from "../i18n/routing";
import { articleLabels } from "./labels";
import { pageDoc, pageToMarkdown } from "./pages";

const TEXT = { "Content-Type": "text/plain; charset=utf-8" };

/**
 * The (locale) params a page's Markdown edition should be prerendered for.
 *
 * A page whose document forces one locale — the untranslated segment pages —
 * is generated once, at that locale, rather than twenty times identically.
 */
export function mdStaticParams(key) {
  const forced = pageDoc(key, DEFAULT_LOCALE)?.forcedLocale;
  return (forced ? [forced] : LOCALE_CODES).map((locale) => ({ locale }));
}

/** The document at `key` in `locale`, as a text/plain response. */
export function mdResponse(key, locale) {
  const doc = pageDoc(key, locale);
  if (!doc) {
    return new Response("Not found\n", { status: 404, headers: TEXT });
  }

  /* The canonical the document points at is the RENDERED page in the reader's
     language, not this file: a model that cites the source should cite the URL
     a person can open. */
  const canonicalLocale = doc.forcedLocale || locale;
  const url = `${SITE_URL}${withLocale(doc.path, canonicalLocale)}`;

  return new Response(pageToMarkdown(doc, url, articleLabels(canonicalLocale)), {
    headers: {
      ...TEXT,
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
    },
  });
}
