"""Recover the MuAPI tickets a crashed process left behind -- collect only.

A job's pipeline call (``jobs.py``'s ``run_generation_job`` /
``run_continue_from_script_job``) is one long-running async task. If the
process dies while that task is mid-poll on a provider call, the job's
in-memory state is gone, but the ticket MuAPI issued for that call was
already written to Supabase the instant it was issued -- see
``Job.mark_provider_job_submitted`` and the ``on_provider_job_submitted``
wiring in ``jobs.py``. This script is what turns that record back into
either a finished asset or an honest failure, instead of a silent loss.

WHAT THIS DOES NOT DO: resume the rest of that job's pipeline. MuseForge's
pipeline is one long async task per job, not a set of resumable stages a
script can re-enter partway through (contrast with a file-per-stage design,
where any stage can be re-run against files a previous stage left behind).
Recovering a scene's video here does not re-drive lip sync, assembly, or
delivery for that job -- it only makes sure a paid-for file is not lost, and
tells an operator plainly when a job needs to be re-run from the top instead
of silently retried (which would double-charge the provider).

Usage::

    python -m tools.recover_orphaned_jobs                  # all stale jobs
    python -m tools.recover_orphaned_jobs --job-id <id>     # one job
    python -m tools.recover_orphaned_jobs --max-age-minutes 5 --dry-run
"""

import argparse
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from tools.muapi_client import MuAPIClient, MuAPIError, extract_output_urls

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

#: A ticket younger than this is assumed to still be in its own process's
#: poll loop -- recovering it here would race that loop's own completion.
DEFAULT_MAX_AGE_MINUTES = 15


def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }


async def _fetch_candidate_jobs(job_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """RUNNING/QUEUED jobs from Supabase -- the only copy that survives a restart.

    The in-memory JobStore is exactly what a crash loses, so recovery has to
    read the same durable row ``Job.mark_provider_job_submitted`` wrote to.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        logger.error("SUPABASE_URL/SUPABASE_SERVICE_KEY not configured; nothing to recover from.")
        return []
    params: Dict[str, str] = {"select": "id,status,result,updated_at"}
    if job_id:
        params["id"] = f"eq.{job_id}"
    else:
        params["status"] = "in.(running,queued)"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/jobs", params=params, headers=_sb_headers()
        )
        resp.raise_for_status()
        rows = resp.json()
    return rows if isinstance(rows, list) else []


async def _patch_job_result(job_id: str, result: Dict[str, Any]) -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.patch(
            f"{SUPABASE_URL}/rest/v1/jobs",
            params={"id": f"eq.{job_id}"},
            json={"result": result},
            headers={**_sb_headers(), "Content-Type": "application/json", "Prefer": "return=minimal"},
        )
        resp.raise_for_status()


def _is_stale(submitted_at: str, max_age_minutes: int) -> bool:
    try:
        submitted = datetime.fromisoformat(submitted_at)
    except (TypeError, ValueError):
        return True
    if submitted.tzinfo is None:
        submitted = submitted.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - submitted > timedelta(minutes=max_age_minutes)


async def recover_job(
    row: Dict[str, Any], client: MuAPIClient, max_age_minutes: int, dry_run: bool
) -> None:
    job_id = row.get("id")
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    pending = result.get("_pending_provider_jobs")
    if not isinstance(pending, dict) or not pending:
        return

    changed = False
    for key, ticket in list(pending.items()):
        if not isinstance(ticket, dict):
            continue
        request_id = ticket.get("request_id")
        submitted_at = ticket.get("submitted_at", "")
        if not request_id:
            continue
        if not _is_stale(submitted_at, max_age_minutes):
            logger.info("job=%s key=%s ticket=%s still fresh, leaving it alone", job_id, key, request_id)
            continue

        try:
            status_data = await client.check_status_once(request_id)
        except MuAPIError as exc:
            logger.warning("job=%s key=%s: could not check %s: %s", job_id, key, request_id, exc)
            continue

        status = status_data.get("status", "")
        if status == "completed":
            outputs = extract_output_urls(status_data)
            logger.info(
                "job=%s key=%s stage=%s: RECOVERED -- %s finished with %d file(s): %s",
                job_id, key, ticket.get("stage"), request_id, len(outputs), outputs,
            )
            if not dry_run:
                pending.pop(key, None)
                changed = True
        elif status in ("failed", "cancelled"):
            logger.error(
                "job=%s key=%s stage=%s: %s ended in status=%r -- this money is "
                "gone; the job needs a full re-run, not a silent retry.",
                job_id, key, ticket.get("stage"), request_id, status,
            )
            if not dry_run:
                pending.pop(key, None)
                changed = True
        else:
            logger.info(
                "job=%s key=%s stage=%s: %s is still %r, nothing to do yet",
                job_id, key, ticket.get("stage"), request_id, status or "unknown",
            )

    if changed and not dry_run:
        result["_pending_provider_jobs"] = pending
        await _patch_job_result(job_id, result)
        logger.info("job=%s: pending-ticket record updated in Supabase", job_id)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", default=None, help="Recover only this job.")
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=DEFAULT_MAX_AGE_MINUTES,
        help="Only act on tickets older than this (default: %(default)s).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without writing anything back.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    rows = await _fetch_candidate_jobs(args.job_id)
    if not rows:
        logger.info("No candidate jobs found.")
        return

    client = MuAPIClient(os.environ.get("MUAPI_KEY", ""))
    for row in rows:
        await recover_job(row, client, args.max_age_minutes, args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
