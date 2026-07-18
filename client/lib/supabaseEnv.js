// Single source of truth for Supabase's public URL/key, mirroring
// lib/apiBase.js's reasoning: reading process.env.NEXT_PUBLIC_SUPABASE_URL
// directly in 4 different files meant no single place guarded against a
// pasted-in trailing slash or stray whitespace (a very easy mistake when
// copy-pasting into Vercel's env var UI). A trailing slash here can make
// the Supabase client construct malformed request paths internally,
// surfacing as "Invalid path specified in request URL".
//
// Also strips known REST/Auth/Storage path suffixes (e.g. "/rest/v1"),
// since Supabase's own dashboard shows example URLs like
// "https://xxx.supabase.co/rest/v1" in its API docs section, which people
// understandably copy instead of the bare "Project URL". If that suffix
// is left in, the supabase-js client appends its own "/auth/v1/..." on
// top of it, producing broken double paths like
// "https://xxx.supabase.co/rest/v1/auth/v1/signup" -> 404.
const KNOWN_BAD_SUFFIXES = [/\/rest\/v1$/, /\/auth\/v1$/, /\/storage\/v1$/];

function normalizeSupabaseUrl(raw) {
  let url = (raw || "").trim().replace(/\/+$/, "");
  for (const pattern of KNOWN_BAD_SUFFIXES) {
    url = url.replace(pattern, "");
  }
  return url;
}

export const SUPABASE_URL = normalizeSupabaseUrl(process.env.NEXT_PUBLIC_SUPABASE_URL);

export const SUPABASE_ANON_KEY = (process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "").trim();

export function hasSupabaseConfig() {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}
