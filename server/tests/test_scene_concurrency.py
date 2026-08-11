"""Parallel scene rendering + tension-scaled shot durations.

Scene rendering is the entire cost of a job -- each scene is a multi-minute
Kling call -- and with one shot per scene the per-shot semaphore never
engaged, so scenes ran strictly in series. Scenes are independent in the
default identity mode (every scene re-anchors to the locked portrait), which
is what makes rendering them in parallel safe: the character lock does not
depend on scene order. Reference-chaining mode DOES depend on order, so it
must force concurrency back to 1 rather than silently racing.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import CharacterProfile, DramaScript  # noqa: E402
from pipelines.idea2video import (  # noqa: E402
    DEFAULT_SCENE_CONCURRENCY,
    _scene_concurrency,
    _scene_tension,
)


# --- concurrency resolution --------------------------------------------


def test_default_concurrency_is_parallel_but_bounded(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_SCENE_CONCURRENCY", raising=False)
    monkeypatch.delenv("MUSEFORGE_DYNAMIC_REFERENCE", raising=False)
    assert 1 < DEFAULT_SCENE_CONCURRENCY <= 4
    assert _scene_concurrency(5) == DEFAULT_SCENE_CONCURRENCY
    # Never more slots than scenes.
    assert _scene_concurrency(2) == 2
    assert _scene_concurrency(1) == 1


def test_env_override_and_bad_values(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_DYNAMIC_REFERENCE", raising=False)
    monkeypatch.setenv("MUSEFORGE_SCENE_CONCURRENCY", "5")
    assert _scene_concurrency(8) == 5
    monkeypatch.setenv("MUSEFORGE_SCENE_CONCURRENCY", "0")
    assert _scene_concurrency(8) == 1
    monkeypatch.setenv("MUSEFORGE_SCENE_CONCURRENCY", "banana")
    assert _scene_concurrency(8) == DEFAULT_SCENE_CONCURRENCY


def test_reference_chaining_forces_sequential(monkeypatch):
    """Chained mode feeds scene N-1's frame into scene N -- parallel rendering
    would race that handoff and silently fall back to the portrait, discarding
    the continuity the mode exists for."""
    monkeypatch.setenv("MUSEFORGE_SCENE_CONCURRENCY", "4")
    monkeypatch.setenv("MUSEFORGE_DYNAMIC_REFERENCE", "1")
    assert _scene_concurrency(8) == 1


# --- scenes really overlap, and the character lock holds ----------------


@pytest.mark.asyncio
async def test_scenes_render_in_parallel_with_locked_portraits(monkeypatch, tmp_path):
    """Two guarantees at once: scene renders overlap in time, and every scene
    still uses the LOCKED portrait as its identity reference while doing so."""
    import agents.screenwriter as screenwriter_mod
    import pipelines.idea2video as idea2video_mod
    import pipelines.script2video as script2video_mod

    monkeypatch.delenv("MUSEFORGE_DYNAMIC_REFERENCE", raising=False)
    monkeypatch.setenv("MUSEFORGE_SCENE_CONCURRENCY", "3")

    active = 0
    max_active = 0
    references_used = []

    async def fake_scene_run(self, script, characters, **kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        references_used.append(
            (kwargs["character_portraits"] or {}).get("Maya")
        )
        await asyncio.sleep(0.05)  # long enough for overlap to be observable
        active -= 1
        idx = kwargs["scene_idx"]
        path = str(tmp_path / f"scene_{idx}.mp4")
        with open(path, "wb") as f:
            f.write(b"scene")
        return {"path": path, "url": None, "shots": [{"idx": 0, "scene": idx}]}

    async def fake_write_script(self, idea, style="Cinematic", num_scenes=3,
                                user_requirement="", preset_characters=None, language="en"):
        return DramaScript(
            title="t", logline=idea,
            characters=[CharacterProfile(name="Maya", description="30s")],
            scenes=[f"Scene {i}" for i in range(num_scenes)],
        )

    async def fake_portrait(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        return "https://fake.cdn/maya_portrait.png"

    async def fake_assemble(self, scene_paths, working_dir, *a, **k):
        # Concatenation order is the drama's scene order -- assert it here.
        names = [os.path.basename(p) for p in scene_paths]
        assert names == sorted(names), f"scenes concatenated out of order: {names}"
        out = os.path.join(working_dir, "final.mp4")
        os.makedirs(working_dir, exist_ok=True)
        with open(out, "wb") as f:
            f.write(b"final")
        return out

    import tools.muapi_image_generator as image_mod

    monkeypatch.setattr(screenwriter_mod.ScreenwriterAgent, "write_script", fake_write_script)
    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image", fake_portrait)
    monkeypatch.setattr(script2video_mod.Script2VideoPipeline, "run", fake_scene_run)
    monkeypatch.setattr(idea2video_mod.Idea2VideoPipeline, "_assemble_final_drama", fake_assemble)
    monkeypatch.setattr(
        "tools.supabase_storage.upload_video",
        lambda *a, **k: asyncio.sleep(0, result=None),
    )

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    result = await pipeline.run(
        idea="Maya", num_scenes=3, working_dir=str(tmp_path / "job")
    )

    assert max_active >= 2, "scene renders never overlapped -- still sequential"
    # The character lock under parallelism: every scene got the same portrait.
    assert references_used == ["https://fake.cdn/maya_portrait.png"] * 3
    # Results keep scene order regardless of completion order.
    assert [s["index"] for s in result["scenes"]] == [0, 1, 2]


# --- tension-scaled duration caps --------------------------------------


def test_duration_cap_without_tension_matches_legacy():
    assert StoryboardArtist.duration_cap(False) == StoryboardArtist.NON_FINALE_MAX_DURATION
    assert StoryboardArtist.duration_cap(True) == StoryboardArtist.FINALE_MAX_DURATION


def test_duration_cap_scales_with_tension():
    """Screen time follows the drama: quiet beats are short, the climax is
    long. That is also the cost lever -- Kling bills by generated seconds, so
    a run of scenes can no longer each sit at the flat maximum."""
    quiet = StoryboardArtist.duration_cap(False, tension=1)
    mid = StoryboardArtist.duration_cap(False, tension=5)
    peak = StoryboardArtist.duration_cap(False, tension=10)
    assert quiet == StoryboardArtist.TENSION_MIN_DURATION
    assert quiet < mid < peak
    assert peak <= StoryboardArtist.NON_FINALE_MAX_DURATION


def test_finale_keeps_room_even_when_quiet():
    """A quiet resolution is still the ending -- it must not be squeezed to
    the 5s a tension-2 mid-story beat would get."""
    quiet_finale = StoryboardArtist.duration_cap(True, tension=2)
    assert quiet_finale >= StoryboardArtist.FINALE_MIN_DURATION
    assert StoryboardArtist.duration_cap(True, tension=10) <= StoryboardArtist.FINALE_MAX_DURATION


def test_tension_cap_cuts_typical_drama_cost():
    """The whole-drama effect: a 5-scene arc under tension caps costs less
    generated-seconds than five scenes drifting to the flat 9s ceiling."""
    arc = [3, 6, 8, 10, 4]  # the template fallback's tension shape
    capped = sum(
        StoryboardArtist.duration_cap(i == len(arc) - 1, t)
        for i, t in enumerate(arc)
    )
    flat = 4 * StoryboardArtist.NON_FINALE_MAX_DURATION + StoryboardArtist.FINALE_MAX_DURATION
    assert capped < flat * 0.85, (capped, flat)


def test_scene_tension_extraction():
    from interfaces.character import ScriptScene

    assert _scene_tension(ScriptScene(action="x", tension=9)) == 9
    assert _scene_tension({"action": "x", "tension": "7"}) == 7
    assert _scene_tension("legacy string scene") == 0
    assert _scene_tension({"action": "x"}) == 0
    assert _scene_tension({"action": "x", "tension": "high"}) == 0
    assert _scene_tension({"action": "x", "tension": 99}) == 10


@pytest.mark.asyncio
async def test_one_failing_scene_cancels_its_siblings(monkeypatch, tmp_path):
    """gather() alone propagates the first failure but leaves sibling scene
    tasks running -- polling the provider and burning credits behind a job
    that has already failed. They must be cancelled."""
    import agents.screenwriter as screenwriter_mod
    import pipelines.idea2video as idea2video_mod
    import pipelines.script2video as script2video_mod
    import tools.muapi_image_generator as image_mod

    monkeypatch.delenv("MUSEFORGE_DYNAMIC_REFERENCE", raising=False)
    monkeypatch.setenv("MUSEFORGE_SCENE_CONCURRENCY", "3")

    cancelled = []

    async def fake_scene_run(self, script, characters, **kwargs):
        idx = kwargs["scene_idx"]
        if idx == 0:
            await asyncio.sleep(0.01)
            raise RuntimeError("provider exploded")
        try:
            await asyncio.sleep(5)  # would stall the test if not cancelled
        except asyncio.CancelledError:
            cancelled.append(idx)
            raise
        return {"path": None, "url": None, "shots": []}

    async def fake_write_script(self, idea, style="Cinematic", num_scenes=3,
                                user_requirement="", preset_characters=None, language="en"):
        return DramaScript(
            title="t", logline=idea,
            characters=[CharacterProfile(name="Maya", description="30s")],
            scenes=[f"Scene {i}" for i in range(num_scenes)],
        )

    async def fake_portrait(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        return "https://fake.cdn/p.png"

    monkeypatch.setattr(screenwriter_mod.ScreenwriterAgent, "write_script", fake_write_script)
    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image", fake_portrait)
    monkeypatch.setattr(script2video_mod.Script2VideoPipeline, "run", fake_scene_run)

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    with pytest.raises(RuntimeError, match="provider exploded"):
        await asyncio.wait_for(
            pipeline.run(idea="Maya", num_scenes=3, working_dir=str(tmp_path / "job")),
            timeout=2.0,
        )
    assert sorted(cancelled) == [1, 2], f"siblings not cancelled: {cancelled}"
