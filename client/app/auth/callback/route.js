import { NextResponse } from "next/server";
import { createServerSupabaseClient } from "../../../lib/supabase-server";

export async function GET(request) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/";

  if (code) {
    // The shared helper rather than a second inline createServerClient: this
    // route had its own copy of the cookie plumbing and, unlike the helper, no
    // hasSupabaseConfig() guard — so on a deployment without Supabase env vars
    // it constructed a client against an empty URL and threw inside the OAuth
    // callback, which the user sees as a blank crash mid-sign-in rather than a
    // redirect back to the login page.
    const supabase = createServerSupabaseClient();
    if (supabase) {
      const { error } = await supabase.auth.exchangeCodeForSession(code);
      if (!error) {
        return NextResponse.redirect(`${origin}${next}`);
      }
    }
  }

  return NextResponse.redirect(`${origin}/login?error=auth_callback_failed`);
}
