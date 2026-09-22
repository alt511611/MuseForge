"""Every scene's foley failed, and they failed together, which is one failure.

DELIVERED JOB 4631cc44-d30, a three-scene drama. The foley stage opened at
09:04:16 and reported:

    09:07:52 WARNING Foley failed for scene 2, continuing without it:
             MuAPI job timed out after 200.0s
    09:07:53 WARNING Foley failed for scene 0, continuing without it: ...
    09:07:54 WARNING Foley failed for scene 1, continuing without it: ...

Three scenes, three timeouts, 216 / 217 / 218 seconds after the stage began --
every one of them having waited out the entire poll budget without finishing.
The drama shipped with dialogue and score over a silent picture, which is the
degradation this stage is designed for, so nothing else in the job said a word
about it.

Failures that land within two seconds of each other are not three independent
failures. They are one queue, and this stage built it twice over:

* `_generate_foley` submitted every scene at once -- a bare `asyncio.gather`
  over the scene list with nothing between it and the provider.
* The budget those queued jobs were measured against was 100 polls at 2s. 200
  seconds: the tightest wait of any MuAPI stage in this repo, against lip
  sync's 480, Kling's 600, music's 300 and the voice prober's 240. Nothing
  wrote down why foley, alone, should wait a third as long as everything else
  for eleven seconds of audio.

So the budget stops a queued job being abandoned, and the bound stops the
queue forming. Raising only the first would have paid for the queue rather
than avoided it.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines import idea2video as pipeline  # noqa: E402
from pipelines.idea2video import (  # noqa: E402
    DEFAULT_FOLEY_CONCURRENCY,
    _foley_concurrency,
)
from tools import muapi_client, muapi_sfx_generator as sfx  # noqa: E402


# --- the budget ---------------------------------------------------------


def test_foley_no_longer_waits_less_than_every_other_stage(monkeypatch):
    """The 200-second ceiling is gone, and what replaced it is not a second
    unexplained number -- it is the client's own default, which is what every
    stage that never had a reason to differ already uses."""
    monkeypatch.delenv("MUSEFORGE_SFX_MAX_POLLS", raising=False)
    assert sfx._max_polls() == muapi_client.DEFAULT_MAX_POLLS
    assert sfx.SFX_POLL_INTERVAL == muapi_client.DEFAULT_POLL_INTERVAL
    waited = sfx._max_polls() * sfx.SFX_POLL_INTERVAL
    assert waited > 200.0, "this is the ceiling the delivered job died against"


def test_a_deployment_may_disagree_without_a_release(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_SFX_MAX_POLLS", "45")
    assert sfx._max_polls() == 45


def test_a_typo_in_the_budget_does_not_take_the_drama_with_it(monkeypatch):
    """This is read on the way to generating foley, and foley is the layer a
    film can most afford to lose -- losing it to a malformed environment
    variable would be the one way this module could fail a paid render."""
    monkeypatch.setenv("MUSEFORGE_SFX_MAX_POLLS", "soon")
    assert sfx._max_polls() == muapi_client.DEFAULT_MAX_POLLS


# --- the bound ----------------------------------------------------------


def test_the_bound_never_exceeds_the_scenes_there_are(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_FOLEY_CONCURRENCY", raising=False)
    assert _foley_concurrency(1) == 1
    assert _foley_concurrency(9) == DEFAULT_FOLEY_CONCURRENCY
    monkeypatch.setenv("MUSEFORGE_FOLEY_CONCURRENCY", "5")
    assert _foley_concurrency(9) == 5
    monkeypatch.setenv("MUSEFORGE_FOLEY_CONCURRENCY", "0")
    assert _foley_concurrency(9) == 1, "a bound of zero renders no foley at all"
    monkeypatch.setenv("MUSEFORGE_FOLEY_CONCURRENCY", "two")
    assert _foley_concurrency(9) == DEFAULT_FOLEY_CONCURRENCY


class _CountingGenerator:
    """Records the high-water mark of simultaneous provider calls."""

    def __init__(self):
        self.in_flight = 0
        self.peak = 0
        self.calls = 0

    async def generate_scene_sfx(self, audio_desc, duration=8.0, **kwargs):
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        self.calls += 1
        # Read before the awaits below: `self.calls` has moved on by the time
        # this coroutine resumes, so naming the file after it there gives two
        # scenes the same sound bed.
        nth = self.calls
        try:
            # Enough turns of the loop that every unbounded caller would have
            # entered before the first one leaves.
            for _ in range(4):
                await asyncio.sleep(0)
            return f"https://example.invalid/{nth}.mp3"
        finally:
            self.in_flight -= 1


@pytest.fixture
def five_scenes(monkeypatch, tmp_path):
    """A five-scene job with the provider and the duration probe stubbed."""
    counter = _CountingGenerator()
    monkeypatch.setenv("MUSEFORGE_FOLEY", "1")
    monkeypatch.setattr(pipeline, "make_sfx_generator", lambda *a, **k: counter)
    monkeypatch.setattr(pipeline, "_probe_video_duration", lambda path: 8.0)
    monkeypatch.setattr(pipeline, "_scene_emotion", lambda script: "tense")
    paths = []
    for i in range(5):
        clip = tmp_path / f"scene_{i}.mp4"
        clip.write_bytes(b"")
        paths.append(str(clip))
    scenes = [
        {"index": i, "clip_index": i, "shots": [{"audio_desc": "rain on steel"}]}
        for i in range(5)
    ]
    return counter, scenes, paths


async def _run_foley(scenes, paths):
    pipe = pipeline.Idea2VideoPipeline.__new__(pipeline.Idea2VideoPipeline)
    pipe.demo = False
    pipe.api_key = "k"
    pipe.locked_providers = set()
    return await pipe._generate_foley(scenes, paths)


@pytest.mark.asyncio
async def test_five_scenes_no_longer_reach_the_provider_at_once(
    five_scenes, monkeypatch
):
    """THE TEST THIS FILE EXISTS FOR. The delivered job put every scene on the
    wire in the same instant; the failures came back in the same instant too."""
    monkeypatch.delenv("MUSEFORGE_FOLEY_CONCURRENCY", raising=False)
    counter, scenes, paths = five_scenes
    tracks = await _run_foley(scenes, paths)
    assert counter.calls == 5, "every scene is still offered a sound bed"
    assert counter.peak <= DEFAULT_FOLEY_CONCURRENCY, (
        f"{counter.peak} scenes were submitted at once; the bound is "
        f"{DEFAULT_FOLEY_CONCURRENCY}"
    )
    assert len(tracks) == 5


@pytest.mark.asyncio
async def test_the_bound_still_overlaps_rather_than_serialising(
    five_scenes, monkeypatch
):
    """This stage is a wait on a provider, not work on this box. A bound of one
    would turn a five-scene film into five waits end to end."""
    monkeypatch.delenv("MUSEFORGE_FOLEY_CONCURRENCY", raising=False)
    counter, scenes, paths = five_scenes
    await _run_foley(scenes, paths)
    assert counter.peak > 1, "foley was serialised; the bound is not a queue"


@pytest.mark.asyncio
async def test_a_scene_that_fails_still_only_costs_its_own_sound(
    five_scenes, monkeypatch
):
    """The promise this method has always made, kept while holding a
    semaphore: a raising scene must release it and must not take the other
    four -- or the finished drama -- with it."""
    monkeypatch.delenv("MUSEFORGE_FOLEY_CONCURRENCY", raising=False)
    counter, scenes, paths = five_scenes
    original = counter.generate_scene_sfx
    # Named rather than counted: with a bound in place the order scenes reach
    # the provider is not the order they were listed in.
    scenes[2]["shots"] = [{"audio_desc": "the one that times out"}]

    async def _fail_that_one(audio_desc, duration=8.0, **kwargs):
        url = await original(audio_desc, duration=duration, **kwargs)
        if audio_desc == "the one that times out":
            raise sfx.MuAPIError("MuAPI job timed out after 480.0s")
        return url

    counter.generate_scene_sfx = _fail_that_one
    tracks = await _run_foley(scenes, paths)
    assert len(tracks) == 4
    assert counter.in_flight == 0, "the failing scene never released its slot"
