import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { SUPABASE_URL, SUPABASE_ANON_KEY, hasSupabaseConfig } from "./supabaseEnv";

// Same null-if-unconfigured guard as lib/supabase.js — see that file for why.
export function createServerSupabaseClient() {
  if (!hasSupabaseConfig()) {
    return null;
  }

  const cookieStore = cookies();
  return createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          );
        } catch {
          // Server component — can be ignored
        }
      },
    },
  });
}
