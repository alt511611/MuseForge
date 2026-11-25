"""Job d91a4172: the event was already over when the take began.

The brief: "the city's power dies the moment she opens it". The climax was one
11-second close-up, and its opening frame was drawn in the changed world --
dark, doors shut -- because the scene the event happens IN was treated like
every scene after it. So the doors never opened, no light poured out, nothing
went out on screen; and between two dark anchors the take lit the floodlights
again for four seconds, because nothing in it was the change.

Three more from the same film:
* both dialogue scenes were redrawn from their first (wide) frame by the
  lip-sync pass, which replaced two of each scene's three storyboarded angles;
* the discovery close-up was told "no trace of a smile" and smiled;
* the climax close-up was punched in to 1.45x, 745 lines stretched to 1080.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces import acting, long_take, pacing  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.scene_take import Beat, Element, SceneTake  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.idea2video import _redraw_discards_an_angle  # noqa: E402
from pipelines.script2video import build_motion_prompt  # noqa: E402

EVENT = (
    "Every floodlight on the pier and every light of the city skyline goes "
    "dark, leaving the humming container's glow as the only light"
)
ACTION = (
    "Mara wrenches the latch and hauls the container doors open. Blinding "
    "blue-white light floods out, and every floodlight goes dark."
)
HARBOUR = "rain-soaked cargo harbour pier with a sodium floodlight pole"


# --- when the take carries the event ------------------------------------------


def test_a_one_shot_long_climax_carries_its_event():
    assert long_take.event_spans_take(EVENT, 1, 11.0, has_character=True, draws_frames=True)


@pytest.mark.parametrize(
    "change, shots, seconds, character, frames",
    [
        ("", 1, 11.0, True, True),        # nothing happens in this scene
        (EVENT, 3, 11.0, True, True),     # covered in angles: which one is unknowable
        (EVENT, 1, 5.0, True, True),      # too short to hold a change
        (EVENT, 1, 11.0, False, True),    # no face to anchor the end to
        (EVENT, 1, 11.0, True, False),    # reference-only: no frames to draw
    ],
)
def test_otherwise_the_scene_is_changed_from_its_first_frame(change, shots, seconds, character, frames):
    assert not long_take.event_spans_take(change, shots, seconds, character, frames)


def test_the_take_is_told_the_event_happens_in_it_not_that_it_has():
    shot = StoryboardShot(idx=0, visual_desc="x", motion_desc="Mara wrenches the latch", shot_type="close-up")
    prompt = build_motion_prompt(shot, world_state=EVENT, event_in_take=True)
    assert "THIS is the shot the story's event happens in" in prompt
    assert "never changes back" in prompt
    assert "already changed" not in prompt
    # A scene after the event still holds it from frame one.
    assert "already changed" in build_motion_prompt(shot, world_state=EVENT)


def test_the_one_shot_take_on_the_multishot_path_says_the_same():
    take = SceneTake(
        seconds=11,
        beats=(Beat(seconds=11, description="Mara wrenches the latch.", shot_type="close-up"),),
        elements=(Element(name="Mara", images=("https://cdn/f.jpg",)),),
        max_prompt_chars=512,
        world_state=EVENT,
        event_in_take=True,
    )
    prompt = take.multi_prompt()[0]["prompt"]
    assert "In this take, once and for good" in prompt
    assert "has changed and stays so" not in prompt


# --- the climax, again --------------------------------------------------------


class _MiniMaxLike:
    accepts_reference_set = True
    can_start_from_frame = True
    uses_character_reference_to_video = True

    def __init__(self):
        self.calls = []

    async def generate_video_from_image(self, prompt, image_url, duration=5,
                                        aspect_ratio="16:9", plan="free",
                                        is_cancelled=None, shot_profile=None, **kwargs):
        self.calls.append({"prompt": prompt, "image_url": image_url, **kwargs})
        return "https://cdn/video.mp4"


async def _climax(monkeypatch, tmp_path, seconds):
    from pipelines.script2video import Script2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    monkeypatch.setenv("MUSEFORGE_CHARACTER_QA_ENABLED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    drawn, checked = [], []

    async def fake_ref(self, prompt, references, aspect_ratio="16:9", is_cancelled=None, **kw):
        drawn.append({"prompt": prompt, "references": list(references)})
        return f"https://cdn/drawn_{len(drawn)}.jpg"

    async def fake_verify(frame_url, expected_character_desc, expected_setting, anthropic_api_key=""):
        checked.append(expected_setting)
        return {"character_ok": True, "setting_ok": True, "issue": ""}

    async def fake_design(self, script, characters, *a, **kw):
        return [StoryboardShot(
            idx=0,
            visual_desc="Mara grips the container latch, floodlights burning behind her",
            motion_desc="Mara wrenches the latch upward",
            shot_type="close-up",
            duration_seconds=seconds,
        )]

    async def fake_download(url, path):
        open(path, "wb").write(b"v")
        return path

    async def fake_trim(path, out_path, seconds, from_head=True):
        return path

    monkeypatch.setattr("pipelines.script2video.verify_frame", fake_verify)
    monkeypatch.setattr("agents.storyboard_artist.StoryboardArtist.design_storyboard", fake_design)
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image_with_reference", fake_ref
    )
    monkeypatch.setattr("pipelines.script2video.download_video", fake_download)
    monkeypatch.setattr("pipelines.script2video.trim_to_duration", fake_trim)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    backend = _MiniMaxLike()
    pipeline.video_gen = backend
    result = await pipeline.run(
        script=ACTION,
        characters=[CharacterInScene(idx=0, name="Mara", static_features="a woman")],
        working_dir=str(tmp_path),
        character_portraits={"Mara": "https://cdn/mara_sheet.jpg"},
        location_plate_url="https://cdn/plate.jpg",
        setting_location=HARBOUR,
        setting_time_of_day="night",
        world_change=EVENT,
        scene_duration=seconds,
    )
    return drawn, checked, backend.calls, result


@pytest.mark.asyncio
async def test_the_climax_opens_before_the_event_and_is_drawn_to_end_after_it(monkeypatch, tmp_path):
    drawn, checked, videos, result = await _climax(monkeypatch, tmp_path, 11.0)

    opening, end = drawn[0], drawn[1]
    assert "changed STATE" not in opening["prompt"], "the opening frame is the world BEFORE"
    assert EVENT not in checked[0], "and it is checked against the place as it was"

    assert end["references"][0] == "https://cdn/drawn_1.jpg"
    assert "hauls the container doors open" in end["prompt"], "the end is the scene's end"
    assert "stays changed" in end["prompt"]

    video = videos[0]
    assert video["image_url"] == "https://cdn/drawn_1.jpg"
    assert video["last_image"] == "https://cdn/drawn_2.jpg"
    assert "THIS is the shot the story's event happens in" in video["prompt"]
    assert result["shots"][0]["event_in_take"] is True


@pytest.mark.asyncio
async def test_a_short_climax_is_still_changed_from_its_first_frame(monkeypatch, tmp_path):
    drawn, checked, videos, result = await _climax(monkeypatch, tmp_path, 5.0)

    assert "changed STATE" in drawn[0]["prompt"]
    assert EVENT in checked[0]
    assert "already changed" in videos[0]["prompt"]
    assert result["shots"][0]["event_in_take"] is False


# --- the angles the lip sync threw away ----------------------------------------


def _shots(*seconds):
    return [{"shot_type": "medium", "duration_seconds": s} for s in seconds]


def test_the_discovery_scene_s_redraw_replaced_two_of_its_three_angles():
    """Scene 1: wide 4 s, medium 4 s, close-up 3 s; redraw 9.46 s."""
    assert _redraw_discards_an_angle(_shots(4.0, 4.0, 3.0), 9.46)


def test_a_one_shot_scene_has_nothing_to_lose():
    assert not _redraw_discards_an_angle(_shots(11.0), 9.46)


def test_an_angle_that_starts_after_the_redraw_survives_in_the_rejoined_tail():
    assert not _redraw_discards_an_angle(_shots(8.0, 3.0), 5.0)


def test_a_second_under_the_redraw_is_tolerated():
    assert not _redraw_discards_an_angle(_shots(4.5, 6.0), 5.0)


def test_without_durations_it_fails_open():
    assert not _redraw_discards_an_angle([{"shot_type": "wide"}, {"shot_type": "close-up"}], 9.0)


# --- the smile -------------------------------------------------------------------


@pytest.mark.parametrize("tag", ["wary curiosity", "tense confrontation"])
def test_a_face_is_never_told_the_expression_it_is_not(tag):
    beat = acting.resolve(tag)
    for text in (beat.onset, beat.peak):
        assert "smile" not in text, "a video model with no negative prompt reads the noun"


# --- the punch-in ----------------------------------------------------------------


def test_a_close_up_is_not_punched_in_past_what_its_pixels_hold():
    cuts = pacing.plan_internal_cuts(11.0, tension=10, shot_type="close-up", pacing="medium")
    assert cuts, "it is still cut: the rhythm stays"
    assert max(c.zoom for c in cuts) <= 1.18


def test_a_wide_still_punches_in_to_find_the_face():
    cuts = pacing.plan_internal_cuts(11.0, tension=10, shot_type="wide", pacing="medium")
    assert max(c.zoom for c in cuts) == 1.45
