import { SITE_URL } from "../../../../../lib/seo";
import { ARTICLES, articlePath, loadArticle, localesOf } from "../../../../../lib/content";
import { withLocale } from "../../../../../lib/i18n/routing";
import { articleToMarkdown } from "../../../../../lib/content/markdown";
import { articleLabels } from "../../../../../lib/content/labels";

/**
 * /md/<locale>/blog/<slug> — one article as Markdown.
 *
 * WHY THE PREFIX RATHER THAN A ".md" SUFFIX. The obvious URL is
 * /blog/<slug>.md, but a Next segment is either a literal or a parameter and
 * cannot be "[slug] followed by .md". A distinct prefix is the honest version
 * of the same idea, and it keeps the plain-text editions out of the localized
 * route tree: /md is in UNLOCALIZED_PREFIXES and in the middleware's exclusion
 * list, so nothing rewrites it to /en/md/... on the way in.
 *
 * WHY THE LOCALE IS A SEGMENT RATHER THAN `?lang=`. A query parameter cannot
 * be prerendered -- `dynamic = "force-static"` strips the search string, so the
 * first version of this route answered every language in English. Giving each
 * translation its own path makes every edition a static file and gives it a URL
 * that can be linked, cached and cited, which is what a distinct document
 * should have anyway. English is spelled out as /md/en/... here: the
 * as-needed-prefix rule exists to keep marketing URLs clean, and these are not
 * marketing URLs.
 *
 * The body is the same prose the HTML page renders (see
 * lib/content/markdown.js), never a different or expanded version of it.
 */

export const dynamic = "force-static";

/** Only the (locale, slug) pairs that have a body — the same rule the pages use. */
export function generateStaticParams() {
  return ARTICLES.flatMap((a) => localesOf(a).map((locale) => ({ locale, slug: a.slug })));
}

export function GET(_request, { params: { locale, slug } }) {
  const article = loadArticle(slug, locale);
  if (!article) {
    return new Response("Not found\n", {
      status: 404,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }

  const canonicalUrl = `${SITE_URL}${withLocale(articlePath(slug), locale)}`;

  return new Response(articleToMarkdown(article, canonicalUrl, articleLabels(locale)), {
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      /* Points a crawler that found this file at the page it is a copy of, so
         the two are never treated as competing documents. */
      Link: `<${canonicalUrl}>; rel="canonical"`,
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
    },
  });
}
