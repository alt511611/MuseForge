"""Hard timeout around pipeline.run() in run_generation_job."""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_run_generation_job_hard_timeout_marks_failed(monkeypatch):
    """A hung pipeline.run() must fail the job with a clear timeout error."""
    import asyncio

    import jobs as jobs_mod

    monkeypatch.setattr(jobs_mod, "PIPELINE_HARD_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(jobs_mod, "cleanup_working_dir", lambda *_a, **_k: None)
    monkeypatch.setattr(jobs_mod.job_store, "persist", AsyncMock())
    monkeypatch.setattr(jobs_mod.job_store, "emit", AsyncMock())

    job = jobs_mod.Job(
        id="timeout-job-1",
        idea="A story that never ends",
        status=jobs_mod.JobStatus.QUEUED,
        demo=True,
        num_scenes=1,
    )

    async def _hang_forever(*_args, **_kwargs):
        await asyncio.sleep(999999)

    mock_pipeline = MagicMock()
    mock_pipeline.run = AsyncMock(side_effect=_hang_forever)

    with patch("pipelines.idea2video.Idea2VideoPipeline", return_value=mock_pipeline):
        await jobs_mod.run_generation_job(job, api_key="test-key")

    assert job.status == jobs_mod.JobStatus.FAILED
    assert job.error == "Generation timed out — please try again."
    jobs_mod.job_store.emit.assert_awaited()
    error_calls = [
        c
        for c in jobs_mod.job_store.emit.await_args_list
        if len(c.args) >= 2 and c.args[1] == "error"
    ]
    assert error_calls, "expected an error emit on timeout"
