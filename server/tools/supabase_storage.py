"""Upload finished videos to Supabase Storage and return a signed URL.

Uses the same httpx + service-key pattern as server/auth.py / server/jobs.py.
No extra SDKs (no boto3, no supabase-py).

Demo mode / missing env → return the local path unchanged (no network).
Upload failure → log and return the local path (fail-open).

Nothing used to leave this bucket. upload_video writes, and the only other
Supabase delete in the codebase (jobs._sb_delete) removes the job ROW, which
strands its object with nothing left pointing at it. The bucket therefore grew
by every delivered job forever, and a deployment met its plan quota at 1.12 GB
-- roughly a dozen masters, because a 1080p CRF 18 scene is 15-25 MB. Hence
delete_expired_videos below.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
STORAGE_BUCKET = os.environ.get("MUSEFORGE_STORAGE_BUCKET", "videos")


def _int_env(name: str, default: int) -> int:
    """An integer setting, falling back to ``default`` on anything unusable.

    Bare ``int(os.environ.get(...))`` is wrong for every knob a deployment
    declares without a value, because "leave this alone" is written as an
    EMPTY STRING rather than as an absent variable -- so the default never
    applies and int() raises. At module scope that is not a bad setting, it is
    a server that will not import.

    Every platform this has run on does it: Render's blueprint wrote
    ``value: ""``, and Coolify's environment editor stores ``NAME=`` the same
    way. Same shape as jobs._stale_timeout_minutes.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r, using %s", name, raw, default)
        return default


SIGNED_URL_TTL_SECONDS = _int_env("MUSEFORGE_SIGNED_URL_TTL", 7 * 24 * 3600)

#: Grace on TOP of the signed-URL TTL before an object may be deleted.
#:
#: The retention window is DERIVED from SIGNED_URL_TTL_SECONDS rather than
#: configured beside it, and that coupling is the entire safety argument:
#: upload_video signs for exactly that long, nothing here ever re-signs an
#: object, so past the TTL the video is already unreachable -- the re-export
#: path meets the dead URL and answers 502 (api._resolve_job_source_video). Its bytes
#: are pure quota. Two independent numbers would mean that the day someone
#: raises the TTL to thirty days, retention carries on deleting at seven and
#: starts destroying videos whose URLs still work.
#:
#: The grace sits outside the TTL because an object is written before its URL
#: is signed, and neither clock is ours. A window ending exactly at the TTL
#: could catch a URL with seconds left on it.
RETENTION_GRACE_SECONDS = _int_env("MUSEFORGE_STORAGE_RETENTION_GRACE_SECONDS", 24 * 3600)

#: Sweep interval. The bucket only grows when a job completes, so there is
#: nothing to gain from looking more often than jobs.orphan_cleanup_loop does.
RETENTION_INTERVAL_SECONDS = _int_env("MUSEFORGE_STORAGE_RETENTION_INTERVAL_SECONDS", 3600)

#: One page of a bucket listing.
_LIST_PAGE_SIZE = 100

#: Storage caps a bulk delete at 1000 keys and separately bounds the request by
#: total key length; 100 stays well inside both.
_DELETE_BATCH_SIZE = 100

#: Refuses to walk a bucket forever. Only reachable if `offset` stopped paging,
#: in which case every page comes back full and identical -- an infinite loop
#: of writes against someone else's API is not an acceptable failure mode for a
#: background task.
_MAX_LIST_PAGES = 500


def _is_demo() -> bool:
    return os.environ.get("MUSEFORGE_DEMO", "").lower() in ("1", "true", "yes")


def _storage_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _headers(content_type: Optional[str] = None) -> dict:
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    if content_type:
        h["Content-Type"] = content_type
    return h


async def upload_video(local_path: str, job_id: str) -> str:
    """Upload ``local_path`` to the private ``videos`` bucket as ``{job_id}.mp4``.

    Returns a signed HTTPS URL on success. In demo mode, when Supabase is not
    configured, or on any upload/sign failure, returns ``local_path`` unchanged
    (fail-open, logged).
    """
    if not local_path or not os.path.isfile(local_path):
        logger.error("upload_video: local file missing: %s", local_path)
        return local_path or ""

    if _is_demo() or not _storage_configured():
        # Match tools/muapi_uploader.py — no network in demo / local-dev.
        return local_path

    object_path = f"{job_id}.mp4"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{object_path}"
    sign_url = f"{SUPABASE_URL}/storage/v1/object/sign/{STORAGE_BUCKET}/{object_path}"

    try:
        file_bytes = Path(local_path).read_bytes()
        async with httpx.AsyncClient(timeout=120.0) as client:
            upload_resp = await client.post(
                upload_url,
                content=file_bytes,
                headers={
                    **_headers("video/mp4"),
                    "x-upsert": "true",
                },
            )
            upload_resp.raise_for_status()

            sign_resp = await client.post(
                sign_url,
                json={"expiresIn": SIGNED_URL_TTL_SECONDS},
                headers=_headers("application/json"),
            )
            sign_resp.raise_for_status()
            data = sign_resp.json()
            signed = data.get("signedURL") or data.get("signedUrl") or ""
            if not signed:
                raise ValueError(f"No signedURL in response: {data}")

            if signed.startswith("http"):
                return signed
            # Supabase returns a path like /object/sign/...?token=...
            if not signed.startswith("/"):
                signed = "/" + signed
            if signed.startswith("/storage/v1"):
                return f"{SUPABASE_URL}{signed}"
            return f"{SUPABASE_URL}/storage/v1{signed}"

    except Exception as exc:
        logger.error(
            "upload_video failed for job %s (keeping local path): %s",
            job_id,
            exc,
        )
        return local_path


# ── Retention ─────────────────────────────────────────────────────────────────


def retention_enabled() -> bool:
    """Whether the sweep may delete. Empty = ON.

    ON by default because a bucket nothing prunes is what put a deployment over
    its quota, and because the objects it removes cannot be opened by anyone
    anyway. A deployment that has promised its customers a longer life for
    their videos should raise MUSEFORGE_SIGNED_URL_TTL -- which moves the
    retention window with it -- rather than switching this off and going back
    to a bucket that only grows.
    """
    return os.environ.get("MUSEFORGE_STORAGE_RETENTION", "").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def retention_seconds() -> int:
    """How old an object must be before deleting it can take nothing away."""
    return max(0, SIGNED_URL_TTL_SECONDS) + max(0, RETENTION_GRACE_SECONDS)


def _parse_ts(value: object) -> Optional[datetime]:
    """Parse a Storage timestamptz (ISO-8601) into an aware UTC datetime."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _expired_object_names(client: httpx.AsyncClient, cutoff: datetime) -> List[str]:
    """Every object in the bucket created before ``cutoff``.

    Walks the whole bucket rather than sorting by created_at and stopping at
    the first survivor. The early exit is only correct while the sort is
    actually applied, and if it ever silently were not, the walk would stop at
    the first young object and never reach the old ones behind it -- retention
    would quietly do nothing. A full walk costs a handful of extra requests an
    hour and cannot be wrong in that direction.
    """
    names: List[str] = []
    offset = 0

    for _ in range(_MAX_LIST_PAGES):
        resp = await client.post(
            f"{SUPABASE_URL}/storage/v1/object/list/{STORAGE_BUCKET}",
            json={"prefix": "", "limit": _LIST_PAGE_SIZE, "offset": offset},
            headers=_headers("application/json"),
        )
        resp.raise_for_status()
        page = resp.json()
        if not isinstance(page, list) or not page:
            return names

        for obj in page:
            if not isinstance(obj, dict):
                continue
            name = obj.get("name")
            if not name or not isinstance(name, str):
                continue
            created = _parse_ts(obj.get("created_at"))
            if created is None:
                # An unreadable timestamp is not evidence of age, and the only
                # thing this list feeds is a delete.
                logger.warning("Retention: %r has no usable created_at, keeping it", name)
                continue
            if created < cutoff:
                names.append(name)

        if len(page) < _LIST_PAGE_SIZE:
            return names
        offset += len(page)

    logger.warning(
        "Retention: stopped after %d pages of %s; sweeping what was found so far",
        _MAX_LIST_PAGES,
        STORAGE_BUCKET,
    )
    return names


async def _delete_objects(client: httpx.AsyncClient, names: List[str]) -> int:
    """Remove ``names`` from the bucket in batches. Returns how many went."""
    removed = 0
    for start in range(0, len(names), _DELETE_BATCH_SIZE):
        batch = names[start : start + _DELETE_BATCH_SIZE]
        # httpx's .delete() takes no body and this endpoint requires one.
        resp = await client.request(
            "DELETE",
            f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}",
            json={"prefixes": batch},
            headers=_headers("application/json"),
        )
        resp.raise_for_status()
        removed += len(batch)
    return removed


async def delete_expired_videos() -> int:
    """Drop bucket objects whose signed URL has certainly expired.

    Returns how many were removed; 0 whenever it cannot or should not run.

    Deliberately leaves public.jobs alone. The row is the customer's history of
    what they made and what it cost them, and it was already pointing at a URL
    that had stopped resolving before this ran -- deleting the bytes changes
    nothing they can see. Erasing the record would.
    """
    if _is_demo() or not _storage_configured() or not retention_enabled():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=retention_seconds())

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            names = await _expired_object_names(client, cutoff)
            if not names:
                return 0
            removed = await _delete_objects(client, names)
    except Exception as exc:
        logger.error("Storage retention sweep failed: %s", exc)
        return 0

    logger.info(
        "Storage retention removed %d object(s) from %s older than %s",
        removed,
        STORAGE_BUCKET,
        cutoff.isoformat(),
    )
    return removed


async def storage_retention_loop() -> None:
    """Background task: hold the videos bucket to its retention window."""
    while True:
        try:
            await delete_expired_videos()
        except Exception as exc:
            logger.error("Storage retention loop error: %s", exc)
        await asyncio.sleep(RETENTION_INTERVAL_SECONDS)
