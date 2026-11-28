"""The frame after a cut had never seen the frame before it.

Every scene's opening frame was drawn from the portraits, the empty plate and
the prompt -- none of which is the scene that was just on screen. Two scenes
in the same room, back to back, were two independent drawings of it: the same
walls under different light, from another side, props moved.

The bridge sends the previous scene's opening frame as a SET reference: after
every face (so the portrait still binds the face -- the reason chaining frames
as identity references is off by default), before the plate (so "the last
reference is the set" stays true), named for its light and layout only.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces import cut_bridge  # noqa: E402
from interfaces.character import CharacterInScene, CharacterProfile, DramaScript, ScriptScene  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    _BRIDGE_AND_PLATE_NOTE,
    _PLATE_REFERENCE_NOTE,
    build_frame_prompt,
    label_frame_references,
    resolve_frame_references,
)

OFFICE = "harbour office with a steel desk and one window"
PIER = "wooden pier with a bollard and a moored rowboat"


# --- when a cut is bridged ---------------------------------------------------


def _scenes(*specs):
    return [ScriptScene(action="x", **spec) for spec in specs]


def test_consecutive_scenes_in_one_place_are_bridged():
    scenes = _scenes({}, {})
    assert cut_bridge.bridges(scenes, 1, [OFFICE, OFFICE], has_plate=True)


def test_the_first_scene_has_nothing_before_it():
    assert not cut_bridge.bridges(_scenes({}), 0, [OFFICE], has_plate=True)


def test_a_cut_to_another_place_is_not_bridged():
    scenes = _scenes({}, {"location": PIER})
    assert not cut_bridge.bridges(scenes, 1, [OFFICE, PIER], has_plate=True)


def test_a_declared_jump_moved_the_light_on_purpose():
    scenes = _scenes({}, {"starts_with": "JUMP: three days later, at night"})
    assert not cut_bridge.bridges(scenes, 1, [OFFICE, OFFICE], has_plate=True)


def test_the_scene_the_world_changes_in_is_not_told_to_match_the_world_before():
    scenes = _scenes({}, {"world_change": "every light in the city goes out"})
    assert not cut_bridge.bridges(scenes, 1, [OFFICE, OFFICE], has_plate=True)


def test_a_place_with_no_plate_has_no_sentence_to_carry_the_bridge():
    assert not cut_bridge.bridges(_scenes({}, {}), 1, [OFFICE, OFFICE], has_plate=False)


def test_the_bridge_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_CUT_BRIDGE", "0")
    assert not cut_bridge.bridges(_scenes({}, {}), 1, [OFFICE, OFFICE], has_plate=True)


# --- what the frame is sent -------------------------------------------------


class _Shot:
    def __init__(self, visual_desc="Vera reads the letter at the desk."):
        self.visual_desc = visual_desc
        self.motion_desc = ""
        self.shot_type = "medium shot"
        self.lens = "35mm"
        self.camera_movement = "static"
        self.audio_desc = ""


VERA = CharacterInScene(idx=0, name="Vera", static_features="woman, 40s")
EMRE = CharacterInScene(idx=1, name="Emre", static_features="man, 50s")
PORTRAITS = {"Vera": "https://cdn/vera.png", "Emre": "https://cdn/emre.png"}


def test_the_bridge_goes_after_every_face_and_before_the_set():
    _, anchor, refs = resolve_frame_references(
        _Shot("Vera hands Emre the letter."),
        [VERA, EMRE],
        PORTRAITS,
        location_plate_url="https://cdn/office.png",
        bridge_frame_url="https://cdn/scene1_opening.png",
    )

    assert anchor == "https://cdn/vera.png", "a generated frame must never bind a face"
    assert refs == [
        "https://cdn/vera.png",
        "https://cdn/emre.png",
        "https://cdn/scene1_opening.png",
        "https://cdn/office.png",
    ]


def test_a_shot_with_nobody_in_it_is_not_bridged():
    """Its anchor IS the plate. Inserting the bridge would make it the last
    reference, and the sentence about the last reference would be a lie."""
    _, _, refs = resolve_frame_references(
        _Shot("The empty desk, the letter on it."),
        [VERA],
        PORTRAITS,
        location_plate_url="https://cdn/office.png",
        bridge_frame_url="https://cdn/scene1_opening.png",
    )
    assert "https://cdn/scene1_opening.png" not in refs


def test_the_bridge_is_named_for_what_it_is():
    refs = ["https://cdn/vera.png", "https://cdn/scene1_opening.png", "https://cdn/office.png"]
    labels = label_frame_references(
        refs,
        _Shot(),
        [VERA],
        PORTRAITS,
        matched_char=VERA,
        location_plate_url="https://cdn/office.png",
        bridge_frame_url="https://cdn/scene1_opening.png",
    )
    assert labels == ["Vera", "the previous scene, same place", "the empty set"]


def test_the_prompt_asks_the_bridge_for_its_light_and_not_its_people():
    kwargs = dict(
        style="Cinematic",
        shot=_Shot(),
        setting_location=OFFICE,
        setting_time_of_day="dusk",
        characters=[VERA],
        matched_char=VERA,
        has_location_plate=True,
        has_reference=True,
    )
    plain = build_frame_prompt(**kwargs)
    bridged = build_frame_prompt(**kwargs, has_bridge_frame=True)

    assert _PLATE_REFERENCE_NOTE in plain and _BRIDGE_AND_PLATE_NOTE not in plain
    assert _BRIDGE_AND_PLATE_NOTE in bridged
    assert "not its people" in _BRIDGE_AND_PLATE_NOTE
    # One sentence naming both pictures, not a second sentence at the same rank.
    assert _PLATE_REFERENCE_NOTE not in bridged.replace(_BRIDGE_AND_PLATE_NOTE, "")


# --- the render -------------------------------------------------------------


class _FakeShot:
    def __init__(self, visual_desc):
        self.idx = 0
        self.visual_desc = visual_desc
        self.motion_desc = "slow push-in"
        self.audio_desc = "ambient"
        self.shot_type = "medium shot"
        self.camera_movement = "static"
        self.lens = "35mm"
        self.duration_seconds = 5.0
        self.frame_url = None
        self.video_url = None

    def model_dump(self, **kwargs):
        return {
            "idx": self.idx,
            "visual_desc": self.visual_desc,
            "motion_desc": self.motion_desc,
            "duration_seconds": self.duration_seconds,
            "frame_url": self.frame_url,
            "video_url": self.video_url,
        }


async def _render(monkeypatch, tmp_path, scenes):
    """Renders through the REAL script2video, with every vendor faked."""
    frame_calls = {}

    async def fake_generate_image(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        return "https://cdn/pier.png" if PIER in prompt else (
            "https://cdn/office.png" if "Empty location plate" in prompt else "https://cdn/vera.png"
        )

    async def fake_generate_image_with_reference(
        self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None
    ):
        scene = int(prompt.split("SCENE-")[1].split(" ")[0].rstrip("."))
        frame_calls[scene] = (list(reference_url), prompt)
        return f"https://cdn/scene{scene}_opening.png"

    async def fake_video(self, prompt, image_url, duration=5, aspect_ratio="16:9", plan="free",
                         is_cancelled=None, shot_profile=None):
        return "https://cdn/video.mp4"

    async def fake_design_storyboard(self, script, characters, *a, **kw):
        return [_FakeShot(script)]

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"v")
        return path

    async def fake_concat(paths, out_path):
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(b"c")
        return out_path

    import agents.storyboard_artist as storyboard_mod
    import pipelines.idea2video as idea2video_mod
    import pipelines.script2video as script2video_mod
    import tools.muapi_image_generator as image_mod
    import tools.muapi_video_generator as video_mod

    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image", fake_generate_image)
    monkeypatch.setattr(
        image_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_generate_image_with_reference
    )
    monkeypatch.setattr(video_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_video)
    monkeypatch.setattr(storyboard_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(script2video_mod, "download_video", fake_download)
    monkeypatch.setattr(script2video_mod, "concatenate_videos", fake_concat)
    monkeypatch.setattr(idea2video_mod, "concatenate_videos", fake_concat)

    script = DramaScript(
        title="Harbour",
        logline="A letter arrives.",
        setting_location=OFFICE,
        setting_time_of_day="dusk",
        characters=[CharacterProfile(name="Vera", description="woman, 40s", role="protagonist")],
        scenes=scenes,
    )
    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    result = await pipeline.continue_from_script(
        script=script, working_dir=str(tmp_path / "job"), aspect_ratio="16:9"
    )
    return frame_calls, result


@pytest.mark.asyncio
async def test_the_second_scene_in_the_office_is_shown_the_first(monkeypatch, tmp_path):
    frame_calls, result = await _render(
        monkeypatch,
        tmp_path,
        [
            ScriptScene(action="SCENE-0 Vera reads the letter at the desk."),
            ScriptScene(action="SCENE-1 Vera folds the letter at the desk."),
        ],
    )

    refs_1, prompt_1 = frame_calls[1]
    assert refs_1 == [
        "https://cdn/vera.png",
        "https://cdn/scene0_opening.png",
        "https://cdn/office.png",
    ]
    assert _BRIDGE_AND_PLATE_NOTE.strip() in prompt_1
    # The first scene had nothing to be shown.
    assert "https://cdn/scene0_opening.png" not in frame_calls[0][0]
    shots_1 = result["scenes"][1]["shots"]
    assert shots_1[0]["bridged_from_previous_scene"] is True
    assert result["scenes"][0]["shots"][0]["bridged_from_previous_scene"] is False


@pytest.mark.asyncio
async def test_a_cut_to_the_pier_is_not_shown_the_office(monkeypatch, tmp_path):
    frame_calls, _ = await _render(
        monkeypatch,
        tmp_path,
        [
            ScriptScene(action="SCENE-0 Vera reads the letter at the desk."),
            ScriptScene(action="SCENE-1 Vera runs down the pier.", location=PIER),
        ],
    )

    refs_1, _ = frame_calls[1]
    assert "https://cdn/scene0_opening.png" not in refs_1
    assert refs_1[-1] == "https://cdn/pier.png"


@pytest.mark.asyncio
async def test_a_scene_that_draws_no_frame_does_not_hold_the_next_one_hostage(
    monkeypatch, tmp_path
):
    """The wait is resolved in a finally. A scene that finishes without ever
    drawing an opening frame releases its neighbour the moment it ends, not
    after BRIDGE_WAIT_SECONDS -- which is set far beyond this test's patience
    so that only the release can make it pass."""
    import pipelines.idea2video as idea2video_mod

    monkeypatch.setattr(cut_bridge, "BRIDGE_WAIT_SECONDS", 600.0)
    seen = {}

    async def fake_run(**kwargs):
        idx = kwargs["scene_idx"]
        if idx == 1:
            seen["bridge"] = await kwargs["bridge_frame"]()
        # Scene 0 never calls on_opening_frame: no frame on its path.
        return {"path": None, "shots": []}

    async def plate(*a, **kw):
        return "https://cdn/office.png"

    async def no_portraits(*a, **kw):
        return {}

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="", demo=True)
    monkeypatch.setattr(pipeline, "_lock_character_portraits", no_portraits)
    monkeypatch.setattr(pipeline, "_lock_location_plate", plate)
    monkeypatch.setattr(pipeline.script2video, "run", fake_run)

    script = DramaScript(
        title="Harbour",
        logline="x",
        setting_location=OFFICE,
        characters=[CharacterProfile(name="Vera", description="woman, 40s")],
        scenes=[ScriptScene(action="a"), ScriptScene(action="b")],
    )
    await asyncio.wait_for(
        pipeline.continue_from_script(script, working_dir=str(tmp_path / "job")),
        timeout=10.0,
    )
    assert "bridge" in seen, "scene 1 was offered a bridge and waited on it"
    assert seen["bridge"] is None


@pytest.mark.asyncio
async def test_a_retake_is_bridged_from_the_frame_the_viewer_saw(tmp_path):
    from unittest.mock import AsyncMock

    from pipelines.idea2video import Idea2VideoPipeline

    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"v")
    record = lambda i: {
        "index": i,
        "clip_path": str(clip),
        "take": 1,
        "shots": [{"frame_url": f"https://cdn/delivered_{i}.png"}],
    }
    previous = {
        "scenes": [record(0), record(1)],
        "location_plate": "https://cdn/office.png",
        "_render_state": {
            "script": {
                "title": "Harbour",
                "logline": "x",
                "setting_location": OFFICE,
                "scenes": [{"action": "a"}, {"action": "b"}],
                "characters": [{"name": "Vera", "description": "40s"}],
            },
            "scene_durations": [8.0, 8.0],
        },
    }
    seen = {}

    class _Stop(Exception):
        pass

    async def fake_run(**kwargs):
        seen["bridge"] = await kwargs["bridge_frame"]() if kwargs.get("bridge_frame") else None
        raise _Stop()

    pipeline = Idea2VideoPipeline("test-key", demo=True)
    pipeline.script2video.run = AsyncMock(side_effect=fake_run)

    with pytest.raises(_Stop):
        await pipeline._rerender_scenes(
            previous_result=previous, scene_indices=[1], working_dir=str(tmp_path / "job")
        )
    assert seen["bridge"] == "https://cdn/delivered_0.png"

    # Re-shooting both: scene 0's delivered frame is about to leave the screen.
    seen.clear()
    with pytest.raises(_Stop):
        await pipeline._rerender_scenes(
            previous_result=previous, scene_indices=[1, 0], working_dir=str(tmp_path / "job2")
        )
    assert seen["bridge"] is None
