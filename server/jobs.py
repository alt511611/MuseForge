"""In-memory job store with SSE progress streaming."""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional

HEARTBEAT_INTERVAL = 15.0


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
    character_image: Optional[str] = None   # base64 data URI from file upload
    character_name: str = ""                # required alongside character_image
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
            "events": [e.to_dict() for e in self.events] if include_events else [],
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "progress": self.events[-1].progress if self.events else 0,
        }


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
            return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

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
                    # Keep the connection alive during long generation stages
                    # instead of terminating the stream after one idle window.
                    last = job.events[-1].progress if job.events else 0
                    yield JobEvent(stage="heartbeat", message="", progress=last, seq=-1)
        finally:
            if queue in job._subscribers:
                job._subscribers.remove(queue)


job_store = JobStore()

JOBS_DIR = os.environ.get("MUSEFORGE_JOBS_DIR", "/tmp/museforge_jobs")


async def run_generation_job(job: Job, api_key: str):
    from pipelines.idea2video import Idea2VideoPipeline
    from pipelines.script2video import PipelineCancelled
    from tools.muapi_uploader import InvalidCharacterPhoto, upload_base64_image

    job.status = JobStatus.RUNNING
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
            return
        except Exception as exc:
            # Non-fatal: continue without the uploaded reference rather than
            # failing the whole generation over an upload hiccup.
            await job_store.emit(
                job, "portraits", f"Could not use uploaded photo, generating one instead: {exc}", 3
            )

    try:
        pipeline = Idea2VideoPipeline(api_key=api_key, demo=job.demo)
        result = await pipeline.run(
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
        )
        if is_cancelled():
            await job_store.emit(job, "cancelled", "Generation cancelled", 100)
            return
        job.result = result
        job.status = JobStatus.COMPLETED
        await job_store.emit(job, "complete", "Generation finished", 100, result)
    except PipelineCancelled:
        job.status = JobStatus.CANCELLED
        await job_store.emit(job, "cancelled", "Generation cancelled", 100)
    except Exception as exc:
        job.error = str(exc)
        job.status = JobStatus.FAILED
        await job_store.emit(
            job, "error", str(exc), job.events[-1].progress if job.events else 0
        )
