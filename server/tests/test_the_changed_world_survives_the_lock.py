"""The locked setting must not veto the one scene allowed to break it.

Two locks protect continuity across a drama: the setting line ("the EXACT SAME
physical location") and the lighting plan ("identical in every shot of this
film"). Both are right for four scenes out of five, and both are aimed
straight at the fifth -- the scene where the story's event changes the place.

The lighting plan already stands down for that scene. Two things did not.

* The setting line is the screenwriter's, and a screenwriter describing a
  place at night describes how it is lit. The delivered job's own locked
  setting reads "rain-soaked cargo harbour, stacked shipping containers under
  sodium floodlights" -- so against a brief whose event is the city losing
  power, the prompt asked for the floodlights and for their failure in the
  same breath. Every lamp in the yard stayed on, through all three scenes.

* The vision QA verifies each frame against that same locked setting. A
  correctly blacked-out harbour is a mismatch to it, and the repair
  regenerates the frame -- aimed by an issue string saying the place looks
  wrong -- until the lights come back.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import build_frame_prompt  # noqa: E402


HARBOUR = "rain-soaked cargo harbour, stacked shipping containers under sodium floodlights"
EVENT = "the city's power dies the moment she opens it"


def _prompt(**kwargs):
    shot = StoryboardShot(
        idx=0,
        visual_desc="Mara Voss staggers back from the open container door",
        motion_desc="handheld push in",
        shot_type="medium shot",
        lens="35mm",
        expression_desc="eyes wide, breath caught",
    )
    character = CharacterInScene(
        idx=0,
        name="Mara Voss",
        static_features="a woman in her late thirties, dark hair pulled back",
        wardrobe="a yellow high-visibility rain jacket",
    )
    return build_frame_prompt(
        "Sci-Fi",
        shot,
        setting_location=HARBOUR,
        setting_time_of_day="night",
        setting_era="near future",
        has_dialogue=True,
        characters=[character],
        matched_char=character,
        **kwargs,
    )


def test_the_scene_that_causes_the_event_renders_it():
    prompt = _prompt(world_change=EVENT)
    assert EVENT in prompt
    assert "must be plainly visible in the frame, not implied" in prompt


def test_a_later_scene_inherits_the_changed_world():
    """Once the city's power dies it stays dead: the film must not cut from a
    blackout back to a lit harbour."""
    prompt = _prompt(world_state=EVENT)
    assert EVENT in prompt


def test_the_lighting_plan_stands_down_for_it():
    assert "Lighting continuity" in _prompt()
    assert "Lighting continuity" not in _prompt(world_change=EVENT)


def test_the_light_named_in_the_setting_is_overruled():
    """The setting line still has to name the place -- it is the same harbour,
    with the same containers -- but its sodium floodlights describe the world
    before the change, and asking for both is asking for the lamps."""
    prompt = _prompt(world_change=EVENT)
    assert HARBOUR in prompt, "the location lock has to survive"
    assert "describes this place BEFORE the change" in prompt
    assert "do not light the frame with it" in prompt


def test_an_unchanged_scene_keeps_its_prompt_exactly_as_it_was():
    prompt = _prompt()
    assert "BEFORE the change" not in prompt
    assert "Only the time-of-day lighting may shift subtly" in prompt


# ── and the QA does not repair the event away ───────────────────────────────


@pytest.mark.asyncio
async def test_the_frame_check_is_told_what_the_story_did_to_the_place(
    monkeypatch, tmp_path
):
    from pipelines.script2video import Script2VideoPipeline

    checked = []

    async def fake_verify(frame_url, expected_character_desc, expected_setting,
                          anthropic_api_key=""):
        checked.append(expected_setting)
        return {"character_ok": True, "setting_ok": True, "issue": ""}

    async def fake_design(self, script, characters, user_requirement, director_style, **_kw):
        return [
            StoryboardShot(
                idx=0,
                visual_desc="Mara Voss staggers back from the open container",
                motion_desc="handheld",
                duration_seconds=8.0,
            )
        ]

    async def fake_frame(self, prompt, *a, **kw):
        return "https://fake.cdn/frame.png"

    async def fake_video(self, prompt, image_url, duration, **kwargs):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    async def fake_trim(path, out_path, seconds, from_head=True):
        return path

    monkeypatch.setenv("MUSEFORGE_CHARACTER_QA_ENABLED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("pipelines.script2video.verify_frame", fake_verify)
    monkeypatch.setattr(
        "agents.storyboard_artist.StoryboardArtist.design_storyboard", fake_design
    )
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image_with_reference",
        fake_frame,
    )
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image", fake_frame
    )
    monkeypatch.setattr(
        "tools.muapi_video_generator.MuAPIVideoGenerator.generate_video_from_image",
        fake_video,
    )
    monkeypatch.setattr("pipelines.script2video.download_video", fake_download)
    monkeypatch.setattr("pipelines.script2video.trim_to_duration", fake_trim)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    await pipeline.run(
        script="Mara opens the container.",
        characters=[
            CharacterInScene(idx=0, name="Mara Voss", static_features="a woman")
        ],
        working_dir=str(tmp_path),
        character_portraits={"Mara Voss": "https://fake.cdn/mara.png"},
        setting_location=HARBOUR,
        setting_time_of_day="night",
        world_change=EVENT,
    )

    assert checked, "QA never ran, so this proves nothing"
    assert EVENT in checked[0], (
        "the frame check would read a blacked-out harbour as the wrong place "
        "and repair the film's event away"
    )
