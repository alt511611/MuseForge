"""A finished job must keep working after the process that made it forgets it.

The in-memory job store is the only thing the post-production endpoints ever
looked in, and it holds at most `max_jobs` jobs and nothing at all across a
restart. Meanwhile the browser happily loads any job from storage. So the
re-export / retake / re-cut / global-edit controls kept rendering on a page
whose every button answered "Job not found" — the gap between what the read
path can serve and what the write path can find.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import jobs as jobs_mod  # noqa: E402
from jobs import Job, JobStatus, JobStore, _sb_row_to_dict  # noqa: E402


def _row(**over):
    row = {
        "id": "job123",
        "status": "completed",
        "idea": "A container hums.",
        "style": "Cinematic",
        "director_style": "cinematic_balanced",
        "aspect_ratio": "16:9",
        "num_scenes": 3,
        "user_requirement": "keep it quiet",
        "demo": False,
        "music_enabled": True,
        "dialogue_enabled": True,
        "plan": "pro",
        "user_id": "user-1",
        "user_email": "a@b.c",
        "error": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "result": {
            "video_url": "https://cdn/x.mp4",
            "language": "tr",
            "lipsynced_scenes": [0, 1],
            "scenes": [{"index": 0, "clip_index": 0}],
            "_render_state": {"script": {"title": "T"}},
        },
    }
    row.update(over)
    return row


# --- the two job shapes must agree -----------------------------------------


def test_a_stored_job_serialises_to_the_same_shape_as_a_live_one():
    """Any key Job.to_dict() has and _sb_row_to_dict() lacks is a field that
    silently becomes undefined for every job served from storage."""
    live = Job(id="job123").to_dict()
    stored = _sb_row_to_dict(_row())

    assert set(live) == set(stored), set(live) ^ set(stored)


def test_stored_job_recovers_the_fields_that_are_not_columns():
    stored = _sb_row_to_dict(_row())

    # Not columns on the jobs table — read back off the result instead.
    assert stored["language"] == "tr"
    assert stored["lipsync_enabled"] is True
    assert stored["user_requirement"] == "keep it quiet"


def test_a_run_without_lipsync_does_not_claim_it():
    stored = _sb_row_to_dict(_row(result={"video_url": "x", "lipsynced_scenes": []}))

    assert stored["lipsync_enabled"] is False


def test_the_wire_shape_still_hides_server_machinery():
    """Recovering fields from the result must not start shipping _render_state
    to the browser — it is large and sent on every poll."""
    stored = _sb_row_to_dict(_row())

    assert "_render_state" not in stored["result"]


# --- restoring the job itself ----------------------------------------------


@pytest.mark.asyncio
async def test_a_forgotten_job_is_restored_from_storage(monkeypatch):
    store = JobStore()

    async def fake_get(job_id):
        return _row(id=job_id)

    monkeypatch.setattr(jobs_mod, "_sb_get", fake_get)

    job = await store.get_or_restore("job123")

    assert job is not None
    assert job.status is JobStatus.COMPLETED
    assert job.plan == "pro"
    assert job.language == "tr"
    assert job.lipsync_enabled is True
    # A retake reads this; public_result() strips it on the way OUT to the
    # browser, not on the way in from storage.
    assert job.result["_render_state"]["script"]["title"] == "T"
    # Restored into memory, so the work that follows behaves like a live job.
    assert store.get("job123") is job


@pytest.mark.asyncio
async def test_memory_wins_and_storage_is_not_consulted(monkeypatch):
    store = JobStore()
    live = Job(id="job123", status=JobStatus.RUNNING)
    store._jobs["job123"] = live

    async def fail(job_id):  # pragma: no cover - must never run
        raise AssertionError("storage was queried for a job already in memory")

    monkeypatch.setattr(jobs_mod, "_sb_get", fail)

    assert await store.get_or_restore("job123") is live


@pytest.mark.asyncio
async def test_an_unknown_job_still_reports_missing(monkeypatch):
    store = JobStore()

    async def fake_get(job_id):
        return None

    monkeypatch.setattr(jobs_mod, "_sb_get", fake_get)

    assert await store.get_or_restore("nope") is None


@pytest.mark.asyncio
async def test_a_row_with_an_unknown_status_is_not_restored(monkeypatch):
    """Better to 404 than to hand the pipeline a job in a state it cannot
    reason about."""
    store = JobStore()

    async def fake_get(job_id):
        return _row(status="teleported")

    monkeypatch.setattr(jobs_mod, "_sb_get", fake_get)

    assert await store.get_or_restore("job123") is None


@pytest.mark.asyncio
async def test_restoring_respects_the_store_ceiling(monkeypatch):
    """Browsing old jobs must not grow the store without bound."""
    store = JobStore(max_jobs=2)
    store._jobs["a"] = Job(id="a", status=JobStatus.COMPLETED, created_at="2020")
    store._jobs["b"] = Job(id="b", status=JobStatus.COMPLETED, created_at="2021")

    async def fake_get(job_id):
        return _row(id=job_id)

    monkeypatch.setattr(jobs_mod, "_sb_get", fake_get)

    await store.get_or_restore("job123")

    assert len(store._jobs) == 2
    assert "a" not in store._jobs, "the oldest finished job should have gone"
    assert "job123" in store._jobs


# --- the endpoints that were dead ends -------------------------------------


def test_post_production_endpoints_can_reach_a_stored_job():
    """Guards the wiring, not the handler: each of these used job_store.get()
    alone, which cannot see a job this process did not create."""
    import inspect

    import api as _api

    for handler in (
        _api.export_job_format,
        _api.approve_script,
        _api.regenerate_scene,
        _api.global_edit,
        _api.timeline_edit,
    ):
        source = inspect.getsource(handler)
        assert "get_or_restore" in source, handler.__name__
