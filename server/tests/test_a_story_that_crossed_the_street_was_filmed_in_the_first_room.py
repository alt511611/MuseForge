"""A story that crossed the street was filmed in the first room.

The screenwriter was told "if the story needs somewhere else, it is a
different scene with a different location" and given no field to put that
location in. A drama had one place: one plate, one setting clause on every
frame. A scene the story moved to the pier was described in its action line
and then conditioned on a picture of the office, under a prompt saying "The
EXACT SAME location as the opening shot".

A scene now names its place when it moves, and each place gets its own plate,
drawn once.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.character import CharacterProfile, DramaScript, ScriptScene  # noqa: E402
from interfaces.places import MAX_EXTRA_LOCATIONS, extra_locations, scene_location  # noqa: E402

OFFICE = "harbour office with a steel desk and one window"
PIER = "wooden pier with a bollard and a moored rowboat"
WARD = "hospital ward with two beds"
CHAPEL = "stone chapel with a single pew"


# --- where a scene is -------------------------------------------------------


def test_a_scene_that_does_not_move_is_in_the_drama_s_place():
    assert scene_location(ScriptScene(action="x"), OFFICE) == OFFICE
    # A legacy string scene has nowhere else to be.
    assert scene_location("She opens the letter.", OFFICE) == OFFICE


def test_restating_the_drama_s_place_is_not_a_second_set():
    """A model told "only when it is somewhere else" still fills the field in.
    Same words, different case or spacing, is the same room."""
    scene = ScriptScene(action="x", location="  Harbour office with a steel desk and one WINDOW ")
    assert scene_location(scene, OFFICE) == OFFICE
    assert extra_locations([scene], OFFICE) == []


def test_each_place_is_built_once_in_story_order():
    scenes = [
        ScriptScene(action="a"),
        ScriptScene(action="b", location=PIER),
        ScriptScene(action="c", location=PIER),
        ScriptScene(action="d", location=WARD),
    ]
    assert extra_locations(scenes, OFFICE) == [PIER, WARD]


def test_a_drama_cannot_wander_past_the_cap():
    """Every place is a set to build and a set the viewer must learn. The cap
    cuts from the end: the places the story reaches first are established."""
    scenes = [ScriptScene(action=p, location=p) for p in (PIER, WARD, CHAPEL)]
    assert extra_locations(scenes, OFFICE) == [PIER, WARD][:MAX_EXTRA_LOCATIONS]


def test_the_screenwriter_is_told_the_same_cap_the_pipeline_enforces():
    words = {1: "one", 2: "two", 3: "three", 4: "four"}
    prompt = ScreenwriterAgent.SYSTEM_PROMPT
    assert f"At most\n{words[MAX_EXTRA_LOCATIONS]} places besides" in prompt
    assert '"location":' in prompt


def test_the_place_is_written_in_english_like_every_field_a_model_reads():
    assert '"world_change" and "location"' in ScreenwriterAgent.LANGUAGE_CLAUSE


# --- the render ------------------------------------------------------------


def _async_return(value):
    async def _f(*a, **kw):
        return value

    return _f


async def _render(monkeypatch, tmp_path, scenes, failing=()):
    import pipelines.idea2video as mod

    plate_prompts = []
    runs = []

    async def fake_generate_image(prompt, aspect_ratio="1:1", is_cancelled=None):
        plate_prompts.append(prompt)
        for name, place in (("pier", PIER), ("ward", WARD), ("chapel", CHAPEL)):
            if place in prompt:
                if name in failing:
                    raise RuntimeError("plate refused")
                return f"https://cdn/{name}.png"
        return "https://cdn/office.png"

    async def fake_run(**kwargs):
        runs.append(kwargs)
        return {"path": None, "shots": []}

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=True)
    monkeypatch.setattr(pipeline, "_lock_character_portraits", _async_return({}))
    monkeypatch.setattr(pipeline.image_gen, "generate_image", fake_generate_image)
    monkeypatch.setattr(pipeline.script2video, "run", fake_run)

    script = DramaScript(
        title="Harbour",
        logline="A letter arrives.",
        setting_location=OFFICE,
        setting_time_of_day="dusk",
        characters=[CharacterProfile(name="Vera", description="woman, 40s")],
        scenes=scenes,
    )
    result = await pipeline.continue_from_script(script, working_dir=str(tmp_path / "job"))
    runs.sort(key=lambda r: r["scene_idx"])
    return plate_prompts, runs, result


@pytest.mark.asyncio
async def test_a_scene_on_the_pier_is_filmed_on_the_pier(monkeypatch, tmp_path):
    plate_prompts, runs, result = await _render(
        monkeypatch,
        tmp_path,
        [
            ScriptScene(action="Vera opens the letter."),
            ScriptScene(action="Vera runs to the boat.", location=PIER),
            ScriptScene(action="Vera comes back to the desk."),
        ],
    )

    assert [r["setting_location"] for r in runs] == [OFFICE, PIER, OFFICE]
    assert [r["location_plate_url"] for r in runs] == [
        "https://cdn/office.png",
        "https://cdn/pier.png",
        "https://cdn/office.png",
    ]
    # Each place drawn once, and the pier at the drama's own hour.
    assert len(plate_prompts) == 2
    assert any(PIER in p and "dusk" in p for p in plate_prompts)
    assert result["location_plate"] == "https://cdn/office.png"
    assert result["location_plates"] == {
        OFFICE: "https://cdn/office.png",
        PIER: "https://cdn/pier.png",
    }


@pytest.mark.asyncio
async def test_a_place_whose_plate_failed_is_not_given_the_office(monkeypatch, tmp_path):
    """The compromise this exists to remove is a pier scene conditioned on a
    picture of the office. No picture is better than the wrong one."""
    _, runs, _ = await _render(
        monkeypatch,
        tmp_path,
        [ScriptScene(action="a"), ScriptScene(action="b", location=PIER)],
        failing=("pier",),
    )

    assert runs[1]["setting_location"] == PIER
    assert runs[1]["location_plate_url"] is None


@pytest.mark.asyncio
async def test_a_place_past_the_cap_keeps_its_words_and_gets_no_picture(monkeypatch, tmp_path):
    plate_prompts, runs, _ = await _render(
        monkeypatch,
        tmp_path,
        [
            ScriptScene(action="a", location=PIER),
            ScriptScene(action="b", location=WARD),
            ScriptScene(action="c", location=CHAPEL),
        ],
    )

    assert not any(CHAPEL in p for p in plate_prompts)
    assert runs[2]["setting_location"] == CHAPEL
    assert runs[2]["location_plate_url"] is None


@pytest.mark.asyncio
async def test_a_one_room_drama_draws_exactly_what_it_did_before(monkeypatch, tmp_path):
    plate_prompts, runs, result = await _render(
        monkeypatch, tmp_path, [ScriptScene(action="a"), ScriptScene(action="b")]
    )

    assert len(plate_prompts) == 1
    assert all(r["location_plate_url"] == "https://cdn/office.png" for r in runs)
    assert result["location_plates"] == {OFFICE: "https://cdn/office.png"}


# --- after delivery ----------------------------------------------------------


def _delivered(tmp_path):
    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"not really a video")
    scene_record = lambda i: {"index": i, "clip_path": str(clip), "shots": [], "take": 1}
    return {
        "scenes": [scene_record(0), scene_record(1)],
        "video_url": "https://cdn/master.mp4",
        "location_plate": "https://cdn/office.png",
        "location_plates": {
            OFFICE: "https://cdn/office.png",
            PIER: "https://cdn/pier.png",
        },
        "_render_state": {
            "script": {
                "title": "Harbour",
                "logline": "A letter arrives.",
                "setting_location": OFFICE,
                "scenes": [
                    {"action": "Vera opens the letter."},
                    {"action": "Vera runs to the boat.", "location": PIER},
                ],
                "characters": [{"name": "Vera", "description": "40s, grey coat"}],
            },
            "scene_durations": [8.0, 8.0],
        },
    }


class _Stop(Exception):
    pass


@pytest.mark.asyncio
async def test_a_retake_of_the_pier_scene_is_still_on_the_pier(tmp_path):
    from unittest.mock import AsyncMock

    from pipelines.idea2video import Idea2VideoPipeline

    seen = {}

    async def fake_run(**kwargs):
        seen.update(kwargs)
        raise _Stop()

    pipeline = Idea2VideoPipeline("test-key", demo=True)
    pipeline.script2video.run = AsyncMock(side_effect=fake_run)

    with pytest.raises(_Stop):
        await pipeline._rerender_scenes(
            previous_result=_delivered(tmp_path),
            scene_indices=[1],
            working_dir=str(tmp_path / "job"),
        )

    assert seen["setting_location"] == PIER
    assert seen["location_plate_url"] == "https://cdn/pier.png"


@pytest.mark.asyncio
async def test_editing_the_set_re_shoots_only_the_scenes_in_it(tmp_path):
    """"Make the office night" cannot touch the pier, and re-rendering the pier
    scene would charge for a scene the edit does not change."""
    from unittest.mock import AsyncMock

    from pipelines.idea2video import Idea2VideoPipeline

    pipeline = Idea2VideoPipeline("test-key", demo=True)
    pipeline.image_gen.generate_image_with_reference = AsyncMock(
        return_value="https://cdn/office_night.png"
    )
    pipeline._rerender_scenes = AsyncMock(return_value={})

    await pipeline.apply_global_edit(
        previous_result=_delivered(tmp_path),
        instruction="make it night",
        target="location",
        working_dir=str(tmp_path / "job"),
    )

    kwargs = pipeline._rerender_scenes.await_args.kwargs
    assert kwargs["scene_indices"] == [0]
    assert kwargs["location_plate_override"] == "https://cdn/office_night.png"
