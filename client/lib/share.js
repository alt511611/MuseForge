/**
 * Reading a published share page, from the server.
 *
 * WHY EVERY FETCH HERE IS SERVER-SIDE. The share page's whole job is to be
 * crawlable and to render a social card. Both are read by clients that run no
 * JavaScript, so the title, the logline, the poster and the JSON-LD have to be
 * in the HTML that comes back from the first request — a client-side fetch
 * would hand Googlebot and Twitter an empty page with a spinner.
 *
 * WHY IT IS CACHED FOR AN HOUR. A share is immutable in everything the page
 * shows: the film is finished before it can be published. Only its EXISTENCE
 * changes, when the owner revokes it, and an hour is the longest a revoked page
 * may stay up — short enough to be an honest promise, long enough that a link
 * doing numbers on Reddit does not turn every visitor into an API call.
 */

import { API_BASE } from "./apiBase";
import { SITE_URL } from "./seo";

/** Where a slug lives on this site. One URL per share — see UNLOCALIZED_PREFIXES. */
export const sharePath = (slug) => `/s/${slug}`;
export const shareUrl = (slug) => `${SITE_URL}/s/${slug}`;
export const embedPath = (slug) => `/embed/${slug}`;
export const embedUrl = (slug) => `${SITE_URL}/embed/${slug}`;

/** Seconds a share page and the gallery are cached for. */
export const SHARE_REVALIDATE = 3600;

/** Absolute URL for a video path the API returned site-relative. */
export function resolveShareVideo(share) {
  const path = share?.video_url || "";
  if (!path) return "";
  return path.startsWith("http") ? path : `${API_BASE}${path}`;
}

/**
 * One published share, or null.
 *
 * Returns null for a 404 (revoked, or never existed) AND for an unreachable
 * API, which the page turns into notFound(). A share page that cannot read its
 * share has nothing to render either way, and a 500 would ask Google to keep
 * the URL and come back — which is right for an outage and wrong for a revoke.
 * The difference is not knowable from here; the conservative answer is the one
 * that does not leave a dead page indexed.
 */
export async function getShare(slug) {
  if (!API_BASE || !slug) return null;
  try {
    const res = await fetch(`${API_BASE}/api/share/${encodeURIComponent(slug)}`, {
      next: { revalidate: SHARE_REVALIDATE },
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data && data.slug ? data : null;
  } catch {
    return null;
  }
}

/**
 * The most recently published shares. Feeds the sitemap.
 *
 * Fails open with an empty list: a sitemap that cannot reach the API must
 * still list the static routes rather than 500 and take the whole file down.
 */
export async function getRecentShares(limit = 200) {
  if (!API_BASE) return [];
  try {
    const res = await fetch(`${API_BASE}/api/shares?limit=${limit}`, {
      next: { revalidate: SHARE_REVALIDATE },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data?.items) ? data.items : [];
  } catch {
    return [];
  }
}

/** "48s" / "1m 48s" — the only place a duration is formatted. */
export function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (!total) return "";
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m ? `${m}m ${s}s` : `${s}s`;
}

/** ISO-8601 duration, which is the only form schema.org accepts. */
export function isoDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (!total) return undefined;
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `PT${m ? `${m}M` : ""}${s}S`;
}

/** The iframe a viewer copies. Kept here so the page and the API agree on it. */
export function embedSnippet(slug, aspect = "16:9") {
  const [w, h] = aspect === "9:16" ? [405, 720] : aspect === "1:1" ? [600, 600] : [720, 405];
  return (
    `<iframe src="${embedUrl(slug)}" width="${w}" height="${h}" ` +
    `frameborder="0" allow="autoplay; fullscreen; picture-in-picture" ` +
    `allowfullscreen title="MuseForge"></iframe>`
  );
}
