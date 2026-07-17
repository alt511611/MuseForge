// Single source of truth for Supabase's public URL/key, mirroring
// lib/apiBase.js's reasoning: reading process.env.NEXT_PUBLIC_SUPABASE_URL
// directly in 4 different files meant no single place guarded against a
// pasted-in trailing slash or stray whitespace (a very easy mistake when
// copy-pasting into Vercel's env var UI). A trailing slash here can make
// the Supabase client construct malformed request paths internally,
// surfacing as "Invalid path specified in request URL".
export const SUPABASE_URL = (process.env.NEXT_PUBLIC_SUPABASE_URL || "")
  .trim()
  .replace(/\/+$/, "");

export const SUPABASE_ANON_KEY = (process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "").trim();

export function hasSupabaseConfig() {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);
}
