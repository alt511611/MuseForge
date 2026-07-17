// Single source of truth for the backend base URL. Import this everywhere
// instead of reading process.env.NEXT_PUBLIC_API_URL directly — having that
// duplicated across many files is exactly how some call sites ended up
// missing the prefix (and how a trailing slash silently caused
// "https://api.example.com//api/generate" double-slash URLs).
//
// Trailing slash is stripped so `${API_BASE}/api/xyz` never produces a
// double slash regardless of whether the env var was set with or without
// one (e.g. both "https://api.example.com" and "https://api.example.com/"
// work correctly).
export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/+$/, "");
