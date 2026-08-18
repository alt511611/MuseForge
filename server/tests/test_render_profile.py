"""A render is a chain of multi-minute provider calls. When one takes 24
minutes, "which stage?" has to be answerable from the logs — hand-subtracting
timestamps out of the event log does not work at all for stages that run
concurrently.
"""

import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jobs import Job, JobStore  # noqa: E402


@pytest.mark.asyncio
async def test_stage_durations_accumulate_across_repeats(monkeypatch):
    """`storyboard` is emitted once per scene, so its time must add up rather
    than each emission overwriting the last."""
    store = JobStore()
    job = Job(id="job-1")

    clock = {"t": 0.0}
    monkeypatch.setattr("jobs.time.monotonic", lambda: clock["t"])

    await store.emit(job, "screenwriting", "Writing script", 5)
    clock["t"] = 30.0
    await store.emit(job, "storyboard", "Scene 1", 10)
    clock["t"] = 50.0
    await store.emit(job, "frames", "Frame 1", 20)
    clock["t"] = 90.0
    await store.emit(job, "storyboard", "Scene 2", 30)
    clock["t"] = 110.0
    await store.emit(job, "assembly", "Splicing", 90)

    assert job._stage_seconds["screenwriting"] == 30.0
    assert job._stage_seconds["frames"] == 40.0
    # 20s for scene 1 + 20s for scene 2 — accumulated, not overwritten.
    assert job._stage_seconds["storyboard"] == 40.0


@pytest.mark.asyncio
async def test_heartbeats_do_not_fragment_a_stage(monkeypatch):
    """Heartbeats fire on a timer, not on progress. Counting them as stage
    changes would chop a long render into meaningless slivers."""
    store = JobStore()
    job = Job(id="job-2")

    clock = {"t": 0.0}
    monkeypatch.setattr("jobs.time.monotonic", lambda: clock["t"])

    await store.emit(job, "frames", "Frame 1", 20)
    clock["t"] = 60.0
    await store.emit(job, "heartbeat", "", 20)
    clock["t"] = 120.0
    await store.emit(job, "assembly", "Splicing", 90)

    assert job._stage_seconds == {"frames": 120.0}


@pytest.mark.asyncio
async def test_profile_names_the_worst_stage(monkeypatch, caplog):
    store = JobStore()
    job = Job(id="job-3")

    clock = {"t": 0.0}
    monkeypatch.setattr("jobs.time.monotonic", lambda: clock["t"])

    await store.emit(job, "screenwriting", "Writing script", 5)
    clock["t"] = 60.0
    await store.emit(job, "video", "Rendering", 50)
    clock["t"] = 1200.0
    await store.emit(job, "assembly", "Splicing", 90)

    with caplog.at_level(logging.INFO):
        store.log_stage_profile(job)

    # Read the profile RECORD, not the whole capture: every stage emitted
    # above also logs at INFO, and since the app configures logging those
    # lines are now captured too -- searching caplog.text found "screenwriting"
    # in an emit line rather than in the profile this test is about.
    profile = next(
        (r.getMessage() for r in caplog.records if "render profile" in r.getMessage()),
        None,
    )
    assert profile is not None, caplog.text
    # Worst offender first, with its share of the run.
    assert profile.index("video") < profile.index("screenwriting")
    assert "95%" in profile


def test_profile_is_silent_for_a_job_that_never_ran(caplog):
    with caplog.at_level(logging.INFO):
        JobStore.log_stage_profile(Job(id="job-4"))
    assert "render profile" not in caplog.text
