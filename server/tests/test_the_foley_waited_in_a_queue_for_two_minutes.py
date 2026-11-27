"""The foley waited in a queue for two minutes.

MMAudio runs in about three seconds. fal's request history for jobs 93be3d88
and 265209d6 shows the 154 s and 111 s "foley" stages were 90-120 s of queue
before the model started, added to the end of the job. The requests now leave
from the storyboard, while the picture renders, and what is still not back
when the picture is done gets FOLEY_DEADLINE_SECONDS.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as mod  # noqa: E402


class _Gen:
    def __init__(self, delay=0.0, fail=False):
        self.delay, self.fail = delay, fail
        self.calls = []

    async def generate_scene_sfx(self, audio_desc, duration=8.0, scene_emotion="", is_cancelled=None):
        self.calls.append({"audio_desc": audio_desc, "duration": duration})
        await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("queue")
        return f"https://cdn/foley_{len(self.calls)}.mp3"


def _pipeline(monkeypatch, gen):
    monkeypatch.setattr(mod, "is_foley_enabled", lambda: True)
    monkeypatch.setattr(mod, "make_sfx_generator", lambda *a, **k: gen)
    monkeypatch.setattr(mod, "_probe_video_duration", lambda path: 10.0)
    return mod.Idea2VideoPipeline(api_key="k", demo=False)


@pytest.mark.asyncio
async def test_the_foley_starts_from_the_storyboard_with_the_scene_s_budget(monkeypatch):
    gen = _Gen()
    pipeline = _pipeline(monkeypatch, gen)
    task = pipeline._start_foley(
        0, [{"audio_desc": "rain on steel, a low electrical hum"}], 10.0, None, asyncio.Semaphore(2)
    )
    assert await task == "https://cdn/foley_1.mp3"
    assert gen.calls[0]["audio_desc"] == "rain on steel, a low electrical hum"
    assert gen.calls[0]["duration"] == pytest.approx(10.0 + mod.FOLEY_HEAD_START_PAD_SECONDS)


@pytest.mark.asyncio
async def test_a_started_foley_is_used_and_not_asked_for_twice(monkeypatch):
    gen = _Gen()
    pipeline = _pipeline(monkeypatch, gen)
    early = {0: pipeline._start_foley(0, [{"audio_desc": "x"}], 8.0, None, asyncio.Semaphore(2))}
    tracks = await pipeline._generate_foley(
        [{"index": 0, "clip_index": 0, "shots": [{"audio_desc": "x"}]}], ["/s0.mp4"], early=early
    )
    assert tracks == [{"scene_index": 0, "audio_url": "https://cdn/foley_1.mp3"}]
    assert len(gen.calls) == 1


@pytest.mark.asyncio
async def test_a_foley_still_queued_after_the_deadline_is_left_out(monkeypatch):
    monkeypatch.setattr(mod, "FOLEY_DEADLINE_SECONDS", 0.05)
    gen = _Gen(delay=5.0)
    pipeline = _pipeline(monkeypatch, gen)
    early = {0: pipeline._start_foley(0, [{"audio_desc": "x"}], 8.0, None, asyncio.Semaphore(2))}
    tracks = await asyncio.wait_for(
        pipeline._generate_foley(
            [{"index": 0, "clip_index": 0, "shots": []}], ["/s0.mp4"], early=early
        ),
        timeout=2.0,
    )
    assert tracks == []
    assert early[0].cancelled() or early[0].done()


@pytest.mark.asyncio
async def test_a_failed_early_foley_costs_only_its_layer(monkeypatch):
    gen = _Gen(fail=True)
    pipeline = _pipeline(monkeypatch, gen)
    early = {0: pipeline._start_foley(0, [{"audio_desc": "x"}], 8.0, None, asyncio.Semaphore(2))}
    assert await pipeline._generate_foley(
        [{"index": 0, "clip_index": 0, "shots": []}], ["/s0.mp4"], early=early
    ) == []


@pytest.mark.asyncio
async def test_a_scene_with_no_head_start_is_generated_as_before(monkeypatch):
    gen = _Gen()
    pipeline = _pipeline(monkeypatch, gen)
    tracks = await pipeline._generate_foley(
        [{"index": 1, "clip_index": 0, "shots": [{"audio_desc": "wind"}]}], ["/s0.mp4"], early={}
    )
    assert tracks == [{"scene_index": 0, "audio_url": "https://cdn/foley_1.mp3"}]
    assert gen.calls[0]["duration"] == 10.0, "the finished clip's own length"


def test_demo_and_off_start_nothing(monkeypatch):
    monkeypatch.setattr(mod, "is_foley_enabled", lambda: False)
    pipeline = mod.Idea2VideoPipeline(api_key="k", demo=False)
    assert pipeline._start_foley(0, [], 8.0, None, asyncio.Semaphore(1)) is None


@pytest.mark.asyncio
async def test_the_render_hands_the_storyboard_to_the_foley(monkeypatch, tmp_path):
    """Through continue_from_script: the callback reaches script2video.run and
    the task it starts is the one the mix uses."""
    from interfaces.character import CharacterProfile, DramaScript, ScriptScene

    gen = _Gen()
    pipeline = _pipeline(monkeypatch, gen)

    async def fake_run(**kwargs):
        kwargs["on_storyboard"]([{"audio_desc": "card shuffle, a hum"}])
        return {"path": str(tmp_path / "s.mp4"), "shots": [{"audio_desc": "card shuffle, a hum"}]}

    async def nothing(*a, **k):
        return {}

    monkeypatch.setattr(pipeline, "_lock_character_portraits", nothing)
    monkeypatch.setattr(pipeline.script2video, "run", fake_run)
    seen = {}
    original = pipeline._generate_foley

    async def spy(scene_results, scene_paths, is_cancelled=None, early=None):
        seen["early"] = dict(early or {})
        return []

    monkeypatch.setattr(pipeline, "_generate_foley", spy)
    script = DramaScript(
        title="t", logline="l",
        characters=[CharacterProfile(name="Rosa", description="woman")],
        scenes=[ScriptScene(action="Rosa deals.")],
    )
    try:
        await pipeline.continue_from_script(script, working_dir=str(tmp_path / "job"))
    except Exception:
        pass  # assembly of a fake clip may fail; the hand-off is what is checked
    assert 0 in seen.get("early", {}), "the scene's foley was started from its storyboard"
