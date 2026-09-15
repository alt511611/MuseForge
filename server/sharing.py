"""A finished drama, turned into a page anyone can open.

WHY THIS EXISTS
---------------
The Share button on the results page copied `window.location.href`. That URL
is `/generate/{job_id}`, which `client/middleware.js` gates behind auth and
`next.config.js` serves with `X-Robots-Tag: noindex`. So every link a customer
has ever shared went to a sign-in wall for the recipient and to nothing at all
for a crawler. The button worked; the link did not.

This module is the other half of that button: an explicit, revocable,
owner-only decision to publish ONE job as a public page at `/s/{slug}`, plus
the narrow public projection of a job row that such a page is allowed to read.

WHAT IS PUBLISHED, AND WHAT IS NOT
----------------------------------
`PUBLIC_FIELDS` is the whole contract. What goes out is what the pipeline
WROTE about the film -- its title, its logline, its mood, its shape, its
length, its poster frame, the video itself. What stays behind is everything
about the person who made it and everything the renderer needs to redo the
work: `user_id`, `user_email`, `_render_state`, `characters` (which carry
locked portrait URLs and cast voice ids), and the job id itself.

The raw `idea` stays behind too, and that one is worth stating plainly because
it is the field a growth argument would most want: it is the only text on the
record the USER wrote, it is frequently personal ("a film about my father"),
and nobody pressing Share is thinking about it. `title` and `logline` are
model-written descriptions of the delivered film, they are unique per job, and
they are what the page needs. A prompt library is a thing this product may
well want to publish one day -- with its own opt-in, not this one.

ON THE SLUG
-----------
A share URL is a capability: anyone holding it can watch the film. It is
therefore readable-but-not-guessable -- a slug of the title so the link says
what it is when pasted into Slack, and 80 bits of randomness after it so the
set of live share pages cannot be walked. Revoking a share clears the column,
and re-sharing mints a NEW slug rather than reviving the old one; a link the
owner took back does not come back.

STORAGE
-------
Three columns on `public.jobs`, read and written with the service key. When
Supabase is not configured at all (local dev, demo mode, CI) the same calls
fall through to a process-local dict, exactly as the character library does --
the feature stays exercisable without a database, and nothing silently
pretends to have persisted.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

#: Columns the share endpoints select. Never `select=*`: the projection IS the
#: privacy boundary, and a `*` would quietly start publishing every column a
#: future migration adds to public.jobs.
ROW_FIELDS = (
    "id,share_slug,shared_at,status,style,director_style,aspect_ratio,"
    "num_scenes,demo,created_at,result"
)

#: In-memory stand-in for the three columns, keyed by job id, used only when
#: SUPABASE_URL/SUPABASE_SERVICE_KEY are unset.
_shares_mem: Dict[str, Dict[str, Any]] = {}

#: Randomness appended to every slug. 16 hex characters = 64 bits, which is
#: the same order as a Supabase signed-URL token and far past the point where
#: guessing beats asking the owner for the link.
SLUG_ENTROPY_CHARS = 16


def _configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def slugify(text: str, max_words: int = 6) -> str:
    """A short, ASCII, URL-safe stem for a title.

    Diacritics fold rather than drop, so "Gözlerin Rengi" becomes
    "gozlerin-rengi" and not "gzlerin-rengi". A title that folds away to
    nothing (CJK, Arabic, an emoji, an empty string) yields "" and the caller
    falls back to a word that is not a title -- the random half of the slug is
    what makes it work, the readable half is only a courtesy.
    """
    folded = unicodedata.normalize("NFKD", str(text or ""))
    ascii_only = folded.encode("ascii", "ignore").decode("ascii").lower()
    words = [w for w in re.split(r"[^a-z0-9]+", ascii_only) if w]
    return "-".join(words[:max_words])[:60].strip("-")


def new_slug(title: str) -> str:
    """Mint a slug for a title. Called once per share, never reused."""
    stem = slugify(title) or "scene"
    return f"{stem}-{secrets.token_hex(SLUG_ENTROPY_CHARS // 2)}"


def _first_frame(result: Dict[str, Any]) -> Optional[str]:
    """The poster: the first generated frame of the first scene that has one.

    Social cards and the `<video poster>` both need a still, and the pipeline
    never renders one separately -- but every shot records the frame it was
    animated from. Scenes are walked in order because scene 1 shot 1 is the
    image the film opens on, which is the one a link preview should show.
    """
    for scene in result.get("scenes") or []:
        for shot in (scene or {}).get("shots") or []:
            url = (shot or {}).get("frame_url")
            if isinstance(url, str) and url.startswith(("http://", "https://")):
                return url
    for url in (result.get("portraits") or {}).values():
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
    return None


def public_payload(row: Dict[str, Any]) -> Dict[str, Any]:
    """The share page's entire view of a job. See the module docstring.

    Built from an explicit key list rather than by deleting private keys from
    the row: a projection that names what goes OUT cannot be widened by adding
    a column, whereas a blocklist silently can.
    """
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    slug = row.get("share_slug")
    return {
        "slug": slug,
        "title": result.get("title") or "Untitled scene",
        "logline": result.get("logline") or "",
        "mood": result.get("mood") or "",
        "style": row.get("style") or result.get("style") or "",
        "director_style": row.get("director_style") or result.get("director_style") or "",
        "aspect_ratio": row.get("aspect_ratio") or result.get("aspect_ratio") or "16:9",
        "scene_count": result.get("scene_count") or row.get("num_scenes") or 0,
        "duration_seconds": result.get("duration_estimate") or 0,
        "language": result.get("language") or "en",
        "narrative_mode": result.get("narrative_mode") or "cinematic",
        "setting_location": result.get("setting_location") or "",
        "setting_time_of_day": result.get("setting_time_of_day") or "",
        "setting_era": result.get("setting_era") or "",
        "poster_url": _first_frame(result),
        # Always the share-scoped path, never the stored `video_url`. A
        # Supabase signed URL expires, and a page that Google has indexed
        # outlives any signature -- so the page links to an endpoint that
        # re-resolves the file on every request. It also keeps the job id off
        # the public page, which the raw URL would otherwise carry.
        "video_url": f"/api/share/{slug}/video" if slug else None,
        "demo": bool(row.get("demo")),
        "shared_at": row.get("shared_at"),
        "created_at": row.get("created_at"),
    }


# ── Reads ─────────────────────────────────────────────────────────────────────

async def _select(params: Dict[str, str]) -> List[Dict[str, Any]]:
    if not _configured():
        return []
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs",
                params={"select": ROW_FIELDS, **params},
                headers=_headers(),
            )
            if resp.status_code >= 400:
                logger.error("share select failed: %s", resp.text[:300])
                return []
            data = resp.json()
            return data if isinstance(data, list) else []
    except Exception as exc:
        logger.error("share select error: %s", exc)
        return []


async def get_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """The raw row behind a share slug, or None. Callers project it."""
    if not _configured():
        for job_id, rec in _shares_mem.items():
            if rec.get("share_slug") == slug:
                return dict(rec)
        return None
    rows = await _select({"share_slug": f"eq.{slug}", "limit": "1"})
    return rows[0] if rows else None


async def recent(limit: int = 60) -> List[Dict[str, Any]]:
    """Most recently shared first -- what the sitemap and a gallery read.

    Demo jobs are excluded. A demo render is a stand-in the pipeline produced
    without paying a provider, and a public page is a claim about what this
    product makes; the two must not be the same page.
    """
    limit = max(1, min(int(limit or 60), 500))
    if not _configured():
        rows = [r for r in _shares_mem.values() if r.get("share_slug")]
        rows.sort(key=lambda r: r.get("shared_at") or "", reverse=True)
        return [r for r in rows if not r.get("demo")][:limit]
    return await _select(
        {
            "share_slug": "not.is.null",
            "demo": "is.false",
            "order": "shared_at.desc",
            "limit": str(limit),
        }
    )


# ── Writes ────────────────────────────────────────────────────────────────────

async def _patch(job_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _configured():
        rec = _shares_mem.setdefault(job_id, {"id": job_id})
        rec.update(patch)
        return dict(rec)
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/jobs",
                params={"id": f"eq.{job_id}", "select": ROW_FIELDS},
                json=patch,
                headers=_headers(),
            )
            if resp.status_code >= 400:
                logger.error("share patch failed: %s", resp.text[:300])
                return None
            data = resp.json()
            return data[0] if isinstance(data, list) and data else None
    except Exception as exc:
        logger.error("share patch error: %s", exc)
        return None


async def share(
    job_id: str, title: str, seed_row: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """Publish a job and return its row, or None if the write failed.

    Idempotent by design: a job that already has a slug keeps it, so a user who
    presses Share twice gets one URL rather than orphaning the one they already
    pasted somewhere. Only a revoke mints a new one.

    ``seed_row`` is the caller's own view of the job (from the job store) and is
    used ONLY to populate the in-memory fallback, which has no jobs table to
    read the rest of the row back from. When Supabase is configured the stored
    row always wins -- seeding from the caller there would let a job dict that
    predates the share silently answer "not shared yet" and mint a second slug
    for a page that already exists.
    """
    existing = await _row_for(job_id)
    if existing and existing.get("share_slug"):
        return existing
    patched = await _patch(
        job_id,
        {
            "share_slug": new_slug(title),
            "shared_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    if patched is None:
        return None
    if not _configured():
        merged = {**(seed_row or {}), **(existing or {}), **patched}
        _shares_mem[job_id] = merged
        return merged
    return patched


async def revoke(job_id: str) -> bool:
    """Unpublish. The page 404s from the next request on."""
    if not _configured():
        rec = _shares_mem.get(job_id)
        if rec:
            rec["share_slug"] = None
            rec["shared_at"] = None
        return True
    return await _patch(job_id, {"share_slug": None, "shared_at": None}) is not None


async def _row_for(job_id: str) -> Optional[Dict[str, Any]]:
    if not _configured():
        rec = _shares_mem.get(job_id)
        return dict(rec) if rec else None
    rows = await _select({"id": f"eq.{job_id}", "limit": "1"})
    return rows[0] if rows else None


async def shared_job_ids() -> List[str]:
    """Every job id that currently has a share page.

    Feeds the Storage retention sweep's exemption list, which is why this one
    RAISES instead of following the fail-open convention the reads above use.
    Those return `[]` on failure because an empty gallery is a harmless
    degradation; here an empty list means "nothing is shared", and the caller
    would act on it by deleting the videos behind every live share page. A
    lookup that failed must not be able to say that.
    """
    if not _configured():
        return [j for j, rec in _shares_mem.items() if rec.get("share_slug")]
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/jobs",
            params={"select": "id", "share_slug": "not.is.null", "limit": "10000"},
            headers=_headers(),
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            raise ValueError(f"shared_job_ids: unexpected response {type(rows)}")
        return [r["id"] for r in rows if isinstance(r, dict) and r.get("id")]
