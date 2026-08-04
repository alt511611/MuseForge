import { SITE_URL } from "../lib/seo";
import { LOCALE_CODES, DEFAULT_LOCALE } from "../lib/i18n/routing";

/* Private or thin routes. Each one exists under every locale prefix too
   (/tr/dashboard, /ja/dashboard, ...), so the list is expanded accordingly —
   a bare "Disallow: /dashboard" would leave 19 crawlable duplicates. */
const PRIVATE_PATHS = ["/admin", "/dashboard", "/generate", "/auth", "/api", "/login"];

export default function robots() {
  const disallow = PRIVATE_PATHS.flatMap((p) => [
    p,
    ...LOCALE_CODES.filter((c) => c !== DEFAULT_LOCALE).map((c) => `/${c}${p}`),
  ]);

  return {
    rules: [{ userAgent: "*", allow: "/", disallow }],
    sitemap: `${SITE_URL}/sitemap.xml`,
    // Yandex's Host directive takes a bare hostname, not a full URL.
    host: new URL(SITE_URL).host,
  };
}
