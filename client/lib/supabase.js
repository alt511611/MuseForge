import { createBrowserClient } from "@supabase/ssr";
import { SUPABASE_URL, SUPABASE_ANON_KEY, hasSupabaseConfig } from "./supabaseEnv";

// Returns null (instead of throwing) when Supabase isn't configured, so
// static prerendering of public pages (/, /pricing, /legal/*) never fails
// just because auth env vars aren't set yet. Callers must handle a null
// client (see contexts/AuthContext.js).
export function createClient() {
  if (!hasSupabaseConfig()) {
    return null;
  }
  return createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY);
}
