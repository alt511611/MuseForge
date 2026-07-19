import { createServerClient } from "@supabase/ssr";
import { NextResponse } from "next/server";
import { SUPABASE_URL, SUPABASE_ANON_KEY, hasSupabaseConfig } from "./lib/supabaseEnv";

// NOTE: "/" is intentionally NOT in this list. The landing page must stay
// reachable by anonymous visitors (demo mode generates videos without an
// account). Only the actual generation results page and admin are gated.
const PROTECTED = ["/generate"];
const ADMIN_ONLY = ["/admin"];

export async function middleware(request) {
  const { pathname } = request.nextUrl;
  let response = NextResponse.next({ request });

  const isProtected = PROTECTED.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );
  const isAdminRoute = ADMIN_ONLY.some(
    (p) => pathname === p || pathname.startsWith(p + "/")
  );

  // Auth isn't configured yet (e.g. local dev before Supabase is wired up,
  // or a preview deploy without env vars). Don't block anyone — just skip
  // auth-gating entirely rather than crashing every request.
  if (!hasSupabaseConfig()) {
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
        response = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) =>
          response.cookies.set(name, value, options)
        );
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if ((isProtected || isAdminRoute) && !user) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (isAdminRoute && user) {
    const role =
      user.app_metadata?.role || user.user_metadata?.role || "user";
    if (role !== "admin") {
      return NextResponse.redirect(new URL("/", request.url));
    }
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|api/|auth/).*)"],
};
