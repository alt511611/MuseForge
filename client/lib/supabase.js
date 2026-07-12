import { createBrowserClient } from "@supabase/ssr";

// Returns null (instead of throwing) when Supabase isn't configured, so
// static prerendering of public pages (/, /pricing, /legal/*) never fails
// just because auth env vars aren't set yet. Callers must handle a null
// client (see contexts/AuthContext.js).
export function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anonKey) {
    return null;
  }
  return createBrowserClient(url, anonKey);
}
