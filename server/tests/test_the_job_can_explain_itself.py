"""Two questions a delivered drama could not answer about itself.

Both came from a real report: the operator had set MUSEFORGE_LIPSYNC_ENABLED=1
and asked for three scenes, and got a 60-second video with closed mouths.

1. Lip sync had FOUR different reasons to decline, sharing one silent
   `return []`. The video looks identical in every case, so neither the user
   nor the operator could tell "the deployment flag is off" from "the per-job
   toggle never reached the pipeline" -- and nothing was written down.

2. distribute_budget fixes the drama's total length BEFORE any provider call,
   precisely so the cost is known at charge time. That number was logged and
   never looked at again. check_master_duration is not this check: it compares
   the master against the sum of its own scene clips, so when every clip comes
   back longer than it was asked for, both sides are wrong together and it
   stays silent. Three scenes, a 30-second budget, a 60-second master, and
   nothing in the pipeline found that surprising.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.second_budget import SECONDS_PER_CREDIT  # noqa: E402
from pipelines.idea2video import check_budget_was_honoured  # noqa: E402


# ── the runtime the job was costed at ───────────────────────────────────────


def test_a_runtime_that_matches_the_budget_says_nothing():
    assert check_budget_was_honoured(3 * SECONDS_PER_CREDIT, 3) is None


def test_ordinary_overhead_is_not_reported_as_a_fault():
    """The provider rounds to whole seconds, the cold open adds a second or
    two, transitions overlap. None of that is worth a warning."""
    assert check_budget_was_honoured(3 * SECONDS_PER_CREDIT + 3.0, 3) is None


def test_the_delivered_drama_that_prompted_this_is_reported():
    """Three scenes, 30 seconds budgeted, 60.3 delivered."""
    notice = check_budget_was_honoured(60.3, 3)

    assert notice is not None
    assert "60 seconds" in notice and "30 seconds" in notice
    assert "3 scene" in notice


def test_a_film_short_of_its_budget_is_reported_as_missing_not_as_pacing():
    """Over-delivery costs the pricing model; under-delivery costs the
    customer. They are not the same sentence."""
    notice = check_budget_was_honoured(12.0, 3)

    assert notice is not None
    assert "missing" in notice


def test_it_is_logged_as_an_error_so_it_is_searchable(caplog):
    with caplog.at_level(logging.ERROR):
        check_budget_was_honoured(60.3, 3)

    assert any("does not match the budget" in r.message for r in caplog.records)


def test_nothing_to_compare_against_is_not_evidence_of_a_problem():
    assert check_budget_was_honoured(None, 3) is None
    assert check_budget_was_honoured(0.0, 3) is None
    assert check_budget_was_honoured(30.0, 0) is None


# ── why lip sync declined ───────────────────────────────────────────────────


async def _lipsync_with(pipeline, monkeypatch, **kwargs):
    async def progress(*a, **kw):
        return None

    return await pipeline._lipsync_scenes(
        scene_paths=kwargs.get("scene_paths", ["scene0.mp4"]),
        dialogue_tracks=kwargs.get(
            "dialogue_tracks", [{"scene_index": 0, "audio_url": "https://cdn/v.mp3"}]
        ),
        working_dir="/tmp",
        progress=progress,
        requested=kwargs.get("requested", True),
    )


@pytest.mark.asyncio
async def test_the_deployment_flag_being_off_is_named(monkeypatch, caplog):
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.delenv("MUSEFORGE_LIPSYNC_ENABLED", raising=False)
    pipeline = Idea2VideoPipeline("test-key")

    with caplog.at_level(logging.INFO):
        assert await _lipsync_with(pipeline, monkeypatch) == []

    assert any("MUSEFORGE_LIPSYNC_ENABLED" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_the_per_job_opt_in_being_off_is_named(monkeypatch, caplog):
    """The case the operator hits after setting the deployment flag and still
    seeing closed mouths: the flag is on, the request never asked."""
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    pipeline = Idea2VideoPipeline("test-key")

    with caplog.at_level(logging.INFO):
        assert await _lipsync_with(pipeline, monkeypatch, requested=False) == []

    assert any("not requested on this job" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_a_drama_with_no_speech_is_named(monkeypatch, caplog):
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    pipeline = Idea2VideoPipeline("test-key")

    with caplog.at_level(logging.INFO):
        assert await _lipsync_with(pipeline, monkeypatch, dialogue_tracks=[]) == []

    assert any("no dialogue tracks" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_demo_mode_stays_quiet(monkeypatch, caplog):
    """Demo runs make no provider calls by design; a line about it on every
    preview would be noise, not information."""
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    pipeline = Idea2VideoPipeline("test-key", demo=True)

    with caplog.at_level(logging.INFO):
        assert await _lipsync_with(pipeline, monkeypatch) == []

    assert not any("Lip sync" in r.message for r in caplog.records)
