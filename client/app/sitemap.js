import { SITE_URL } from "../lib/seo";
import { lastModified } from "../lib/routeMtime";
import { LOCALE_CODES, withLocale } from "../lib/i18n/routing";
import { getRecentShares, SHARE_REVALIDATE } from "../lib/share";

/* The share list is read from the API, so this file is no longer a pure
   function of the repo. Revalidated on the same hour as the pages themselves:
   a sitemap that promised a URL Google then found revoked is worse than one
   that names it an hour late. */
export const revalidate = SHARE_REVALIDATE;
import { ARTICLES, BLOG_PATH, articlePath, localesOf, articleSourceFiles } from "../lib/content";

/* Only publicly indexable routes belong here. /login, /dashboard, /admin,
   /generate and /auth are excluded — see app/robots.js.
   `files` drives <lastmod>: the last commit touching any of them.
   `locales` narrows a route to the languages it actually exists in; it
   defaults to all twenty, which is right for everything except articles. */
const L = "app/[locale]";

/* The union of every language some article is written in. The index page is
   listed for exactly these: a /ja/blog whose cards are all English is rendered
   for navigation but is noindex, so putting it in the sitemap would be asking
   Google to crawl a page we asked it not to keep. */
const ARTICLE_LOCALES = [
  ...new Set(ARTICLES.flatMap((a) => localesOf(a))),
];

const ROUTES = [
  {
    path: "/",
    files: [`${L}/page.js`, `${L}/HomeContent.js`, "components/IdeaForm.js", "components/MiniDemo.js"],
    changeFrequency: "weekly",
    priority: 1.0,
  },
  {
    path: "/pricing",
    files: [`${L}/pricing/page.js`, `${L}/pricing/PricingContent.js`],
    changeFrequency: "monthly",
    priority: 0.9,
  },
  ...["creators", "agencies", "filmmakers", "education"].map((seg) => ({
    path: `/solutions/${seg}`,
    files: [`${L}/solutions/${seg}/page.js`, "components/SolutionPage.js"],
    changeFrequency: "monthly",
    priority: 0.8,
  })),
  {
    path: BLOG_PATH,
    files: [`${L}/blog/page.js`, "lib/content/index.js"],
    locales: ARTICLE_LOCALES,
    changeFrequency: "weekly",
    priority: 0.8,
  },
  ...ARTICLES.map((article) => ({
    path: articlePath(article.slug),
    files: articleSourceFiles(article),
    locales: localesOf(article),
    changeFrequency: "monthly",
    priority: 0.7,
  })),
  {
    path: "/legal/privacy",
    files: [`${L}/legal/privacy/page.js`, `${L}/legal/privacy/PrivacyContent.js`],
    changeFrequency: "yearly",
    priority: 0.3,
  },
  {
    path: "/legal/terms",
    files: [`${L}/legal/terms/page.js`, `${L}/legal/terms/TermsContent.js`],
    changeFrequency: "yearly",
    priority: 0.3,
  },
];

const abs = (path) => (path === "/" ? SITE_URL : `${SITE_URL}${path}`);

export default async function sitemap() {
  return [...staticEntries(), ...(await shareEntries())];
}

/**
 * The published share pages.
 *
 * One entry each, no hreflang cluster and no locale variants: a share exists
 * at exactly one URL (see UNLOCALIZED_PREFIXES). `lastModified` is when it was
 * published rather than when a file changed, because no file ever does.
 *
 * Fails open to an empty list (see lib/share.js). A sitemap that throws takes
 * every static route down with it, and the static routes are the ones actually
 * carrying rankings.
 */
async function shareEntries() {
  const shares = await getRecentShares(500);
  return shares
    .filter((s) => s?.slug)
    .map((s) => ({
      url: `${SITE_URL}/s/${s.slug}`,
      lastModified: s.shared_at || s.created_at || undefined,
      changeFrequency: "monthly",
      /* Below every hand-written route on purpose. These pages are numerous
         and user-generated; the landing page and /pricing are what the site is
         trying to rank, and a thousand 0.8s would drown them out. */
      priority: 0.5,
    }));
}

function staticEntries() {
  return ROUTES.flatMap(({ path, files, locales, changeFrequency, priority }) => {
    const when = lastModified(files);
    const codes = locales?.length ? locales : LOCALE_CODES;
    // Every locale variant is listed, and each entry carries the full hreflang
    // cluster. Google wants the annotations to be reciprocal — a variant that
    // only appears in <link> tags and never as its own <url> is easy to miss.
    // For a route that exists in a subset of languages the cluster is that
    // subset, matching the <link rel="alternate"> tags the page itself emits.
    const languages = Object.fromEntries(
      codes.map((code) => [code, abs(withLocale(path, code))])
    );
    return codes.map((code) => ({
      url: abs(withLocale(path, code)),
      lastModified: when,
      changeFrequency,
      priority,
      alternates: { languages: { ...languages, "x-default": abs(path) } },
    }));
  });
}
