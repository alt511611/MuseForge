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

/**
 * Resolve a job's video URL for the browser.
 * - Absolute http(s) URLs (e.g. Supabase signed URLs) are used as-is.
 * - Relative paths like `/api/jobs/{id}/video` are prefixed with API_BASE.
 * - Disk paths (`/tmp/...`) or other junk fall back to the streaming endpoint.
 */
export function resolveJobVideoUrl(videoUrl, jobId) {
  const fallback = `${API_BASE}/api/jobs/${jobId}/video`;
  if (!videoUrl || typeof videoUrl !== "string") return fallback;
  if (videoUrl.startsWith("http://") || videoUrl.startsWith("https://")) return videoUrl;
  if (videoUrl.startsWith("/api/")) return `${API_BASE}${videoUrl}`;
  return fallback;
}
