"""Job 7b4b7271: three defects the fal history and the finished film agree on.

* ``falai_h3`` lip sync REDRAWS a scene from its first frame, discarding every
  other shot. The gate asked how many people SPEAK, so a scene with five
  survivors and one line passed, and the film opened on five seconds of Yusuf
  alone -- the wide of all five was generated, paid for and thrown away.
* The empty location plate for "rocky coastal shoreline" came back as a seaside
  promenade (railing, footpath, street lamps), and the plate is a reference of
  every shot.
* The storyboard folded the brief's empty beats ("black surf on wet stones",
  "the flames alone") into populated shots, and a cap of N shots could eat them.
"""
import os
import sys
from types import SimpleNamespace as N

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.idea2video import (  # noqa: E402
    _location_plate_prompt,
    _scene_survives_a_redraw,
)
from tools.falai_h3_lipsync import FalAIH3Lipsync  # noqa: E402

CAST = [
    CharacterInScene(idx=i, name=n, static_features="a sailor", wardrobe="oilskin")
    for i, n in enumerate(["Yusuf", "Deniz", "Kemal", "Ayse", "Selim"])
]


def _shot(visual, shows=None, seconds=4.0, shot_type="medium shot"):
    return StoryboardShot(
        idx=0, visual_desc=visual, motion_desc="push in", shot_type=shot_type,
        duration_seconds=seconds, shows_people=shows,
    )


# ── the redraw gate ─────────────────────────────────────────────────────────


def test_the_h3_backend_declares_that_it_redraws():
    assert FalAIH3Lipsync.redraws_the_take is True


def test_the_scene_of_five_survivors_is_not_redrawn():
    shots = [
        _shot("Yusuf, Deniz, Kemal, Ayse and Selim crawl onto the shingle"),
        _shot("Yusuf grips Deniz's arm"),
    ]
    assert _scene_survives_a_redraw(shots, CAST) is False


def test_a_scene_that_shows_a_second_character_in_another_shot_is_not_redrawn():
    shots = [_shot("Yusuf grips the hull"), _shot("Deniz listens, eyes wide")]
    assert _scene_survives_a_redraw(shots, CAST) is False


def test_a_scene_of_one_character_may_be_redrawn():
    shots = [_shot("Yusuf grips the hull"), _shot("Yusuf, closer, breathing hard")]
    assert _scene_survives_a_redraw(shots, CAST) is True


def test_a_scene_with_an_empty_beat_is_not_redrawn():
    shots = [_shot("black surf on wet stones", shows=False), _shot("Yusuf grips the hull")]
    assert _scene_survives_a_redraw(shots, CAST) is False


def test_where_nothing_is_known_it_fails_open():
    assert _scene_survives_a_redraw(None, CAST) is True
    assert _scene_survives_a_redraw([_shot("Yusuf")], None) is True


def test_dict_shots_are_read_the_same_way():
    shots = [{"visual_desc": "Yusuf and Deniz", "motion_desc": ""}]
    assert _scene_survives_a_redraw(shots, CAST) is False
    assert _scene_survives_a_redraw([{"visual_desc": "x", "shows_people": False}], CAST) is False


class _Redrawer:
    redraws_the_take = True

    def __init__(self):
        self.calls = 0

    def available(self):
        return True

    async def sync(self, video, audio, is_cancelled=None):
        self.calls += 1
        return "https://cdn/synced.mp4"


@pytest.mark.asyncio
async def test_the_pass_never_calls_a_redrawing_backend_for_a_crowded_scene(monkeypatch, tmp_path):
    import pipelines.idea2video as mod
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    fake = _Redrawer()
    monkeypatch.setattr(mod, "make_lipsync", lambda demo=False: fake)
    clip = tmp_path / "scene0.mp4"
    clip.write_bytes(b"original")
    tracks = [{
        "scene_index": 0, "character": "Yusuf", "line": "Count heads.",
        "audio_url": "https://cdn/a.mp3", "start_seconds": 0.0, "end_seconds": 4.0,
    }]

    async def progress(*a, **k):
        pass

    async def run(shots):
        fake.calls = 0
        await Idea2VideoPipeline("test-key")._lipsync_scenes(
            scene_paths=[str(clip)], dialogue_tracks=[dict(t) for t in tracks],
            working_dir=str(tmp_path), progress=progress,
            shots_by_clip={0: shots}, characters=CAST,
        )
        return fake.calls

    crowded = [_shot("Yusuf, Deniz and Kemal on the shingle", shot_type="close-up")]
    assert await run(crowded) == 0
    solo = [_shot("Yusuf on the shingle", shot_type="close-up")]
    assert await run(solo) == 1


# ── the plate ───────────────────────────────────────────────────────────────

LOOK = N(is_photoreal=True, render_note="")


def test_an_outdoor_plate_says_nothing_built_is_added():
    prompt = _location_plate_prompt(
        "rocky coastal shoreline with jagged rocks and a shingle beach", "night", "present day", "Cinematic", LOOK
    )
    assert "holds only what is named above" in prompt
    assert "natural and untouched" in prompt
    assert "no people" in prompt


def test_an_indoor_plate_is_not_told_the_sky_is_natural():
    prompt = _location_plate_prompt("INT. walnut study", "night", "", "Cinematic", LOOK)
    assert "holds only what is named above" in prompt
    assert "natural and untouched" not in prompt


# ── the empty beats ─────────────────────────────────────────────────────────


def _kinds(shots):
    return [("empty" if s.shows_people is False else "people") for s in shots]


def test_the_cap_keeps_the_empty_beat_and_still_bounds_the_people():
    shots = [
        _shot("black surf", shows=False),
        _shot("Yusuf crawls", shows=True),
        _shot("Deniz crawls", shows=True),
        _shot("Kemal crawls", shows=True),
    ]
    kept = StoryboardArtist._cap_shots(shots, 2)
    assert _kinds(kept) == ["empty", "people", "people"]


def test_the_cap_limits_empty_beats_too():
    shots = [_shot(f"empty {i}", shows=False) for i in range(5)] + [_shot("Yusuf", shows=True)]
    assert _kinds(StoryboardArtist._cap_shots(shots, 1)).count("empty") == 2


def test_an_empty_beat_survives_the_shot_plan_in_its_place(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_REACTION_SHOTS", "1")
    shots = [
        _shot("black surf on wet stones", shows=False, seconds=3.0),
        _shot("Yusuf grips Deniz's arm, Deniz flinches", shows=True, seconds=9.0),
    ]
    planned = StoryboardArtist._apply_shot_plan(
        shots, "desperate shock", 8, CAST, lipsync_enabled=False, budget=12.0
    )
    assert planned[0].visual_desc == "black surf on wet stones"
    assert planned[0].shows_people is False
    assert planned[0].duration_seconds == 3.0
    assert planned[0].role == "master" and planned[0].deliver_seconds == 0.0
    # The cutaway is built on the people-shot, never on the empty beat.
    assert [s.shows_people for s in planned][1:] == [True, None]
    assert "Deniz" in planned[2].visual_desc or "Yusuf" in planned[2].visual_desc
    # ...and the empty beat's seconds come out of the scene's budget.
    assert planned[1].duration_seconds <= 12.0 - 3.0


def test_a_scene_of_nothing_is_not_given_a_reaction_cut(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_REACTION_SHOTS", "1")
    shots = [_shot("flames", shows=False, seconds=4.0), _shot("the wave", shows=False, seconds=4.0)]
    planned = StoryboardArtist._apply_shot_plan(
        shots, "dread", 9, CAST, lipsync_enabled=False, budget=8.0
    )
    assert [s.visual_desc for s in planned] == ["flames", "the wave"]


def test_the_designer_is_told_to_film_an_empty_beat_as_its_own_shot():
    import inspect

    source = inspect.getsource(sys.modules[StoryboardArtist.__module__])
    assert "EVERY EMPTY BEAT IN THE ACTION IS ITS OWN SHOT" in source
    assert "Never fold it into the first" in source
