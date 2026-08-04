import { SITE_URL } from "../lib/seo";
import { lastModified } from "../lib/routeMtime";
import { LOCALE_CODES, withLocale } from "../lib/i18n/routing";

/* Only publicly indexable routes belong here. /login, /dashboard, /admin,
   /generate and /auth are excluded — see app/robots.js.
   `files` drives <lastmod>: the last commit touching any of them. */
const L = "app/[locale]";

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

export default function sitemap() {
  return ROUTES.flatMap(({ path, files, changeFrequency, priority }) => {
    const when = lastModified(files);
    // Every locale variant is listed, and each entry carries the full hreflang
    // cluster. Google wants the annotations to be reciprocal — a variant that
    // only appears in <link> tags and never as its own <url> is easy to miss.
    const languages = Object.fromEntries(
      LOCALE_CODES.map((code) => [code, abs(withLocale(path, code))])
    );
    return LOCALE_CODES.map((code) => ({
      url: abs(withLocale(path, code)),
      lastModified: when,
      changeFrequency,
      priority,
      alternates: { languages: { ...languages, "x-default": abs(path) } },
    }));
  });
}
