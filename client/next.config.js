/* Canonical host. Everything else (the apex or www counterpart, preview
   aliases pointed at the same app) gets 301'd here so link equity lands on one
   origin. Kept in sync with NEXT_PUBLIC_SITE_URL, which lib/seo.js also reads.

   The value INCLUDES the www, because that is what the host actually serves:
   museforge.studio 308s to www.museforge.studio. Setting the apex here would
   add a www -> apex redirect on top of the host's apex -> www one, which is a
   loop, not a canonicalisation. The `startsWith("www.")` guard in redirects()
   below is what keeps that from happening -- it emits no rule when the
   canonical host is already the www one. */
const SITE_URL = (
  process.env.NEXT_PUBLIC_SITE_URL || "https://www.museforge.studio"
).replace(/\/$/, "");
const CANONICAL_HOST = new URL(SITE_URL).host;

/* Duplicated from lib/i18n/locales.js: next.config.js is CommonJS and loads
   before the ESM module graph exists, so it can't import it. */
const LOCALE_CODES = [
  "en", "tr", "es", "fr", "de", "pt", "it", "ru", "ar", "hi",
  "ja", "ko", "zh", "id", "vi", "th", "pl", "nl", "uk", "ro",
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  // Next already 308-redirects "/pricing/" -> "/pricing" with this default;
  // stated explicitly so nobody flips it and silently creates duplicate URLs.
  trailingSlash: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
      // Private / thin routes: keep them out of the index even if a crawler
      // reaches them through a shared link rather than through robots.txt.
      // Matched both unprefixed (English) and under a locale prefix.
      ...["/admin", "/dashboard", "/generate", "/auth", "/login"].flatMap((base) => [
        `${base}/:path*`,
        `/:locale(${LOCALE_CODES.join("|")})${base}/:path*`,
      ]).map((source) => ({
        source,
        headers: [{ key: "X-Robots-Tag", value: "noindex, follow" }],
      })),
    ];
  },
  async redirects() {
    if (CANONICAL_HOST.startsWith("www.")) return [];
    return [
      {
        source: "/:path*",
        has: [{ type: "host", value: `www.${CANONICAL_HOST}` }],
        destination: `${SITE_URL}/:path*`,
        permanent: true,
      },
    ];
  },
  async rewrites() {
    const apiUrl = process.env.API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
