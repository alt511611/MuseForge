"use client";

import { useState } from "react";
import { Share2, Check, Loader2, Globe, Link2Off } from "lucide-react";
import { useLanguage } from "../contexts/LanguageContext";
import { useAuth } from "../contexts/AuthContext";
import { API_BASE } from "../lib/apiBase";
import { tr } from "../lib/tr";
import { shareUrl } from "../lib/share";

/**
 * Publish this film, and hand back a link that actually opens.
 *
 * WHAT THIS REPLACES. The old button copied `window.location.href`. On this
 * page that is /generate/{job_id}, which middleware.js sends to /login for
 * anyone who is not the owner and next.config.js serves as noindex. So the
 * button worked and the link did not: every recipient got a sign-in wall, and
 * every crawler was told to forget the URL. Nothing in the product said so,
 * because from the sharer's side it looked identical to this.
 *
 * WHY IT ASKS FIRST. Publishing is the only action here that makes a
 * customer's work readable by strangers and indexable by Google. It is one
 * click, it is clearly labelled, and it is undone by the same button — but it
 * is never the side effect of pressing something called "Share".
 */
export default function ShareButton({ jobId }) {
  const { t } = useLanguage();
  const { getAccessToken } = useAuth();
  const [state, setState] = useState("idle"); // idle | busy | shared | copied
  const [slug, setSlug] = useState(null);
  const [error, setError] = useState(null);

  const publish = async () => {
    if (state === "busy") return;
    setError(null);
    setState("busy");
    try {
      const token = await getAccessToken();
      if (!token) throw new Error(tr(t, "share_needs_account", "Sign in to publish a share page."));
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/share`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || tr(t, "share_failed", "Could not publish this video."));

      setSlug(data.slug);
      setState("shared");

      const url = shareUrl(data.slug);
      /* navigator.share is the right thing on a phone and is also the only
         one of the two that may reject for a reason worth ignoring (the user
         dismissed the sheet). A rejection must not fall through to the
         clipboard, or dismissing the sheet silently copies anyway. */
      if (navigator.share) {
        try {
          await navigator.share({ title: tr(t, "result_share_title", "Watch this"), url });
        } catch {
          /* cancelled */
        }
      } else {
        await navigator.clipboard.writeText(url);
        setState("copied");
        setTimeout(() => setState("shared"), 2000);
      }
    } catch (err) {
      setError(err.message);
      setState("idle");
    }
  };

  const unpublish = async () => {
    if (state === "busy") return;
    setError(null);
    setState("busy");
    try {
      const token = await getAccessToken();
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/share`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(tr(t, "share_revoke_failed", "Could not unpublish this video."));
      setSlug(null);
      setState("idle");
    } catch (err) {
      setError(err.message);
      setState("shared");
    }
  };

  const published = state === "shared" || state === "copied";

  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={published ? undefined : publish}
        disabled={state === "busy"}
        className="flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all hover:scale-[1.02] disabled:opacity-60"
        style={{
          backgroundColor: "var(--mf-panel)",
          border: "1px solid var(--mf-line-strong)",
          color: "var(--mf-ink-2)",
        }}
      >
        {state === "busy" ? (
          <Loader2 size={16} className="animate-spin" />
        ) : state === "copied" ? (
          <Check size={16} />
        ) : published ? (
          <Globe size={16} />
        ) : (
          <Share2 size={16} />
        )}
        {state === "copied"
          ? tr(t, "share_copied", "Copied")
          : published
          ? tr(t, "share_published", "Published")
          : tr(t, "result_share", "Share")}
      </button>

      {published && slug && (
        <>
          <a
            href={shareUrl(slug)}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[11px] truncate underline"
            style={{ color: "var(--mf-ink-3)" }}
          >
            {shareUrl(slug)}
          </a>
          <button
            onClick={unpublish}
            className="inline-flex items-center gap-1.5 text-[11px] self-start"
            style={{ color: "var(--mf-ink-3)" }}
          >
            <Link2Off size={11} />
            {tr(t, "share_unpublish", "Unpublish")}
          </button>
        </>
      )}

      {error && (
        <span className="text-[11px]" style={{ color: "var(--mf-err-soft)" }}>
          {error}
        </span>
      )}
    </div>
  );
}
