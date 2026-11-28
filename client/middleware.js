import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import { SUPABASE_URL, SUPABASE_ANON_KEY, hasSupabaseConfig } from "./lib/supabaseEnv";
import { DEFAULT_LOCALE, isLocale, splitLocale, withLocale } from "./lib/i18n/routing";

// Browsers send a weighted list such as "tr-TR,tr;q=0.9,en;q=0.8". Keep the
// negotiation deliberately small and deterministic: exact locale first,
// then the base language, then English. Unsupported languages are ignored.
function preferredLocale(request) {
  const saved = request.cookies.get("mf_locale")?.value;
  if (saved && isLocale(saved)) return saved;

  const header = request.headers.get("accept-language") || "";
  const candidates = header
    .split(",")
    .map((part, index) => {
      const [raw, ...params] = part.trim().split(";");
      const qParam = params.find((p) => p.trim().startsWith("q="));
      const q = qParam ? Number(qParam.trim().slice(2)) : 1;
      return { raw: raw.toLowerCase(), q: Number.isFinite(q) ? q : 0, index };
    })
    .filter(({ raw, q }) => raw && raw !== "*" && q > 0)
    .sort((a, b) => b.q - a.q || a.index - b.index);

  for (const { raw } of candidates) {
    const exact = raw.split("-")[0];
    if (isLocale(raw)) return raw;
    if (isLocale(exact)) return exact;
  }
  return DEFAULT_LOCALE;
}

function isLikelyCrawler(request) {
  const ua = (request.headers.get("user-agent") || "").toLowerCase();
  return /bot|crawler|spider|slurp|bingpreview|facebookexternalhit|twitterbot|linkedinbot/.test(ua);
}

// NOTE: "/" is intentionally NOT in this list. The landing page must stay
// reachable by anonymous visitors (demo mode generates videos without an
// account). Only the actual generation results page and admin are gated.
// Paths here are locale-stripped, so "/tr/generate/123" matches "/generate".
/**
 * The Markdown edition of `path`, when the request asked for Markdown and one
 * exists. Null otherwise.
 *
 * WHY NEGOTIATE AT ALL, when every page already links its edition with
 * <link rel="alternate" type="text/markdown">. Because the agents that would
 * use it most do not parse the HTML first: a fetch tool that sends
 * `Accept: text/markdown, text/html;q=0.9` is saying, before it has read a
 * byte, that it would rather not. Answering that with 120 KB of React and
 * letting it strip the markup itself is the waste the /md routes exist to
 * prevent. The response is the same file /md/... serves, so there is one
 * Markdown edition, not two.
 *
 * WHEN IT FIRES. Only when text/markdown is preferred over text/html — a
 * browser's wildcard Accept or a crawler's plain "text/html" never matches,
 * so nothing a human or Googlebot sees changes. q-values are honoured because
 * the one thing worse than not negotiating is negotiating wrongly.
 *
 * WHICH PATHS. Exactly the families that have an edition: the home page,
 * /pricing, the four /solutions pages (English only, so always /md/en), and
 * the articles. The blog index and legal pages have none, and fall through to
 * HTML rather than to a 404.
 */
function markdownTarget(request, locale, path) {
  const accept = request.headers.get("accept") || "";
  const weight = (type) => {
    for (const part of accept.split(",")) {
      const [raw, ...params] = part.trim().split(";");
      if (raw.trim().toLowerCase() !== type) continue;
      const q = params.find((p) => p.trim().startsWith("q="));
      const n = q ? Number(q.trim().slice(2)) : 1;
      return Number.isFinite(n) ? n : 0;
    }
    return 0;
  };
  const md = weight("text/markdown");
  if (md <= 0 || md < weight("text/html")) return null;

  if (path === "/") return `/md/${locale}`;
  if (path === "/pricing") return `/md/${locale}/pricing`;
  if (/^\/solutions\/[a-z]+$/.test(path)) return `/md/${DEFAULT_LOCALE}${path}`;
  if (/^\/blog\/[a-z0-9-]+$/.test(path)) return `/md/${locale}${path}`;
  return null;
}

const PROTECTED = ["/generate"];
const ADMIN_ONLY = ["/admin"];

export async function middleware(request) {
  const { pathname } = request.nextUrl;

  // Split "/tr/pricing" -> { locale: "tr", path: "/pricing" }. An unprefixed
  // path yields the default locale and is rewritten to /en/... below, so every
  // request resolves through app/[locale]/ while the URL stays clean.
  const { locale, path } = splitLocale(pathname);
  const hasPrefix = isLocale(pathname.split("/")[1]);

  // The unprefixed root is the stable English URL. For a human's first visit,
  // honour their saved choice or browser language and move them to the
  // localized URL. Crawlers stay on the canonical English URL so indexing is
  // stable and the hreflang cluster remains authoritative.
  if (!hasPrefix && path === "/" && !isLikelyCrawler(request)) {
    const negotiated = preferredLocale(request);
    if (negotiated !== DEFAULT_LOCALE) {
      return NextResponse.redirect(new URL(withLocale("/", negotiated), request.url), 307);
    }
  }

  // /en/pricing and /pricing render identically. Collapse the prefixed form
  // permanently so only one URL per locale is ever crawlable or linkable.
  if (hasPrefix && locale === DEFAULT_LOCALE) {
    const target = new URL(path + request.nextUrl.search, request.url);
    return NextResponse.redirect(target, 308);
  }

  const md = markdownTarget(request, locale, path);
  if (md) {
    const res = NextResponse.rewrite(new URL(md, request.url));
    res.headers.set("Vary", "Accept");
    return res;
  }

  // Rebuilt rather than reused: Supabase's cookie writer needs a fresh
  // response object, and it must keep the locale rewrite or unprefixed
  // gated routes (e.g. /generate/x) would resolve to nothing.
  const buildResponse = () =>
    hasPrefix
      ? NextResponse.next({ request })
      : NextResponse.rewrite(
          new URL(
            `/${DEFAULT_LOCALE}${path === "/" ? "" : path}${request.nextUrl.search}`,
            request.url
          ),
          { request }
        );

  let response = buildResponse();

  const matches = (list) =>
    list.some((p) => path === p || path.startsWith(p + "/"));
  const isProtected = matches(PROTECTED);
  const isAdminRoute = matches(ADMIN_ONLY);

  // Auth isn't configured yet (e.g. local dev before Supabase is wired up,
  // or a preview deploy without env vars). Don't block anyone — just skip
  // auth-gating entirely rather than crashing every request.
  if (!hasSupabaseConfig()) {
    return response;
  }

  if (!isProtected && !isAdminRoute) {
    // Nothing to gate: skip the Supabase round-trip entirely. Public pages are
    // static, and an auth call here would slow every crawl of every locale.
    return response;
  }

  const supabase = createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) =>
          request.cookies.set(name, value)
        );
        response = buildResponse();
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options)
        );
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  // Redirects keep the visitor in their own language.
  if (!user) {
    const loginUrl = new URL(withLocale("/login", locale), request.url);
    loginUrl.searchParams.set("next", path + request.nextUrl.search);
    return NextResponse.redirect(loginUrl);
  }

  if (isAdminRoute) {
    const role =
      user.app_metadata?.role || user.user_metadata?.role || "user";
    if (role !== "admin") {
      return NextResponse.redirect(new URL(withLocale("/", locale), request.url));
    }
  }

  return response;
}

export const config = {
  // Metadata routes, static assets and the unlocalized share routes must never
  // be rewritten into /[locale]. `s/` and `embed/` live outside app/[locale]
  // on purpose (see UNLOCALIZED_PREFIXES): a rewrite would send /s/x to
  // /en/s/x, which is a route that does not exist.
  matcher: [
    "/((?!_next/static|_next/image|api/|auth/|md/|og/|s/|embed/|favicon.ico|icon-\\d+\\.png|icon\\.svg|apple-touch-icon\\.png|robots\\.txt|[0-9a-f]{32}\\.txt|sitemap\\.xml|llms\\.txt|llms-full\\.txt|manifest\\.webmanifest|opengraph-image).*)",
  ],
};
