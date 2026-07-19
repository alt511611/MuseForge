"""Stale job reaper — marks orphaned queued/running Supabase rows as failed."""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.mark.asyncio
async def test_reaper_fails_stale_running_job_leaves_fresh_alone(monkeypatch):
    """A running job updated 1h ago is failed; one updated 5m ago is untouched."""
    import jobs as jobs_mod

    monkeypatch.setenv("MUSEFORGE_STALE_JOB_TIMEOUT_MINUTES", "45")
    monkeypatch.setattr(jobs_mod, "SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setattr(jobs_mod, "SUPABASE_SERVICE_KEY", "fake_key")

    now = datetime.now(timezone.utc)
    stale_id = "stale-job-1h"
    fresh_id = "fresh-job-5m"
    rows = [
        {"id": stale_id, "status": "running", "updated_at": _iso(now - timedelta(hours=1))},
        {"id": fresh_id, "status": "running", "updated_at": _iso(now - timedelta(minutes=5))},
    ]

    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = rows

    patch_resp = MagicMock()
    patch_resp.status_code = 204

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=get_resp)
    mock_client.patch = AsyncMock(return_value=patch_resp)

    with patch("jobs.httpx.AsyncClient", return_value=mock_client):
        n = await jobs_mod.reap_stale_jobs()

    assert n == 1
    assert mock_client.patch.await_count == 1
    patch_call = mock_client.patch.await_args
    # Only the stale job is patched
    assert patch_call.kwargs["params"] == {"id": f"eq.{stale_id}"}
    assert patch_call.kwargs["json"] == {
        "status": "failed",
        "error": jobs_mod.STALE_JOB_ERROR,
    }


@pytest.mark.asyncio
async def test_reaper_updates_in_memory_job_when_present(monkeypatch):
    """If a stale DB job is also in the in-memory store, mark that failed too."""
    import jobs as jobs_mod

    monkeypatch.setenv("MUSEFORGE_STALE_JOB_TIMEOUT_MINUTES", "45")
    monkeypatch.setattr(jobs_mod, "SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setattr(jobs_mod, "SUPABASE_SERVICE_KEY", "fake_key")

    now = datetime.now(timezone.utc)
    job_id = "mem-stale"
    mem_job = jobs_mod.Job(
        id=job_id,
        status=jobs_mod.JobStatus.RUNNING,
        idea="stuck",
    )
    # Old event so the live-activity skip does not apply
    mem_job.events.append(
        jobs_mod.JobEvent(
            stage="video",
            message="old",
            progress=50,
            timestamp=_iso(now - timedelta(hours=2)),
        )
    )
    jobs_mod.job_store._jobs[job_id] = mem_job

    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = [
        {"id": job_id, "status": "running", "updated_at": _iso(now - timedelta(hours=1))},
    ]
    patch_resp = MagicMock()
    patch_resp.status_code = 204

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=get_resp)
    mock_client.patch = AsyncMock(return_value=patch_resp)

    try:
        with patch("jobs.httpx.AsyncClient", return_value=mock_client):
            n = await jobs_mod.reap_stale_jobs()
        assert n == 1
        assert mem_job.status == jobs_mod.JobStatus.FAILED
        assert mem_job.error == jobs_mod.STALE_JOB_ERROR
    finally:
        jobs_mod.job_store._jobs.pop(job_id, None)


@pytest.mark.asyncio
async def test_reaper_skips_live_in_memory_job_with_recent_events(monkeypatch):
    """Actively progressing in-memory jobs are not reaped even if DB updated_at is old."""
    import jobs as jobs_mod

    monkeypatch.setenv("MUSEFORGE_STALE_JOB_TIMEOUT_MINUTES", "45")
    monkeypatch.setattr(jobs_mod, "SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setattr(jobs_mod, "SUPABASE_SERVICE_KEY", "fake_key")

    now = datetime.now(timezone.utc)
    job_id = "live-job"
    mem_job = jobs_mod.Job(id=job_id, status=jobs_mod.JobStatus.RUNNING, idea="live")
    mem_job.events.append(
        jobs_mod.JobEvent(
            stage="video",
            message="recent",
            progress=40,
            timestamp=_iso(now - timedelta(minutes=2)),
        )
    )
    jobs_mod.job_store._jobs[job_id] = mem_job

    get_resp = MagicMock()
    get_resp.status_code = 200
    get_resp.json.return_value = [
        {"id": job_id, "status": "running", "updated_at": _iso(now - timedelta(hours=1))},
    ]

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=get_resp)
    mock_client.patch = AsyncMock()

    try:
        with patch("jobs.httpx.AsyncClient", return_value=mock_client):
            n = await jobs_mod.reap_stale_jobs()
        assert n == 0
        mock_client.patch.assert_not_awaited()
        assert mem_job.status == jobs_mod.JobStatus.RUNNING
    finally:
        jobs_mod.job_store._jobs.pop(job_id, None)
