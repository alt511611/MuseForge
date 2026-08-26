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

from interfaces.language import DEFAULT_LANGUAGE
from interfaces.render_eta import RenderEta, RenderPlan

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
# Pro allows up to 24 sequential scenes (~30–60+ min wall-clock); default 2h.
# Override with MUSEFORGE_PIPELINE_HARD_TIMEOUT (seconds).
PIPELINE_HARD_TIMEOUT_SECONDS = int(
    os.environ.get("MUSEFORGE_PIPELINE_HARD_TIMEOUT", "7200")
)
# Keep aligned with server/api.py. Dialogue is charged per requested scene.
DIALOGUE_EXTRA_CREDIT_COST = 1
# One scene re-shot costs what one scene cost in the first place: a retake is
# the same frame + clip generation, so pricing it below cost would make the
# button a way to buy generation at a discount.
SCENE_RETAKE_CREDIT_COST = 1
# Keep aligned with server/api.py. Lip sync is charged per scene, on top of
# dialogue, because it is a separate paid provider call per speaking scene.
LIPSYNC_EXTRA_CREDIT_COST = 1

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
JOBS_DIR = os.environ.get("MUSEFORGE_JOBS_DIR", "/tmp/museforge_jobs")


def _stale_timeout_minutes() -> int:
    # Must exceed PIPELINE_HARD_TIMEOUT so long Pro jobs aren't reaped mid-run.
    # Default 150 min (> 2h hard timeout). Override via env.
    raw = os.environ.get("MUSEFORGE_STALE_JOB_TIMEOUT_MINUTES", "150")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 150


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
        "dialogue_enabled": job.dialogue_enabled,
        "plan": job.plan,
        "status": job.status.value,
        "result": job.result,
        "error": job.error,
        "created_at": job.created_at,
    }


def public_result(result: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Strip server-side machinery from a result before it goes over the wire.

    Underscore-prefixed keys hold what the pipeline needs to resume or redo
    work -- the full script, the voice tracks, the uploaded portrait overrides.
    They are stored on the result (so they survive the Supabase round-trip a
    job row already makes) but the browser has no use for them, and _render_
    state in particular is large enough that shipping it on every status poll
    and every SSE completion event is a real cost.
    """
    if not isinstance(result, dict):
        return result
    return {k: v for k, v in result.items() if not k.startswith("_")}


def _sb_row_to_dict(row: dict) -> dict:
    """Normalise a Supabase jobs row to the same shape as Job.to_dict().

    "Same shape" is load-bearing, not decorative: this is what the client
    receives for any job the in-memory store has already evicted (a reload
    after the tab was closed, a second server instance, anything older than
    the last restart). A key that Job.to_dict() has and this does not is a
    field that silently becomes ``undefined`` on exactly those requests.

    Three of them are not columns on the jobs table at all -- language,
    lipsync_enabled and require_script_approval were deliberately kept off
    the row so no deployment needs a migration to replay. They are recovered
    from the stored RESULT, which does survive the round trip: without that,
    the generate page's cost/ETA estimate re-fetched for a resumed job quoted
    a run with no dialogue and no lip sync, i.e. the cheapest configuration,
    for what may be the most expensive one.
    """
    status = row.get("status", "unknown")
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    return {
        "id": row.get("id"),
        "status": status,
        "idea": row.get("idea", ""),
        "style": row.get("style", "Cinematic"),
        "director_style": row.get("director_style", "cinematic_balanced"),
        "aspect_ratio": row.get("aspect_ratio", "16:9"),
        "num_scenes": row.get("num_scenes", 3),
        "user_requirement": row.get("user_requirement", ""),
        "language": result.get("language") or DEFAULT_LANGUAGE,
        # Also not a column, and recovered the same way: the pipeline records
        # the mode it wrote to in the result, so a job replayed from storage
        # still reports the shape it was actually made in rather than the
        # default one.
        "narrative_mode": result.get("narrative_mode") or "cinematic",
        "demo": row.get("demo", False),
        "music_enabled": row.get("music_enabled", False),
        "dialogue_enabled": row.get("dialogue_enabled", False),
        # Intent first, evidence second. `_lipsync_enabled` is written when a
        # job parks for script approval -- before anything is rendered, which
        # is precisely when `lipsynced_scenes` cannot exist yet. Falling
        # straight through to the evidence resumed those jobs with lip sync
        # off. A scene only appears in `lipsynced_scenes` when its mouth was
        # actually driven, so it stays the right answer for a finished job
        # made before the intent was recorded.
        "lipsync_enabled": bool(
            result.get("_lipsync_enabled", result.get("lipsynced_scenes"))
        ),
        "plan": row.get("plan", "free"),
        "user_id": row.get("user_id"),
        "user_email": row.get("user_email"),
        # The flag itself is not persisted; the status is what the client acts
        # on, and a job parked awaiting approval was necessarily started with
        # it on.
        "require_script_approval": status == JobStatus.AWAITING_SCRIPT_APPROVAL.value,
        "events": [],  # events are not persisted to DB
        "result": public_result(row.get("result")),
        "error": row.get("error"),
        "created_at": row.get("created_at"),
        "progress": 100 if status in ("completed", "failed", "cancelled") else 0,
        # Nothing measured survives a restart, and Job.eta_seconds() returns
        # None for a finished job anyway. Stated explicitly so the key exists
        # in both shapes rather than being absent from one of them.
        "eta_seconds": None,
    }


async def _sb_upsert(job: "Job") -> None:
    """Upsert job row into Supabase. Never raises (fire-and-forget), but
    now actually surfaces failures instead of hiding them.

    Found via a real, paid generation that completed successfully (a real,
    playable video existed) but had ZERO row in the jobs table -- meaning
    it only ever existed in-memory and was lost forever on the next server
    restart. Root cause: this function only used logger.debug() (invisible
    at production log levels) AND never checked the response status code
    at all -- httpx doesn't raise for a non-2xx response unless you call
    raise_for_status(), so a 400 (e.g. from a schema mismatch -- this repo
    has hit that exact class of bug multiple times this session, most
    recently when music_enabled/plan columns were added) was silently
    treated as success.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/jobs",
                json=_sb_row(job),
                headers=_sb_headers(),
            )
        if resp.status_code >= 400:
            logger.error(
                "Supabase upsert FAILED for job %s: status=%s body=%s",
                job.id, resp.status_code, resp.text[:500],
            )
    except Exception as exc:
        logger.error("Supabase upsert raised an exception for job %s: %s", job.id, exc)


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
        logger.error("Supabase get failed for job %s: %s", job_id, exc)
        return None


#: How long a refunded credit stays spendable. Matches the monthly allowance
#: window in stripe_integration.CREDIT_VALIDITY_DAYS -- a refund gives back what
#: was spent, on the same terms it was sold under.
REFUND_VALIDITY_DAYS = 30


async def _sb_refund_credits(user_id: str, amount: int, job_id: str) -> None:
    """Refund credits to user after a failed/cancelled job. Fire-and-forget safe.

    Goes through grant_credits(), which issues a real credit LOT. The previous
    implementation added the amount straight onto profiles.credits -- but that
    column is only a read cache of the lot table (public.sync_credit_cache
    rewrites it from credit_lots on every grant or deduction), and
    api._get_user_credits reads the credit_balance() RPC, which sums lots and
    ignores the cache entirely. So every refund was invisible the moment it was
    written, and permanently erased by the next credit movement: a failed paid
    job cost the customer their credits twice over, which is exactly the
    outcome the loud logging below was added to catch.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or amount <= 0:
        return
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            headers = {
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
            }
            # grant_credits writes the ledger row and refreshes the cache too,
            # so a successful call needs nothing else.
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/grant_credits",
                json={
                    "p_user_id": user_id,
                    "p_amount": amount,
                    "p_reason": "refund",
                    "p_days": REFUND_VALIDITY_DAYS,
                },
                headers=headers,
            )
            if resp.status_code < 400:
                # grant_credits' ledger row carries no job_id (the RPC has no
                # such parameter), so attach one for support/audit purposes.
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/credit_ledger",
                    params={
                        "user_id": f"eq.{user_id}",
                        "reason": "eq.refund",
                        "job_id": "is.null",
                    },
                    json={"job_id": job_id},
                    headers={**headers, "Prefer": "return=minimal"},
                )
                return

            # An install that has not replayed the credit_lots migration has no
            # grant_credits(). Fall back to the old cache write so those
            # deployments keep refunding rather than silently stopping.
            logger.warning(
                "grant_credits unavailable for refund (status=%s), falling back "
                "to the profiles.credits cache: %s",
                resp.status_code,
                resp.text[:300],
            )
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/profiles",
                params={"id": f"eq.{user_id}", "select": "credits", "limit": "1"},
                headers=headers,
            )
            data = resp.json()
            current = data[0].get("credits", 0) if isinstance(data, list) and data else 0
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
                json={"credits": current + amount},
                headers={**headers, "Prefer": "return=minimal"},
            )
            await client.post(
                f"{SUPABASE_URL}/rest/v1/credit_ledger",
                json={"user_id": user_id, "amount": amount, "reason": "refund", "job_id": job_id},
                headers={**headers, "Prefer": "return=minimal"},
            )
    except Exception as exc:
        # logger.error (not .debug): a silently failed refund means the
        # user loses money twice over -- the generation failed AND they
        # never get their credits back, with zero visibility either time.
        logger.error("Credit refund FAILED for user %s, job %s, amount %s: %s", user_id, job_id, amount, exc)


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
        logger.error("Supabase delete failed for job %s: %s", job_id, exc)


# ── Domain models ──────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_SCRIPT_APPROVAL = "awaiting_script_approval"
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
    #: Remaining seconds as measured when this event was emitted, or None when
    #: the run reports nothing to measure. Rides on the event so the live
    #: countdown updates from the stream rather than from a re-poll.
    eta_seconds: Optional[int] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "message": self.message,
            "progress": self.progress,
            "data": self.data,
            "seq": self.seq,
            "eta_seconds": self.eta_seconds,
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
    # ISO-639-1 code for the drama's SPOKEN language (see interfaces/language).
    # Deliberately absent from _sb_row, like lipsync_enabled and
    # library_characters: it is only needed while the run is in flight, and
    # adding a column to the jobs table would break every deployment that has
    # not replayed the migration yet. It is recorded on the result instead,
    # which already survives the Supabase round-trip.
    language: str = "en"
    # "cinematic" or "micro_drama" -- the dramatic shape the script is written
    # to, and whether the finished cut gets a cold-open hook.
    narrative_mode: str = "cinematic"
    demo: bool = False
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    character_image: Optional[str] = None
    character_name: str = ""
    location_image: Optional[str] = None
    music_enabled: bool = False
    dialogue_enabled: bool = False
    lipsync_enabled: bool = False
    plan: str = "free"
    require_script_approval: bool = False
    # Pro-only: [{name, static_features, portrait_url}, ...]
    library_characters: List[Dict[str, Any]] = field(default_factory=list)
    events: List[JobEvent] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    _seq: int = 0
    _subscribers: List[asyncio.Queue] = field(default_factory=list, repr=False)
    #: Wall-clock profile of the run, filled in by JobStore.emit as stages
    #: change. A render is a chain of multi-minute provider calls, and until
    #: this existed "it took 24 minutes" could not be attributed to a stage
    #: without hand-subtracting timestamps out of the event log -- which does
    #: not work at all for the stages that run concurrently.
    _stage: Optional[str] = field(default=None, repr=False)
    _stage_started: float = field(default=0.0, repr=False)
    _stage_seconds: Dict[str, float] = field(default_factory=dict, repr=False)
    #: Live remaining-time tracker. Fed from every emit(), it measures this
    #: run's real scene rate instead of trusting the prior -- see
    #: interfaces/render_eta for why the constant alone was not good enough.
    _eta: RenderEta = field(default_factory=RenderEta, repr=False)

    def eta_seconds(self) -> Optional[int]:
        """Seconds until this job finishes, or None when unknowable.

        None is a real answer: a retake or a re-cut reports no scene counters,
        and showing no countdown is better than showing a made-up one.
        """
        if self.status in (
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        ):
            return 0
        if self.status == JobStatus.AWAITING_SCRIPT_APPROVAL:
            # Parked on the user, not on us. Any number here would be counting
            # down how long they take to read their own script.
            return None
        return self._eta.remaining(time.monotonic())

    def to_dict(self, include_events: bool = True) -> dict:
        return {
            "id": self.id,
            "status": self.status.value,
            "idea": self.idea,
            "style": self.style,
            "director_style": self.director_style,
            "aspect_ratio": self.aspect_ratio,
            "num_scenes": self.num_scenes,
            # Persisted on the row and served for historical jobs, so a live
            # job has to carry it too: without this the same job answers with
            # a different set of keys depending on whether this process
            # happens to still remember it.
            "user_requirement": self.user_requirement,
            "language": self.language,
            "narrative_mode": self.narrative_mode,
            "demo": self.demo,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "music_enabled": self.music_enabled,
            "dialogue_enabled": self.dialogue_enabled,
            "lipsync_enabled": self.lipsync_enabled,
            "plan": self.plan,
            "require_script_approval": self.require_script_approval,
            "events": [e.to_dict() for e in self.events] if include_events else [],
            "result": public_result(self.result),
            "error": self.error,
            "created_at": self.created_at,
            "progress": self.events[-1].progress if self.events else 0,
            # Measured, not assumed. The client shows this instead of running
            # its own extrapolation off the progress percentage, which spiked
            # every time progress stalled against wall-clock.
            "eta_seconds": self.eta_seconds(),
        }


# ── JobStore ───────────────────────────────────────────────────────────────────

class JobStore:
    def __init__(self, max_jobs: int = 100):
        self._jobs: Dict[str, Job] = {}
        self._max_jobs = max_jobs
        self._lock = asyncio.Lock()

    #: Statuses that mean a job is done and safe to drop from memory.
    _TERMINAL_STATUSES = (
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    )

    def _evict_if_full(self) -> None:
        """Make room for one more job. Caller must hold the lock."""
        if len(self._jobs) < self._max_jobs:
            return
        # Evict a FINISHED job first. Evicting purely by age drops
        # whichever job is oldest even while it is still running --
        # its SSE stream and cancel endpoint then 404 while the work
        # (and the spend) carries on invisibly.
        finished = [
            j for j in self._jobs.values()
            if j.status in self._TERMINAL_STATUSES
        ]
        pool = finished or list(self._jobs.values())
        if not finished:
            logger.warning(
                "Job store full (%s) with no finished jobs; evicting a "
                "live job — raise max_jobs if this recurs.",
                self._max_jobs,
            )
        oldest = min(pool, key=lambda j: j.created_at)
        del self._jobs[oldest.id]

    async def create(self, **kwargs) -> Job:
        async with self._lock:
            self._evict_if_full()

            job_id = str(uuid.uuid4())[:12]
            job = Job(id=job_id, **kwargs)
            self._jobs[job_id] = job

        # Fire-and-forget initial row insert (queued state)
        asyncio.create_task(_sb_upsert(job))
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    async def get_or_restore(self, job_id: str) -> Optional[Job]:
        """The Job itself, rebuilt from Supabase when memory has lost it.

        Everything a finished drama can still be asked to do -- re-export it
        at another ratio, retake a scene, re-cut the timeline, apply a global
        edit -- ran off ``get()`` alone, which only ever sees jobs this process
        has handled since it last started. The store also evicts finished jobs
        once it is full. So the post-production controls kept rendering (the
        job dict they need is served from the database quite happily) while
        every button on them answered "Job not found": a restart, a second
        instance, or a hundred jobs later was enough.

        The row carries the full result, INCLUDING the underscore-prefixed
        ``_render_state`` that a retake needs -- ``public_result`` strips that
        on the way to the browser, not on the way into storage. Restored jobs
        are put back in memory so the work that follows behaves exactly like a
        job that never left.
        """
        job = self._jobs.get(job_id)
        if job:
            return job
        row = await _sb_get(job_id)
        if not row:
            return None
        result = row.get("result") if isinstance(row.get("result"), dict) else None
        try:
            status = JobStatus(row.get("status", "completed"))
        except ValueError:
            logger.warning(
                "Job %s has unrecognised status %r in storage; not restoring.",
                job_id,
                row.get("status"),
            )
            return None
        restored = Job(
            id=row.get("id") or job_id,
            status=status,
            idea=row.get("idea", ""),
            style=row.get("style", "Cinematic"),
            director_style=row.get("director_style", "cinematic_balanced"),
            aspect_ratio=row.get("aspect_ratio", "16:9"),
            num_scenes=row.get("num_scenes", 3),
            user_requirement=row.get("user_requirement", ""),
            # Not columns on the jobs table -- recovered from the result for
            # the same reason _sb_row_to_dict recovers them.
            language=(result or {}).get("language") or DEFAULT_LANGUAGE,
            # Intent first, evidence second -- see _sb_row_to_dict. This is the
            # path that actually RESUMES a job, so reading the evidence here
            # was what dropped lip sync from every approved script that had
            # been evicted while it waited for its human.
            lipsync_enabled=bool(
                (result or {}).get(
                    "_lipsync_enabled", (result or {}).get("lipsynced_scenes")
                )
            ),
            demo=bool(row.get("demo", False)),
            user_id=row.get("user_id"),
            user_email=row.get("user_email"),
            music_enabled=bool(row.get("music_enabled", False)),
            dialogue_enabled=bool(row.get("dialogue_enabled", False)),
            plan=row.get("plan", "free"),
            result=result,
            error=row.get("error"),
            created_at=row.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )
        async with self._lock:
            # Another request may have restored (or the pipeline re-created)
            # the same job while this one was waiting on the network.
            existing = self._jobs.get(job_id)
            if existing:
                return existing
            # A restore is a job entering memory like any other, so it obeys
            # the same ceiling -- otherwise browsing old jobs would grow the
            # store without bound.
            self._evict_if_full()
            self._jobs[restored.id] = restored
        return restored

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
        self._record_stage_timing(job, stage)
        job._eta.observe(stage, data, time.monotonic())
        job._seq += 1
        event = JobEvent(
            stage=stage,
            message=message,
            progress=progress,
            data=data,
            seq=job._seq,
            # Carried on the event itself so a browser watching the SSE stream
            # gets a fresh figure without polling /api/jobs for it.
            eta_seconds=job.eta_seconds(),
        )
        job.events.append(event)
        for queue in list(job._subscribers):
            await queue.put(event)

    @staticmethod
    def _record_stage_timing(job: Job, stage: str) -> None:
        """Close out the previous stage and log how long it ran.

        Stages repeat (`storyboard` is emitted once per scene) so the times
        accumulate per stage name rather than being overwritten. `heartbeat`
        is skipped: it fires on a timer, not on progress, and would otherwise
        chop every real stage into fragments.
        """
        if stage == "heartbeat":
            return
        now = time.monotonic()
        if job._stage is not None and stage != job._stage:
            elapsed = now - job._stage_started
            job._stage_seconds[job._stage] = (
                job._stage_seconds.get(job._stage, 0.0) + elapsed
            )
            logger.info(
                "[%s] stage %r took %.1fs (running total %.1fs)",
                job.id, job._stage, elapsed, sum(job._stage_seconds.values()),
            )
        if stage != job._stage:
            job._stage = stage
            job._stage_started = now

    @staticmethod
    def log_stage_profile(job: Job) -> None:
        """One line naming where a finished run actually spent its time."""
        if not job._stage_seconds:
            return
        total = sum(job._stage_seconds.values())
        breakdown = ", ".join(
            f"{name} {secs:.0f}s ({secs / total * 100:.0f}%)"
            for name, secs in sorted(
                job._stage_seconds.items(), key=lambda kv: kv[1], reverse=True
            )
        )
        logger.info("[%s] render profile — total %.0fs: %s", job.id, total, breakdown)

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
                    # The heartbeat is the only thing that fires during the
                    # long silences — a single Kling call can run for minutes
                    # without a progress event — so it is exactly where a
                    # re-measured ETA needs to ride. Without it the countdown
                    # would only correct itself once a scene landed.
                    yield JobEvent(
                        stage="heartbeat",
                        message="",
                        progress=last,
                        seq=-1,
                        eta_seconds=job.eta_seconds(),
                    )
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

def arm_job_eta(job: Job, *, scenes: Optional[int] = None, prologue: bool = True) -> None:
    """Start the job's remaining-time clock with the shape of the work ahead.

    ``scenes`` overrides the job's own count for post-production runs, which
    re-render only the scenes they were asked to and skip the prologue
    entirely -- quoting those a fresh screenplay and a fresh cast lock would
    overstate a one-scene retake by about a minute.
    """
    from pipelines.idea2video import _scene_concurrency

    num_scenes = max(1, int(scenes if scenes is not None else job.num_scenes or 1))
    job._eta.arm(
        RenderPlan(
            num_scenes=num_scenes,
            concurrency=_scene_concurrency(num_scenes),
            music=bool(job.music_enabled),
            dialogue=bool(job.dialogue_enabled),
            lipsync=bool(job.lipsync_enabled),
            demo=bool(job.demo),
            include_prologue=prologue,
        ),
        time.monotonic(),
    )


def _job_refund_amount(job: Job) -> int:
    return (
        job.num_scenes
        + (1 if job.music_enabled else 0)
        + (
            job.num_scenes * DIALOGUE_EXTRA_CREDIT_COST
            if job.dialogue_enabled
            else 0
        )
        + (
            job.num_scenes * LIPSYNC_EXTRA_CREDIT_COST
            if job.lipsync_enabled
            else 0
        )
    )


async def _refund_undelivered_extras(job: Job, result: Dict[str, Any]) -> None:
    """Give back the credits for a paid extra the job did not deliver.

    Lip sync is charged per scene, up front, and it fails OPEN -- correctly,
    because a mouth that could not be driven is not worth failing a rendered
    film over. What was missing is the other half: job 930f11de-4b0 was billed
    for lip sync on three scenes, had all three refused by a provider account
    out of balance, and shipped closed mouths under a voice track. The job
    already says so in its warnings. It kept the credits anyway.

    Deliberately NOT a job failure. The picture cost real provider money and is
    exactly what was asked for; throwing it away to make the billing tidy would
    charge the user more, not less. This bills for what arrived.

    The condition mirrors the lip-sync term of _job_refund_amount exactly, so
    this can never hand back credits that were never taken.
    """
    if job.demo or not job.user_id or not job.lipsync_enabled:
        return
    if (result or {}).get("lipsynced_scenes"):
        return
    amount = job.num_scenes * LIPSYNC_EXTRA_CREDIT_COST
    if amount <= 0:
        return
    logger.info(
        "[%s] Lip sync was charged (%d credit(s)) and ran on no scene; "
        "refunding it.",
        job.id,
        amount,
    )
    await _sb_refund_credits(job.user_id, amount, job.id)


async def run_generation_job(job: Job, api_key: str):
    """Start a job. If require_script_approval, stop after screenwriting."""
    logger.info("run_generation_job ENTERED for job %s", job.id)
    # Bound BEFORE the try block. The outer handler below calls
    # cleanup_working_dir(working_dir); if anything above the assignment threw
    # (an import error, a Supabase hiccup in persist()), that handler raised
    # NameError while handling the original exception -- turning a legible
    # failure into a traceback that named the wrong line.
    working_dir = os.path.join(JOBS_DIR, job.id)
    try:
        from agents.screenwriter import ScriptGenerationFailed
        from pipelines.idea2video import Idea2VideoPipeline
        from pipelines.script2video import PipelineCancelled
        from tools.muapi_uploader import InvalidCharacterPhoto, upload_base64_image

        job.status = JobStatus.RUNNING
        arm_job_eta(job)
        await job_store.persist(job)  # persist RUNNING state

        def is_cancelled() -> bool:
            return job.status == JobStatus.CANCELLED

        async def progress_callback(stage, message, progress, data=None):
            await job_store.emit(job, stage, message, progress, data)

        character_portraits_override: Dict[str, str] = {}
        library_characters: List[Dict[str, Any]] = list(job.library_characters or [])
        for lib_char in library_characters:
            name = str(lib_char.get("name") or "").strip()
            url = str(lib_char.get("portrait_url") or "").strip()
            if name and url:
                character_portraits_override[name] = url

        # Portrait upload can wait until approve when script approval is on —
        # still do it here so the photo is ready when the user approves.
        if job.character_image and job.character_name.strip():
            try:
                await progress_callback(
                    "portraits", f"Uploading reference photo for {job.character_name}...", 3
                )
                uploaded_url = await upload_base64_image(
                    job.character_image, api_key, demo=job.demo
                )
                character_portraits_override[job.character_name.strip()] = uploaded_url
                # Stash for continue_from_script (character_image base64 is large;
                # keep the uploaded URL in result scratch).
                job.result = {
                    **(job.result or {}),
                    "_portraits_override": character_portraits_override,
                    "_library_characters": library_characters,
                }
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

        # Same treatment for an uploaded location photo: turn the base64 data
        # URI into a hosted URL once, here, and stash it so the approve-script
        # path can reuse it without re-uploading. Never fatal -- unlike a
        # character photo (whose whole point is "this exact face"), a failed
        # location upload just falls back to a generated plate.
        location_url: Optional[str] = None
        if job.location_image:
            try:
                await progress_callback("portraits", "Uploading set reference photo...", 3)
                location_url = await upload_base64_image(
                    job.location_image, api_key, demo=job.demo
                )
                job.result = {
                    **(job.result or {}),
                    "_location_override": location_url,
                }
            except Exception as exc:
                await progress_callback(
                    "portraits",
                    f"Could not use the uploaded set photo, generating one instead: {exc}",
                    3,
                )

        if library_characters and not (job.result or {}).get("_library_characters"):
            job.result = {
                **(job.result or {}),
                "_portraits_override": {
                    **((job.result or {}).get("_portraits_override") or {}),
                    **character_portraits_override,
                },
                "_library_characters": library_characters,
            }

        try:
            pipeline = Idea2VideoPipeline(api_key=api_key, demo=job.demo)

            if job.require_script_approval:
                script = await asyncio.wait_for(
                    pipeline.write_script_only(
                        idea=job.idea,
                        style=job.style,
                        num_scenes=job.num_scenes,
                        user_requirement=job.user_requirement,
                        progress_callback=progress_callback,
                        is_cancelled=is_cancelled,
                        preset_characters=library_characters or None,
                        language=job.language,
                        # Approve-script runs write the script that will later
                        # be voiced, so the screenwriter has to know now — by
                        # the time continue_from_script sees dialogue_enabled,
                        # the (possibly silent) script is already written and
                        # approved.
                        dialogue_enabled=job.dialogue_enabled,
                        narrative_mode=job.narrative_mode,
                    ),
                    timeout=PIPELINE_HARD_TIMEOUT_SECONDS,
                )
                if is_cancelled():
                    job.status = JobStatus.CANCELLED
                    await job_store.emit(job, "cancelled", "Generation cancelled", 100)
                    await job_store.persist(job)
                    return
                script_dict = script.model_dump() if hasattr(script, "model_dump") else dict(script)
                job.result = {
                    **(job.result or {}),
                    "script": script_dict,
                    # The job is about to stop and wait for a human, which is
                    # the one point in its life where it can be evicted from
                    # memory and restored from the row. `lipsync_enabled` is
                    # not a column, and the row reader infers it from
                    # `lipsynced_scenes` -- evidence a run ALREADY had lip
                    # sync, which is exactly what a job that has not rendered
                    # yet cannot have. So a restored job resumed with lip sync
                    # silently off, and the drama came back with the voice laid
                    # over closed mouths on a run the user had paid the
                    # per-scene surcharge for.
                    #
                    # Recorded as INTENT here, where it is still known.
                    "_lipsync_enabled": bool(job.lipsync_enabled),
                }
                job.status = JobStatus.AWAITING_SCRIPT_APPROVAL
                await job_store.persist(job)
                await job_store.emit(
                    job,
                    "script_ready",
                    "Script ready for review",
                    10,
                    {"script": script_dict},
                )
                return

            result = await asyncio.wait_for(
                pipeline.run(
                    idea=job.idea,
                    style=job.style,
                    director_style=job.director_style,
                    user_requirement=job.user_requirement,
                    num_scenes=job.num_scenes,
                    aspect_ratio=job.aspect_ratio,
                    language=job.language,
                    narrative_mode=job.narrative_mode,
                    working_dir=working_dir,
                    progress_callback=progress_callback,
                    is_cancelled=is_cancelled,
                    character_portraits_override=character_portraits_override or None,
                    music_enabled=job.music_enabled,
                    dialogue_enabled=job.dialogue_enabled,
                    lipsync_enabled=job.lipsync_enabled,
                    plan=job.plan,
                    preset_characters=library_characters or None,
                    location_image_override=location_url,
                ),
                timeout=PIPELINE_HARD_TIMEOUT_SECONDS,
            )
            if is_cancelled():
                job.status = JobStatus.CANCELLED
                await job_store.emit(job, "cancelled", "Generation cancelled", 100)
                await job_store.persist(job)
                return
            job.result = result
            # Before COMPLETED is persisted, so the balance the user sees when
            # the job lands is already the corrected one.
            await _refund_undelivered_extras(job, result)
            job.status = JobStatus.COMPLETED
            # Persist COMPLETED + result (includes signed Storage URL when uploaded)
            await job_store.persist(job)
            job_store.log_stage_profile(job)
            await job_store.emit(
                job, "complete", "Generation finished", 100, public_result(result)
            )
            # Disk cleanup only after a successful remote upload
            if not job.demo and _is_remote_storage_url((result or {}).get("video_url")):
                cleanup_working_dir(working_dir)
        except PipelineCancelled:
            job.status = JobStatus.CANCELLED
            await job_store.persist(job)
            await job_store.emit(job, "cancelled", "Generation cancelled", 100)
            # Only refund if credits were already charged (full path, not script-only).
            if job.user_id and not job.demo and not job.require_script_approval:
                asyncio.create_task(
                    _sb_refund_credits(job.user_id, _job_refund_amount(job), job.id)
                )
            cleanup_working_dir(working_dir)
        except ScriptGenerationFailed as exc:
            # No LLM wrote the script, so the render would have ignored the
            # user's idea entirely. Fail with the real reason (and refund)
            # rather than shipping a generic video -- the message is already
            # written for the user, so it is not wrapped in "Internal error".
            logger.error("Script generation failed for job %s: %s", job.id, exc)
            job.status = JobStatus.FAILED
            job.error = str(exc)
            await job_store.emit(job, "error", job.error, 100)
            await job_store.persist(job)
            if job.user_id and not job.demo and not job.require_script_approval:
                asyncio.create_task(
                    _sb_refund_credits(job.user_id, _job_refund_amount(job), job.id)
                )
            cleanup_working_dir(working_dir)
            return
        except asyncio.TimeoutError:
            job.status = JobStatus.FAILED
            job.error = "Generation timed out — please try again."
            await job_store.emit(job, "error", job.error, 100)
            await job_store.persist(job)
            if job.user_id and not job.demo and not job.require_script_approval:
                asyncio.create_task(
                    _sb_refund_credits(job.user_id, _job_refund_amount(job), job.id)
                )
            cleanup_working_dir(working_dir)
            return
    except Exception as exc:
        import traceback

        logger.error(
            "run_generation_job CRASHED before/during pipeline for "
            "job %s: %s\n%s",
            job.id,
            exc,
            traceback.format_exc(),
        )
        job.status = JobStatus.FAILED
        job.error = f"Internal error: {exc}"
        await job_store.emit(job, "error", job.error, 100)
        await job_store.persist(job)
        if job.user_id and not job.demo and not job.require_script_approval:
            asyncio.create_task(
                _sb_refund_credits(job.user_id, _job_refund_amount(job), job.id)
            )
        # A failed job's partial renders are never served -- leaving them on
        # disk fills a fixed-size container long before the 24h orphan sweep.
        cleanup_working_dir(working_dir)

async def run_regenerate_scene_job(
    job: Job,
    api_key: str,
    scene_index: int,
    director_note: str = "",
):
    """Re-shoot one scene of a finished job and splice it back in.

    The job's previous result is kept intact until the new one is complete, so
    a failed retake leaves the customer with the video they already had rather
    than nothing. On failure the single retake credit is refunded — the
    original job's credits are untouched either way.
    """
    from pipelines.idea2video import Idea2VideoPipeline, SceneRegenerationUnavailable
    from pipelines.script2video import PipelineCancelled

    previous_result = dict(job.result or {})
    job.status = JobStatus.RUNNING
    arm_job_eta(job, scenes=1, prologue=False)
    await job_store.persist(job)

    working_dir = os.path.join(JOBS_DIR, job.id)

    def is_cancelled() -> bool:
        return job.status == JobStatus.CANCELLED

    async def progress_callback(stage, message, progress, data=None):
        await job_store.emit(job, stage, message, progress, data)

    def _refund_retake() -> None:
        if job.user_id and not job.demo:
            asyncio.create_task(
                _sb_refund_credits(job.user_id, SCENE_RETAKE_CREDIT_COST, job.id)
            )

    def _restore_previous() -> None:
        """Put the finished video back. Without this, a failed retake would
        leave the job holding a half-updated result and the UI would show a
        completed video the user can no longer play."""
        job.result = previous_result
        job.status = JobStatus.COMPLETED

    try:
        pipeline = Idea2VideoPipeline(api_key=api_key, demo=job.demo)
        result = await asyncio.wait_for(
            pipeline.regenerate_scene(
                previous_result=previous_result,
                scene_index=scene_index,
                working_dir=working_dir,
                director_note=director_note,
                progress_callback=progress_callback,
                is_cancelled=is_cancelled,
            ),
            timeout=PIPELINE_HARD_TIMEOUT_SECONDS,
        )
        if is_cancelled():
            _restore_previous()
            await job_store.persist(job)
            await job_store.emit(job, "cancelled", "Retake cancelled", 100)
            _refund_retake()
            return
        job.result = result
        job.status = JobStatus.COMPLETED
        await job_store.persist(job)
        await job_store.emit(job, "complete", "Retake finished", 100, public_result(result))
    except SceneRegenerationUnavailable as exc:
        # Nothing was generated, so nothing to refund beyond the retake credit.
        _restore_previous()
        job.error = str(exc)
        await job_store.persist(job)
        await job_store.emit(job, "error", str(exc), 100)
        _refund_retake()
    except PipelineCancelled:
        _restore_previous()
        await job_store.persist(job)
        await job_store.emit(job, "cancelled", "Retake cancelled", 100)
        _refund_retake()
    except asyncio.TimeoutError:
        _restore_previous()
        job.error = "The retake timed out — your video is unchanged."
        await job_store.persist(job)
        await job_store.emit(job, "error", job.error, 100)
        _refund_retake()
    except Exception as exc:
        _restore_previous()
        job.error = f"The retake failed, your video is unchanged: {exc}"
        await job_store.persist(job)
        await job_store.emit(job, "error", job.error, 100)
        _refund_retake()


async def run_global_edit_job(
    job: Job,
    api_key: str,
    instruction: str,
    target: str,
    scene_indices: List[int],
    charged_credits: int = 0,
):
    """Apply one continuity change across every scene it affects.

    Same failure contract as a retake: the previous result is held until the
    new one is complete, so a failed edit leaves the customer with the video
    they already had, and everything charged for the edit is refunded.
    """
    from pipelines.idea2video import Idea2VideoPipeline, SceneRegenerationUnavailable
    from pipelines.script2video import PipelineCancelled

    previous_result = dict(job.result or {})
    job.status = JobStatus.RUNNING
    await job_store.persist(job)

    working_dir = os.path.join(JOBS_DIR, job.id)

    def is_cancelled() -> bool:
        return job.status == JobStatus.CANCELLED

    async def progress_callback(stage, message, progress, data=None):
        await job_store.emit(job, stage, message, progress, data)

    def _refund() -> None:
        if job.user_id and not job.demo and charged_credits:
            asyncio.create_task(
                _sb_refund_credits(job.user_id, charged_credits, job.id)
            )

    def _restore_previous() -> None:
        job.result = previous_result
        job.status = JobStatus.COMPLETED

    try:
        pipeline = Idea2VideoPipeline(api_key=api_key, demo=job.demo)
        result = await asyncio.wait_for(
            pipeline.apply_global_edit(
                previous_result=previous_result,
                instruction=instruction,
                target=target,
                working_dir=working_dir,
                scene_indices=scene_indices or None,
                progress_callback=progress_callback,
                is_cancelled=is_cancelled,
            ),
            timeout=PIPELINE_HARD_TIMEOUT_SECONDS,
        )
        if is_cancelled():
            _restore_previous()
            await job_store.persist(job)
            await job_store.emit(job, "cancelled", "Edit cancelled", 100)
            _refund()
            return
        job.result = result
        job.status = JobStatus.COMPLETED
        await job_store.persist(job)
        await job_store.emit(job, "complete", "Edit applied", 100, public_result(result))
    except SceneRegenerationUnavailable as exc:
        _restore_previous()
        job.error = str(exc)
        await job_store.persist(job)
        await job_store.emit(job, "error", str(exc), 100)
        _refund()
    except PipelineCancelled:
        _restore_previous()
        await job_store.persist(job)
        await job_store.emit(job, "cancelled", "Edit cancelled", 100)
        _refund()
    except asyncio.TimeoutError:
        _restore_previous()
        job.error = "The edit timed out — your video is unchanged."
        await job_store.persist(job)
        await job_store.emit(job, "error", job.error, 100)
        _refund()
    except Exception as exc:
        _restore_previous()
        job.error = f"The edit failed, your video is unchanged: {exc}"
        await job_store.persist(job)
        await job_store.emit(job, "error", job.error, 100)
        _refund()


async def run_timeline_edit_job(job: Job, api_key: str, timeline: List[Dict[str, Any]]):
    """Re-cut a finished job from clips that already exist.

    No credits are involved anywhere in this path: reordering, trimming and
    dropping scenes calls no generation model, so there is nothing to charge
    and nothing to refund. A failure simply restores the previous cut.
    """
    from pipelines.idea2video import Idea2VideoPipeline, SceneRegenerationUnavailable
    from pipelines.script2video import PipelineCancelled

    previous_result = dict(job.result or {})
    job.status = JobStatus.RUNNING
    await job_store.persist(job)

    working_dir = os.path.join(JOBS_DIR, job.id)

    def is_cancelled() -> bool:
        return job.status == JobStatus.CANCELLED

    async def progress_callback(stage, message, progress, data=None):
        await job_store.emit(job, stage, message, progress, data)

    def _restore_previous() -> None:
        job.result = previous_result
        job.status = JobStatus.COMPLETED

    try:
        pipeline = Idea2VideoPipeline(api_key=api_key, demo=job.demo)
        result = await asyncio.wait_for(
            pipeline.apply_timeline_edit(
                previous_result=previous_result,
                timeline=timeline,
                working_dir=working_dir,
                progress_callback=progress_callback,
                is_cancelled=is_cancelled,
            ),
            timeout=PIPELINE_HARD_TIMEOUT_SECONDS,
        )
        if is_cancelled():
            _restore_previous()
            await job_store.persist(job)
            await job_store.emit(job, "cancelled", "Re-cut cancelled", 100)
            return
        job.result = result
        job.status = JobStatus.COMPLETED
        await job_store.persist(job)
        await job_store.emit(job, "complete", "New cut ready", 100, public_result(result))
    except SceneRegenerationUnavailable as exc:
        _restore_previous()
        job.error = str(exc)
        await job_store.persist(job)
        await job_store.emit(job, "error", str(exc), 100)
    except PipelineCancelled:
        _restore_previous()
        await job_store.persist(job)
        await job_store.emit(job, "cancelled", "Re-cut cancelled", 100)
    except asyncio.TimeoutError:
        _restore_previous()
        job.error = "The re-cut timed out — your video is unchanged."
        await job_store.persist(job)
        await job_store.emit(job, "error", job.error, 100)
    except Exception as exc:
        _restore_previous()
        job.error = f"The re-cut failed, your video is unchanged: {exc}"
        await job_store.persist(job)
        await job_store.emit(job, "error", job.error, 100)


async def run_restore_take_job(
    job: Job, api_key: str, scene_index: int, take: int
):
    """Put an earlier take of one scene back into the cut.

    Same shape and the same guarantees as the re-cut it is built on: no
    generation model runs, so there is nothing to charge and nothing to
    refund, and any failure leaves the customer looking at exactly the video
    they had before.
    """
    from pipelines.idea2video import Idea2VideoPipeline, SceneRegenerationUnavailable
    from pipelines.script2video import PipelineCancelled

    previous_result = dict(job.result or {})
    job.status = JobStatus.RUNNING
    await job_store.persist(job)

    working_dir = os.path.join(JOBS_DIR, job.id)

    def is_cancelled() -> bool:
        return job.status == JobStatus.CANCELLED

    async def progress_callback(stage, message, progress, data=None):
        await job_store.emit(job, stage, message, progress, data)

    def _restore_previous() -> None:
        job.result = previous_result
        job.status = JobStatus.COMPLETED

    label = f"Take {take} of scene {scene_index + 1}"
    try:
        pipeline = Idea2VideoPipeline(api_key=api_key, demo=job.demo)
        result = await asyncio.wait_for(
            pipeline.restore_scene_take(
                previous_result=previous_result,
                scene_index=scene_index,
                take=take,
                working_dir=working_dir,
                progress_callback=progress_callback,
                is_cancelled=is_cancelled,
            ),
            timeout=PIPELINE_HARD_TIMEOUT_SECONDS,
        )
        if is_cancelled():
            _restore_previous()
            await job_store.persist(job)
            await job_store.emit(job, "cancelled", "Restore cancelled", 100)
            return
        job.result = result
        job.status = JobStatus.COMPLETED
        await job_store.persist(job)
        await job_store.emit(
            job, "complete", f"{label} restored", 100, public_result(result)
        )
    except SceneRegenerationUnavailable as exc:
        _restore_previous()
        job.error = str(exc)
        await job_store.persist(job)
        await job_store.emit(job, "error", str(exc), 100)
    except PipelineCancelled:
        _restore_previous()
        await job_store.persist(job)
        await job_store.emit(job, "cancelled", "Restore cancelled", 100)
    except asyncio.TimeoutError:
        _restore_previous()
        job.error = "Restoring the take timed out — your video is unchanged."
        await job_store.persist(job)
        await job_store.emit(job, "error", job.error, 100)
    except Exception as exc:
        _restore_previous()
        job.error = f"The take could not be restored, your video is unchanged: {exc}"
        await job_store.persist(job)
        await job_store.emit(job, "error", job.error, 100)


async def run_continue_from_script_job(job: Job, api_key: str, script_data: Dict[str, Any]):
    """Resume after script approval — charges already taken by the API layer."""
    from interfaces.character import DramaScript
    from pipelines.idea2video import Idea2VideoPipeline
    from pipelines.script2video import PipelineCancelled

    job.status = JobStatus.RUNNING
    # The screenplay is already written and approved; production starts here.
    arm_job_eta(job)
    await job_store.persist(job)

    working_dir = os.path.join(JOBS_DIR, job.id)

    def is_cancelled() -> bool:
        return job.status == JobStatus.CANCELLED

    async def progress_callback(stage, message, progress, data=None):
        await job_store.emit(job, stage, message, progress, data)

    portraits_override = None
    location_override = None
    library_characters = list(job.library_characters or [])
    if isinstance(job.result, dict):
        portraits_override = job.result.get("_portraits_override") or None
        # Uploaded once in run_generation_job's script-only phase; reuse the
        # hosted URL rather than re-uploading the (large) base64 payload.
        location_override = job.result.get("_location_override") or None
        if not library_characters:
            library_characters = list(job.result.get("_library_characters") or [])

    try:
        script = DramaScript(**script_data)
        pipeline = Idea2VideoPipeline(api_key=api_key, demo=job.demo)
        result = await asyncio.wait_for(
            pipeline.continue_from_script(
                script=script,
                style=job.style,
                director_style=job.director_style,
                user_requirement=job.user_requirement,
                aspect_ratio=job.aspect_ratio,
                language=job.language,
                narrative_mode=job.narrative_mode,
                working_dir=working_dir,
                progress_callback=progress_callback,
                is_cancelled=is_cancelled,
                character_portraits_override=portraits_override,
                music_enabled=job.music_enabled,
                dialogue_enabled=job.dialogue_enabled,
                lipsync_enabled=job.lipsync_enabled,
                plan=job.plan,
                library_characters=library_characters or None,
                location_image_override=location_override,
            ),
            timeout=PIPELINE_HARD_TIMEOUT_SECONDS,
        )
        if is_cancelled():
            job.status = JobStatus.CANCELLED
            await job_store.emit(job, "cancelled", "Generation cancelled", 100)
            await job_store.persist(job)
            if job.user_id and not job.demo:
                asyncio.create_task(
                    _sb_refund_credits(job.user_id, _job_refund_amount(job), job.id)
                )
            cleanup_working_dir(working_dir)
            return
        # Keep approved script alongside final result for the UI.
        result = {**result, "script": script_data}
        job.result = result
        job.status = JobStatus.COMPLETED
        await job_store.persist(job)
        await job_store.emit(
                job, "complete", "Generation finished", 100, public_result(result)
            )
        if not job.demo and _is_remote_storage_url((result or {}).get("video_url")):
            cleanup_working_dir(working_dir)
    except PipelineCancelled:
        job.status = JobStatus.CANCELLED
        await job_store.persist(job)
        await job_store.emit(job, "cancelled", "Generation cancelled", 100)
        if job.user_id and not job.demo:
            asyncio.create_task(
                _sb_refund_credits(job.user_id, _job_refund_amount(job), job.id)
            )
        cleanup_working_dir(working_dir)
    except asyncio.TimeoutError:
        job.status = JobStatus.FAILED
        job.error = "Generation timed out — please try again."
        await job_store.emit(job, "error", job.error, 100)
        await job_store.persist(job)
        if job.user_id and not job.demo:
            asyncio.create_task(
                _sb_refund_credits(job.user_id, _job_refund_amount(job), job.id)
            )
        cleanup_working_dir(working_dir)
    except Exception as exc:
        job.error = str(exc)
        job.status = JobStatus.FAILED
        await job_store.persist(job)
        await job_store.emit(
            job, "error", str(exc), job.events[-1].progress if job.events else 0
        )
        if job.user_id and not job.demo:
            asyncio.create_task(
                _sb_refund_credits(job.user_id, _job_refund_amount(job), job.id)
            )
        cleanup_working_dir(working_dir)
