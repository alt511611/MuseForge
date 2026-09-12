"""Where a series lives between its episodes.

One row per series, holding the whole bible as JSON (see interfaces/series).
One row rather than a table of episodes joined to a table of cast, because
every read of this object is a read of ALL of it -- commissioning episode
forty needs the cast, the locks, the rolling summary and the last
cliffhanger in the same breath -- and a join that is always fully materialised
is a document with extra steps.

Fails the way the character library fails: an unconfigured Supabase keeps the
series in memory (local, demo, tests), and an error is logged and answered
with "not found" rather than raised, because a series is a convenience wrapped
around jobs that are stored independently. Losing the wrapper must never lose
an episode.
"""

from __future__ import annotations

import logging
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

import httpx

from interfaces.series import Series, absorb, from_dict

logger = logging.getLogger(__name__)

TABLE = "series"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get(
    "SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
)

#: The fallback store, keyed by user. Present for the same reason the
#: character library has one: the whole product runs offline in demo mode, and
#: a feature that needs a database to be exercised is a feature nobody tests.
_memory: Dict[str, List[Dict[str, Any]]] = defaultdict(list)


def _configured() -> bool:
    """Read at call time, not at import: the tests and the demo path set the
    environment after this module is already loaded."""
    return bool(
        os.environ.get("SUPABASE_URL")
        and (
            os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        )
    )


def _headers() -> dict:
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get(
        "SUPABASE_SERVICE_ROLE_KEY", ""
    )
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _base_url() -> str:
    return os.environ.get("SUPABASE_URL", "").rstrip("/")


def _row(user_id: str, series: Series) -> Dict[str, Any]:
    """A series as the table stores it.

    ``title`` and ``episode_count`` are columns as well as fields inside the
    bible: a listing has to be able to order and count without parsing every
    document it did not ask for.
    """
    return {
        "id": series.id,
        "user_id": user_id,
        "title": series.title,
        "premise": series.premise,
        "episode_count": len(series.episodes),
        "bible": series.as_dict(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _from_row(row: Mapping[str, Any]) -> Series:
    bible = row.get("bible")
    series = from_dict(bible if isinstance(bible, Mapping) else {})
    # The columns win over the document for the two fields that exist in both:
    # a rename that updated the column and failed to rewrite the JSON should
    # surface as the new title, not as a series that silently reverted.
    series.id = str(row.get("id") or series.id)
    series.title = str(row.get("title") or series.title)
    series.premise = str(row.get("premise") or series.premise)
    return series


async def create(user_id: str, series: Series) -> Series:
    """Store a new series and hand it back with its id filled in."""
    series.id = series.id or str(uuid.uuid4())
    row = _row(user_id, series)
    row["created_at"] = datetime.now(timezone.utc).isoformat()

    if not _configured():
        _memory[user_id].insert(0, row)
        return series
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{_base_url()}/rest/v1/{TABLE}", json=row, headers=_headers()
            )
            if resp.status_code >= 400:
                logger.error("series insert failed: %s", resp.text[:300])
    except Exception as exc:
        logger.error("series insert error: %s", exc)
    return series


async def list_for(user_id: str) -> List[Series]:
    if not _configured():
        return [_from_row(row) for row in _memory.get(user_id, [])]
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{_base_url()}/rest/v1/{TABLE}",
                params={
                    "user_id": f"eq.{user_id}",
                    "select": "id,title,premise,episode_count,bible,created_at",
                    "order": "created_at.desc",
                },
                headers=_headers(),
            )
            if resp.status_code >= 400:
                logger.error("series list failed: %s", resp.text[:300])
                return []
            data = resp.json()
            return [_from_row(row) for row in data if isinstance(row, Mapping)]
    except Exception as exc:
        logger.error("series list error: %s", exc)
        return []


async def get(user_id: str, series_id: str) -> Optional[Series]:
    if not _configured():
        row = next(
            (r for r in _memory.get(user_id, []) if r.get("id") == series_id), None
        )
        return _from_row(row) if row else None
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                f"{_base_url()}/rest/v1/{TABLE}",
                params={
                    "id": f"eq.{series_id}",
                    "user_id": f"eq.{user_id}",
                    "select": "id,title,premise,episode_count,bible,created_at",
                },
                headers=_headers(),
            )
            if resp.status_code >= 400:
                logger.error("series get failed: %s", resp.text[:300])
                return None
            data = resp.json()
            rows = [row for row in data if isinstance(row, Mapping)]
            return _from_row(rows[0]) if rows else None
    except Exception as exc:
        logger.error("series get error: %s", exc)
        return None


async def save(user_id: str, series: Series) -> Series:
    """Write a series back. Never raises: see the module docstring."""
    row = _row(user_id, series)
    if not _configured():
        stored = _memory.get(user_id, [])
        for index, existing in enumerate(stored):
            if existing.get("id") == series.id:
                row["created_at"] = existing.get("created_at")
                stored[index] = row
                return series
        stored.insert(0, row)
        return series
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.patch(
                f"{_base_url()}/rest/v1/{TABLE}",
                params={"id": f"eq.{series.id}", "user_id": f"eq.{user_id}"},
                json={
                    key: value
                    for key, value in row.items()
                    if key not in ("id", "user_id")
                },
                headers=_headers(),
            )
            if resp.status_code >= 400:
                logger.error("series save failed: %s", resp.text[:300])
    except Exception as exc:
        logger.error("series save error: %s", exc)
    return series


async def delete(user_id: str, series_id: str) -> bool:
    if not _configured():
        before = len(_memory.get(user_id, []))
        _memory[user_id] = [
            row for row in _memory.get(user_id, []) if row.get("id") != series_id
        ]
        return len(_memory[user_id]) < before
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.delete(
                f"{_base_url()}/rest/v1/{TABLE}",
                params={"id": f"eq.{series_id}", "user_id": f"eq.{user_id}"},
                headers=_headers(),
            )
            return resp.status_code < 400
    except Exception as exc:
        logger.error("series delete error: %s", exc)
        return False


async def record_episode(
    user_id: str,
    series_id: str,
    number: int,
    job_id: str,
    result: Mapping[str, Any],
) -> Optional[Series]:
    """Fold a finished episode into its series and store the result.

    Called from the job that made it, once, on the way to COMPLETED. Returns
    None when the series is gone (deleted mid-render, or never stored), which
    is not an error: the episode is a finished video in its own right and
    nothing about it depends on the series still existing.
    """
    series = await get(user_id, series_id)
    if not series:
        return None
    return await save(user_id, absorb(series, number, job_id, result))


def reserve_episode(series: Series, job_id: str) -> int:
    """Claim the next episode number before the render starts.

    Claimed up front so two episodes commissioned a second apart cannot both
    be number seven -- the number is part of the brief the script is written
    against ("THIS IS EPISODE 7"), so it has to exist before there is a script.
    The placeholder is replaced by the real record when the episode lands.
    """
    from interfaces.series import Episode

    number = series.next_number
    series.episodes.append(Episode(number=number, job_id=job_id, status="running"))
    return number
