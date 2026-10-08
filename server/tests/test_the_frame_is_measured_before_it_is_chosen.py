"""Phase 0 of best-of-N frame selection: measure, never act.

A take is built from ONE unchecked opening frame, and the frame costs $0.04
while the take built on it costs ~$0.72. Before paying for a second candidate
the pipeline has to know how often the first one is bad -- so one frame is
scored against the portraits it was drawn from and the verdict is logged.
Nothing is regenerated, and the judge may fail without anyone noticing.
"""

import asyncio
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interfaces import frame_choice
from test_a_scene_is_one_take import (
    _FakeMultishotGenerator,
    _three_shots,
    _two_hander,
    _wire,
)
from tools import frame_judge

GOOD = {"identity": 3, "outfit": 3, "setting": 3, "face_readable": 3, "cast_closed": 3}


# --------------------------------------------------------------------------
# The verdict is pure
# --------------------------------------------------------------------------

def test_a_different_face_would_be_rejected():
    assert frame_choice.would_reject({**GOOD, "identity": 1}) is True


def test_a_mouth_that_cannot_be_seen_would_be_rejected():
    """It cannot be lip-synced, and no later stage can put the mouth back."""
    assert frame_choice.would_reject({**GOOD, "face_readable": 0}) is True


def test_a_wrong_outfit_is_weak_but_not_rejected():
    scores = {**GOOD, "outfit": 1}
    assert frame_choice.would_reject(scores) is False
    assert frame_choice.weak_dimensions(scores) == ["outfit"]


def test_no_verdict_is_not_a_pass():
    """A missing measurement must not be tallied as a good frame."""
    assert frame_choice.would_reject(None) is None
    assert frame_choice.would_reject({}) is None


def test_a_partial_reply_is_not_a_verdict():
    assert frame_choice.clean_scores({"identity": 3}) is None
    assert frame_choice.clean_scores("nonsense") is None


def test_scores_are_clamped_to_the_scale():
    assert frame_choice.clean_scores({**GOOD, "identity": 9, "outfit": -4}) == {
        **GOOD,
        "identity": 3,
        "outfit": 0,
    }


# --------------------------------------------------------------------------
# The judge is off, and fail-open
# --------------------------------------------------------------------------

def test_the_judge_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_FRAME_JUDGE", raising=False)
    assert frame_judge.is_frame_judge_enabled() is False
    monkeypatch.setenv("MUSEFORGE_FRAME_JUDGE", "1")
    assert frame_judge.is_frame_judge_enabled() is True


@pytest.mark.asyncio
async def test_no_key_means_no_score_not_a_pass():
    assert await frame_judge.judge_frame("https://f/x.png", [], "", "", "", "") is None


@pytest.mark.asyncio
async def test_an_api_failure_returns_no_score(monkeypatch):
    import anthropic

    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("network down")

    monkeypatch.setattr(anthropic, "AsyncAnthropic", Boom)
    result = await frame_judge.judge_frame(
        "https://f/x.png", ["https://f/p.png"], "woman", "red coat", "bar", "key"
    )
    assert result is None


# --------------------------------------------------------------------------
# In the pipeline
# --------------------------------------------------------------------------

async def _run_take(monkeypatch, tmp_path, judge):
    from pipelines.script2video import Script2VideoPipeline
    import pipelines.script2video as s2v_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(s2v_mod, "judge_frame", judge)

    characters = _two_hander()
    shots = _three_shots()
    shots[0].visual_desc = "Vivian Marsh deals, chips stacked"
    generator = _FakeMultishotGenerator()
    _wire(monkeypatch, tmp_path, generator, characters, shots)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    pipeline.video_gen = generator
    result = await pipeline.run(
        script="Vivian Marsh deals. Julian Voss watches.",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits={
            "Vivian Marsh": "https://cdn/vivian.png",
            "Julian Voss": "https://cdn/julian.png",
        },
        scene_duration=12,
    )
    return result, generator


@pytest.mark.asyncio
async def test_off_by_default_the_take_never_calls_the_judge(monkeypatch, tmp_path):
    monkeypatch.delenv("MUSEFORGE_FRAME_JUDGE", raising=False)
    calls = []

    async def judge(*args):
        calls.append(args)
        return None

    result, generator = await _run_take(monkeypatch, tmp_path, judge)
    assert calls == []
    assert len(generator.takes) == 1
    assert "frame_judge" not in result["shots"][0]


@pytest.mark.asyncio
async def test_a_judged_take_records_and_logs_the_verdict(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("MUSEFORGE_FRAME_JUDGE", "1")
    seen = []

    async def judge(frame, refs, desc, wardrobe, setting, key):
        seen.append((frame, list(refs)))
        return {"scores": {**GOOD, "identity": 1}, "note": "different woman"}

    with caplog.at_level(logging.INFO):
        result, generator = await _run_take(monkeypatch, tmp_path, judge)

    # Judged the frame the take was actually built on, against the portraits.
    assert seen[0][0] == generator.takes[0]["take"].start_image
    assert "https://cdn/vivian.png" in seen[0][1]
    meta = result["shots"][0]["frame_judge"]
    assert meta["identity"] == 1 and meta["would_reject"] is True
    assert "would_reject=True" in caplog.text
    # Measure only: still exactly one generation, the frame is not replaced.
    assert len(generator.takes) == 1


@pytest.mark.asyncio
async def test_a_judge_that_fails_cannot_fail_the_take(monkeypatch, tmp_path):
    monkeypatch.setenv("MUSEFORGE_FRAME_JUDGE", "1")

    async def judge(*args):
        raise RuntimeError("judge exploded")

    result, generator = await _run_take(monkeypatch, tmp_path, judge)
    assert len(generator.takes) == 1
    assert os.path.exists(result["path"])
    assert "frame_judge" not in result["shots"][0]


@pytest.mark.asyncio
async def test_a_judge_that_is_declined_leaves_no_verdict(monkeypatch, tmp_path):
    monkeypatch.setenv("MUSEFORGE_FRAME_JUDGE", "1")

    async def judge(*args):
        return None

    result, _ = await _run_take(monkeypatch, tmp_path, judge)
    assert "frame_judge" not in result["shots"][0]


@pytest.mark.asyncio
async def test_a_failed_video_does_not_leave_the_judge_running(monkeypatch, tmp_path):
    monkeypatch.setenv("MUSEFORGE_FRAME_JUDGE", "1")
    started = asyncio.Event()
    cancelled = []

    async def judge(*args):
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    from pipelines.script2video import Script2VideoPipeline
    import pipelines.script2video as s2v_mod

    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(s2v_mod, "judge_frame", judge)
    characters = _two_hander()
    shots = _three_shots()
    shots[0].visual_desc = "Vivian Marsh deals, chips stacked"
    generator = _FakeMultishotGenerator()

    async def failing_take(*a, **k):
        await started.wait()
        raise RuntimeError("video provider down")

    generator.generate_scene_take = failing_take
    _wire(monkeypatch, tmp_path, generator, characters, shots)
    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    pipeline.video_gen = generator

    with pytest.raises(RuntimeError, match="video provider down"):
        await pipeline.run(
            script="Vivian Marsh deals.",
            characters=characters,
            working_dir=str(tmp_path),
            character_portraits={"Vivian Marsh": "https://cdn/vivian.png"},
            scene_duration=12,
        )
    await asyncio.sleep(0)
    assert cancelled == [True]
