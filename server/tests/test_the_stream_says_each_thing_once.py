"""The SSE stream, and the two races between a subscriber and the pipeline.

Attaching a subscriber and replaying the events so far were two steps, and a
job that emitted between them sent that event twice -- the page showed a stage
advance and then advance again, and a duplicated terminal event ended the
stream twice.

The other end had the mirror problem: the loop ran `while job.status is
QUEUED or RUNNING`, so the status and the final event were two separate
observations. A job that completed while the coroutine sat between them
either waited a whole heartbeat for its "complete" or never sent it.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import jobs as jobs_mod  # noqa: E402
from jobs import Job, JobStatus, job_store  # noqa: E402


@pytest.fixture
def job():
    j = Job(id="stream-job", status=JobStatus.RUNNING, num_scenes=2)
    job_store._jobs[j.id] = j
    yield j
    job_store._jobs.pop(j.id, None)


async def _drain(job_id, limit=10, timeout=2.0):
    events = []

    async def _read():
        async for event in job_store.subscribe(job_id):
            events.append(event)
            if len(events) >= limit:
                return

    try:
        await asyncio.wait_for(_read(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    return events


@pytest.mark.asyncio
async def test_an_event_emitted_while_attaching_is_sent_once(job, monkeypatch):
    monkeypatch.setattr(jobs_mod.job_store, "persist", _noop)
    await job_store.emit(job, "screenwriting", "writing", 10)

    task = asyncio.create_task(_drain(job.id, limit=3))
    await asyncio.sleep(0)
    await job_store.emit(job, "images", "framing", 40)
    await job_store.emit(job, "complete", "done", 100)
    events = await task

    stages = [e.stage for e in events]
    assert stages == ["screenwriting", "images", "complete"]
    assert len(set(e.seq for e in events)) == len(events)


@pytest.mark.asyncio
async def test_the_stream_ends_on_the_event_not_the_status(job, monkeypatch):
    """The completion is what closes it, with no heartbeat in between."""
    monkeypatch.setattr(jobs_mod.job_store, "persist", _noop)

    async def _finish():
        await asyncio.sleep(0.01)
        # The status transition and the event, in the order the pipeline does
        # them -- the window this used to fall into.
        job.status = JobStatus.COMPLETED
        await job_store.emit(job, "complete", "done", 100)

    task = asyncio.create_task(_drain(job.id, limit=5))
    await _finish()
    events = await task

    assert [e.stage for e in events] == ["complete"]


@pytest.mark.asyncio
async def test_a_failure_closes_it_too(job, monkeypatch):
    monkeypatch.setattr(jobs_mod.job_store, "persist", _noop)

    task = asyncio.create_task(_drain(job.id, limit=5))
    await asyncio.sleep(0)
    job.status = JobStatus.FAILED
    await job_store.emit(job, "error", "provider refused", 100)
    events = await task

    assert [e.stage for e in events] == ["error"]


@pytest.mark.asyncio
async def test_a_job_parked_for_approval_does_not_stream_forever(job, monkeypatch):
    """It stops waiting for a pipeline that is waiting for a human."""
    monkeypatch.setattr(jobs_mod.job_store, "persist", _noop)

    task = asyncio.create_task(_drain(job.id, limit=5))
    await asyncio.sleep(0)
    job.status = JobStatus.AWAITING_SCRIPT_APPROVAL
    await job_store.emit(job, "script_ready", "Script ready for review", 10)
    events = await task

    assert [e.stage for e in events] == ["script_ready"]


@pytest.mark.asyncio
async def test_a_subscriber_is_dropped_when_it_leaves(job, monkeypatch):
    monkeypatch.setattr(jobs_mod.job_store, "persist", _noop)

    task = asyncio.create_task(_drain(job.id, limit=1))
    await asyncio.sleep(0)
    await job_store.emit(job, "images", "framing", 40)
    await task

    assert job._subscribers == []


async def _noop(*args, **kwargs):
    return None
