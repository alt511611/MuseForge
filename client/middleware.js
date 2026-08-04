import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import { SUPABASE_URL, SUPABASE_ANON_KEY, hasSupabaseConfig } from "./lib/supabaseEnv";
import { DEFAULT_LOCALE, isLocale, splitLocale, withLocale } from "./lib/i18n/routing";

// NOTE: "/" is intentionally NOT in this list. The landing page must stay
// reachable by anonymous visitors (demo mode generates videos without an
// account). Only the actual generation results page and admin are gated.
// Paths here are locale-stripped, so "/tr/generate/123" matches "/generate".
const PROTECTED = ["/generate"];
const ADMIN_ONLY = ["/admin"];

export async function middleware(request) {
  const { pathname } = request.nextUrl;

  // Split "/tr/pricing" -> { locale: "tr", path: "/pricing" }. An unprefixed
  // path yields the default locale and is rewritten to /en/... below, so every
  // request resolves through app/[locale]/ while the URL stays clean.
  const { locale, path } = splitLocale(pathname);
  const hasPrefix = isLocale(pathname.split("/")[1]);

  // /en/pricing and /pricing render identically. Collapse the prefixed form
  // permanently so only one URL per locale is ever crawlable or linkable.
  if (hasPrefix && locale === DEFAULT_LOCALE) {
    const target = new URL(path + request.nextUrl.search, request.url);
    return NextResponse.redirect(target, 308);
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
  // Metadata routes and static assets must never be rewritten into /[locale].
  matcher: [
    "/((?!_next/static|_next/image|api/|auth/|favicon.ico|icon-\\d+\\.png|icon\\.svg|apple-touch-icon\\.png|robots\\.txt|sitemap\\.xml|manifest\\.webmanifest|opengraph-image).*)",
  ],
};
