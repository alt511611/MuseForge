"""In-memory job store with SSE progress streaming + Supabase persistence.

Design intent
─────────────
• In-memory dict → source-of-truth for live SSE streams (zero latency).
• Supabase public.jobs table → source-of-truth for durable history.
• All Supabase writes are fire-and-forget (asyncio.create_task), so a
  Supabase outage never stalls the generation pipeline.
• On GET cache-miss (post-restart) the store transparently falls back to
  a single Supabase row read.
"""

import asyncio
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = 15.0
ORPHAN_MAX_AGE_SECONDS = 24 * 3600
ORPHAN_CLEANUP_INTERVAL_SECONDS = 3600

# Stale job reaper: mark DB rows stuck in queued/running after a crash/timeout.
# Independent of orphan_cleanup_loop (disk) — both run as parallel background tasks.
STALE_JOB_REAPER_INTERVAL_SECONDS = 10 * 60  # ~10 minutes
STALE_JOB_ERROR = "Orphaned (server restart or timeout)"

# Hard upper bound for a single pipeline.run() call. Prevents silent hangs
# where no exception is raised but generation never finishes.
# Override with MUSEFORGE_PIPELINE_HARD_TIMEOUT (seconds). Default: 20 minutes.
PIPELINE_HARD_TIMEOUT_SECONDS = int(
    os.environ.get("MUSEFORGE_PIPELINE_HARD_TIMEOUT", "1200")
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
JOBS_DIR = os.environ.get("MUSEFORGE_JOBS_DIR", "/tmp/museforge_jobs")


def _stale_timeout_minutes() -> int:
    raw = os.environ.get("MUSEFORGE_STALE_JOB_TIMEOUT_MINUTES", "45")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 45


def _parse_ts(value: Any) -> Optional[datetime]:
    """Parse a Supabase timestamptz (ISO-8601) into an aware UTC datetime."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

# ── Supabase helpers ───────────────────────────────────────────────────────────

def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def _sb_row(job: "Job") -> dict:
    return {
        "id": job.id,
        "user_id": job.user_id,
        "user_email": job.user_email,
        "idea": job.idea,
        "style": job.style,
        "director_style": job.director_style,
        "aspect_ratio": job.aspect_ratio,
        "num_scenes": job.num_scenes,
        "user_requirement": job.user_requirement,
        "demo": job.demo,
        "music_enabled": job.music_enabled,
        "plan": job.plan,
        "status": job.status.value,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at,
    }


def _sb_row_to_dict(row: dict) -> dict:
    """Normalise a Supabase jobs row to the same shape as Job.to_dict()."""
    status = row.get("status", "unknown")
    return {
        "id": row.get("id"),
        "status": status,
        "idea": row.get("idea", ""),
        "style": row.get("style", "Cinematic"),
        "director_style": row.get("director_style", "cinematic_balanced"),
        "aspect_ratio": row.get("aspect_ratio", "16:9"),
        "num_scenes": row.get("num_scenes", 3),
        "demo": row.get("demo", False),
        "music_enabled": row.get("music_enabled", False),
        "plan": row.get("plan", "free"),
        "user_id": row.get("user_id"),
        "user_email": row.get("user_email"),
        "events": [],  # events are not persisted to DB
        "result": row.get("result"),
        "error": row.get("error"),
        "created_at": row.get("created_at"),
        "progress": 100 if status in ("completed", "failed", "cancelled") else 0,
    }


async def _sb_upsert(job: "Job") -> None:
    """Upsert job row into Supabase. Silently swallows all errors."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/jobs",
                json=_sb_row(job),
                headers=_sb_headers(),
            )
    except Exception as exc:
        logger.debug("Supabase upsert failed (non-fatal): %s", exc)


async def _sb_get(job_id: str) -> Optional[dict]:
    """Fetch a single job row from Supabase. Returns None on any error."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs",
                params={"id": f"eq.{job_id}", "limit": "1"},
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                },
            )
        data = resp.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as exc:
        logger.debug("Supabase get failed (non-fatal): %s", exc)
        return None


async def _sb_refund_credits(user_id: str, amount: int, job_id: str) -> None:
    """Refund credits to user after a failed/cancelled job. Fire-and-forget safe."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # Read current balance
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                params={"id": f"eq.{user_id}", "select": "credits", "limit": "1"},
                headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
            )
            data = resp.json()
            current = data[0].get("credits", 0) if isinstance(data, list) and data else 0
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
                json={"credits": current + amount},
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
            )
            await client.post(
                f"{SUPABASE_URL}/rest/v1/credit_ledger",
                json={"user_id": user_id, "amount": amount, "reason": "refund", "job_id": job_id},
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal",
                },
            )
    except Exception as exc:
        logger.debug("Credit refund failed (non-fatal): %s", exc)


async def _sb_delete(job_id: str) -> None:
    """Delete a job row from Supabase. Silently swallows all errors."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            await client.delete(
                f"{SUPABASE_URL}/rest/v1/jobs",
                params={"id": f"eq.{job_id}"},
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Prefer": "return=minimal",
                },
            )
    except Exception as exc:
        logger.debug("Supabase delete failed (non-fatal): %s", exc)


# ── Domain models ──────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobEvent:
    stage: str
    message: str
    progress: float
    data: Optional[Dict[str, Any]] = None
    seq: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "message": self.message,
            "progress": self.progress,
            "data": self.data,
            "seq": self.seq,
            "timestamp": self.timestamp,
        }


@dataclass
class Job:
    id: str
    status: JobStatus = JobStatus.QUEUED
    idea: str = ""
    style: str = "Cinematic"
    director_style: str = "cinematic_balanced"
    aspect_ratio: str = "16:9"
    num_scenes: int = 3
    user_requirement: str = ""
    demo: bool = False
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    character_image: Optional[str] = None
    character_name: str = ""
    music_enabled: bool = False
    plan: str = "free"
    events: List[JobEvent] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    _seq: int = 0
    _subscribers: List[asyncio.Queue] = field(default_factory=list, repr=False)

    def to_dict(self, include_events: bool = True) -> dict:
        return {
            "id": self.id,
            "status": self.status.value,
            "idea": self.idea,
            "style": self.style,
            "director_style": self.director_style,
            "aspect_ratio": self.aspect_ratio,
            "num_scenes": self.num_scenes,
            "demo": self.demo,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "music_enabled": self.music_enabled,
            "plan": self.plan,
            "events": [e.to_dict() for e in self.events] if include_events else [],
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "progress": self.events[-1].progress if self.events else 0,
        }


# ── JobStore ───────────────────────────────────────────────────────────────────

class JobStore:
    def __init__(self, max_jobs: int = 100):
        self._jobs: Dict[str, Job] = {}
        self._max_jobs = max_jobs
        self._lock = asyncio.Lock()

    async def create(self, **kwargs) -> Job:
        async with self._lock:
            if len(self._jobs) >= self._max_jobs:
                oldest = min(self._jobs.values(), key=lambda j: j.created_at)
                del self._jobs[oldest.id]

            job_id = str(uuid.uuid4())[:12]
            job = Job(id=job_id, **kwargs)
            self._jobs[job_id] = job

        # Fire-and-forget initial row insert (queued state)
        asyncio.create_task(_sb_upsert(job))
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    async def persist(self, job: Job) -> None:
        """Fire-and-forget upsert of the current job state to Supabase.
        Call at every status transition; never awaited in a blocking sense."""
        asyncio.create_task(_sb_upsert(job))

    async def get_or_fetch_dict(self, job_id: str) -> Optional[dict]:
        """Return job dict from memory first; fall back to Supabase on miss.
        Used by REST endpoints after a server restart to serve historical jobs."""
        job = self._jobs.get(job_id)
        if job:
            return job.to_dict()
        row = await _sb_get(job_id)
        return _sb_row_to_dict(row) if row else None

    async def delete(self, job_id: str) -> None:
        """Remove from memory and fire-and-forget delete from Supabase."""
        self._jobs.pop(job_id, None)
        asyncio.create_task(_sb_delete(job_id))

    async def emit(self, job: Job, stage: str, message: str, progress: float, data=None):
        job._seq += 1
        event = JobEvent(stage=stage, message=message, progress=progress, data=data, seq=job._seq)
        job.events.append(event)
        for queue in list(job._subscribers):
            await queue.put(event)

    async def subscribe(self, job_id: str) -> AsyncGenerator[JobEvent, None]:
        job = self.get(job_id)
        if not job:
            return

        queue: asyncio.Queue = asyncio.Queue()
        job._subscribers.append(queue)

        try:
            for event in list(job.events):
                yield event

            while job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                    yield event
                except asyncio.TimeoutError:
                    last = job.events[-1].progress if job.events else 0
                    yield JobEvent(stage="heartbeat", message="", progress=last, seq=-1)
        finally:
            if queue in job._subscribers:
                job._subscribers.remove(queue)


job_store = JobStore()


def _is_remote_storage_url(url: Optional[str]) -> bool:
    """True when the result points at a hosted (Supabase Storage) URL."""
    if not url or not isinstance(url, str):
        return False
    return url.startswith("http") and (
        "/storage/v1/" in url or "/object/sign/" in url or "supabase" in url.lower()
    )


def cleanup_working_dir(working_dir: str) -> None:
    """Remove a job's local working directory after successful remote upload."""
    if not working_dir or not os.path.isdir(working_dir):
        return
    try:
        shutil.rmtree(working_dir)
        logger.info("Cleaned working dir: %s", working_dir)
    except Exception as exc:
        logger.error("Failed to clean working dir %s: %s", working_dir, exc)


def cleanup_orphan_job_dirs() -> int:
    """Delete job dirs older than 24h that are not in the in-memory job store.

    Returns the number of directories removed.
    """
    if not os.path.isdir(JOBS_DIR):
        return 0
    active_ids = set(job_store._jobs.keys())
    cutoff = time.time() - ORPHAN_MAX_AGE_SECONDS
    removed = 0
    try:
        entries = os.listdir(JOBS_DIR)
    except OSError as exc:
        logger.error("Cannot list JOBS_DIR %s: %s", JOBS_DIR, exc)
        return 0

    for name in entries:
        path = os.path.join(JOBS_DIR, name)
        if not os.path.isdir(path):
            continue
        if name in active_ids:
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                shutil.rmtree(path)
                removed += 1
                logger.info("Removed orphan job dir: %s", path)
            except Exception as exc:
                logger.error("Failed to remove orphan dir %s: %s", path, exc)
    return removed


async def orphan_cleanup_loop() -> None:
    """Background task: periodically remove stale local job directories."""
    while True:
        try:
            n = cleanup_orphan_job_dirs()
            if n:
                logger.info("Orphan cleanup removed %d directories", n)
        except Exception as exc:
            logger.error("Orphan cleanup loop error: %s", exc)
        await asyncio.sleep(ORPHAN_CLEANUP_INTERVAL_SECONDS)


async def reap_stale_jobs() -> int:
    """Mark queued/running Supabase jobs whose updated_at is past the timeout as failed.

    Skips jobs that are still actively progressing in this process (recent SSE
    events in memory) so a long generation isn't killed just because we don't
    bump updated_at on every emit. Returns the number of jobs reaped.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return 0

    timeout_min = _stale_timeout_minutes()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_min)
    reaped = 0

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            }
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/jobs",
                params={
                    "status": "in.(queued,running)",
                    "select": "id,status,updated_at",
                },
                headers=headers,
            )
            if resp.status_code >= 400:
                logger.error("stale-job reaper list failed: %s %s", resp.status_code, resp.text[:200])
                return 0
            rows = resp.json()
            if not isinstance(rows, list):
                return 0

            patch_headers = {
                **headers,
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            }
            for row in rows:
                job_id = row.get("id")
                updated = _parse_ts(row.get("updated_at"))
                if not job_id or updated is None or updated >= cutoff:
                    continue

                # Live on this process with recent activity → leave alone.
                mem = job_store.get(job_id)
                if mem and mem.status in (JobStatus.QUEUED, JobStatus.RUNNING) and mem.events:
                    last = _parse_ts(mem.events[-1].timestamp)
                    if last is not None and last >= cutoff:
                        continue

                patch = await client.patch(
                    f"{SUPABASE_URL}/rest/v1/jobs",
                    params={"id": f"eq.{job_id}"},
                    json={"status": "failed", "error": STALE_JOB_ERROR},
                    headers=patch_headers,
                )
                if patch.status_code >= 400:
                    logger.error(
                        "stale-job reaper patch failed for %s: %s %s",
                        job_id, patch.status_code, patch.text[:200],
                    )
                    continue

                if mem and mem.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                    mem.status = JobStatus.FAILED
                    mem.error = STALE_JOB_ERROR

                reaped += 1
                logger.info("Reaped stale job %s (updated_at=%s)", job_id, row.get("updated_at"))
    except Exception as exc:
        logger.error("stale-job reaper error: %s", exc)
        return reaped

    return reaped


async def stale_job_reaper_loop() -> None:
    """Background task: periodically fail orphaned queued/running jobs in Supabase."""
    while True:
        try:
            n = await reap_stale_jobs()
            if n:
                logger.info("Stale job reaper marked %d job(s) failed", n)
        except Exception as exc:
            logger.error("Stale job reaper loop error: %s", exc)
        await asyncio.sleep(STALE_JOB_REAPER_INTERVAL_SECONDS)


# ── Generation runner ──────────────────────────────────────────────────────────

async def run_generation_job(job: Job, api_key: str):
    from pipelines.idea2video import Idea2VideoPipeline
    from pipelines.script2video import PipelineCancelled
    from tools.muapi_uploader import InvalidCharacterPhoto, upload_base64_image

    job.status = JobStatus.RUNNING
    await job_store.persist(job)  # persist RUNNING state

    working_dir = os.path.join(JOBS_DIR, job.id)

    def is_cancelled() -> bool:
        return job.status == JobStatus.CANCELLED

    async def progress_callback(stage, message, progress, data=None):
        await job_store.emit(job, stage, message, progress, data)

    character_portraits_override: Dict[str, str] = {}
    if job.character_image and job.character_name.strip():
        try:
            await progress_callback(
                "portraits", f"Uploading reference photo for {job.character_name}...", 3
            )
            uploaded_url = await upload_base64_image(
                job.character_image, api_key, demo=job.demo
            )
            character_portraits_override[job.character_name.strip()] = uploaded_url
        except InvalidCharacterPhoto as exc:
            job.error = str(exc)
            job.status = JobStatus.FAILED
            await job_store.emit(job, "error", str(exc), 0)
            await job_store.persist(job)
            return
        except Exception as exc:
            await job_store.emit(
                job, "portraits", f"Could not use uploaded photo, generating one instead: {exc}", 3
            )

    try:
        pipeline = Idea2VideoPipeline(api_key=api_key, demo=job.demo)
        result = await asyncio.wait_for(
            pipeline.run(
                idea=job.idea,
                style=job.style,
                director_style=job.director_style,
                user_requirement=job.user_requirement,
                num_scenes=job.num_scenes,
                aspect_ratio=job.aspect_ratio,
                working_dir=working_dir,
                progress_callback=progress_callback,
                is_cancelled=is_cancelled,
                character_portraits_override=character_portraits_override or None,
                music_enabled=job.music_enabled,
                plan=job.plan,
            ),
            timeout=PIPELINE_HARD_TIMEOUT_SECONDS,
        )
        if is_cancelled():
            job.status = JobStatus.CANCELLED
            await job_store.emit(job, "cancelled", "Generation cancelled", 100)
            await job_store.persist(job)
            return
        job.result = result
        job.status = JobStatus.COMPLETED
        # Persist COMPLETED + result (includes signed Storage URL when uploaded)
        await job_store.persist(job)
        await job_store.emit(job, "complete", "Generation finished", 100, result)
        # Disk cleanup only after a successful remote upload
        if not job.demo and _is_remote_storage_url((result or {}).get("video_url")):
            cleanup_working_dir(working_dir)
    except PipelineCancelled:
        job.status = JobStatus.CANCELLED
        await job_store.persist(job)
        await job_store.emit(job, "cancelled", "Generation cancelled", 100)
        # Refund credits on cancellation (user triggered) — include the music
        # surcharge if it was charged at generation time.
        if job.user_id and not job.demo:
            refund_amount = job.num_scenes + (1 if job.music_enabled else 0)
            asyncio.create_task(_sb_refund_credits(job.user_id, refund_amount, job.id))
    except asyncio.TimeoutError:
        job.status = JobStatus.FAILED
        job.error = "Generation timed out — please try again."
        await job_store.emit(job, "error", job.error, 100)
        await job_store.persist(job)
        # Refund credits — timeout is a system failure, not the user's fault.
        if job.user_id and not job.demo:
            refund_amount = job.num_scenes + (1 if job.music_enabled else 0)
            asyncio.create_task(_sb_refund_credits(job.user_id, refund_amount, job.id))
        cleanup_working_dir(working_dir)
        return
    except Exception as exc:
        job.error = str(exc)
        job.status = JobStatus.FAILED
        await job_store.persist(job)  # persist FAILED + error message
        await job_store.emit(
            job, "error", str(exc), job.events[-1].progress if job.events else 0
        )
        # Refund credits on failure so users aren't penalised for pipeline errors
        if job.user_id and not job.demo:
            refund_amount = job.num_scenes + (1 if job.music_enabled else 0)
            asyncio.create_task(_sb_refund_credits(job.user_id, refund_amount, job.id))
