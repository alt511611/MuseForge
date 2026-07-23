"""Outer crash handler on run_generation_job."""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_run_generation_job_pipeline_crash_logs_traceback_and_fails(
    monkeypatch, caplog
):
    import jobs as jobs_mod

    monkeypatch.setattr(jobs_mod.job_store, "persist", AsyncMock())
    monkeypatch.setattr(jobs_mod.job_store, "emit", AsyncMock())

    job = jobs_mod.Job(
        id="crash-job-1",
        idea="A story that blows up immediately",
        status=jobs_mod.JobStatus.QUEUED,
        demo=True,
        num_scenes=2,
    )

    mock_pipeline = MagicMock()
    mock_pipeline.run = AsyncMock(side_effect=RuntimeError("pipeline exploded"))

    with patch("pipelines.idea2video.Idea2VideoPipeline", return_value=mock_pipeline):
        with caplog.at_level("ERROR", logger="jobs"):
            await jobs_mod.run_generation_job(job, api_key="test-key")

    assert job.status == jobs_mod.JobStatus.FAILED
    assert job.error == "Internal error: pipeline exploded"
    jobs_mod.job_store.emit.assert_awaited()
    error_calls = [
        c for c in jobs_mod.job_store.emit.await_args_list if len(c.args) >= 2 and c.args[1] == "error"
    ]
    assert error_calls
    assert any("run_generation_job CRASHED" in r.message for r in caplog.records)
    assert any("Traceback" in r.message for r in caplog.records)
