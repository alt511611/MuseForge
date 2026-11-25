"""Job 6efbb788: one woman alone on a dock was four women, and the blackout came back on.

Thirty seconds, one visible character (Mira; Dess is a voice on the radio),
MiniMax H3 in reference mode with the multi-view character sheet switched on.

* Four faces. The two medium/wide shots were reference-only: the only picture
  of Mira the video model had was a 2x2 sheet of hips-up figures, faces an
  eighth of its height. Only the close-ups, which start from a rendered frame,
  came near it.
* The blackout reverted. The climax's frame was correctly dark; the take
  animated from it was handed the plate -- drawn before the event, every
  floodlight burning -- as "the empty set", and by its sixth second had lit
  every pole again. The frame prompt had told the model to take the plate's
  LIGHT.
* A grin into a walkie-talkie. "wary curiosity" matched the suspicion beat,
  a poker face held at somebody, with "the smile staying on the mouth".
* The climax's one shot was the breath before the event ("floodlight poles
  still burn steadily behind her").
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces import acting  # noqa: E402
from interfaces.character import CharacterInScene, CharacterProfile, DramaScript, ScriptScene  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    CHANGED_PLATE_LABEL,
    _BRIDGE_AND_PLATE_NOTE,
    _CHANGED_PLATE_NOTE,
    _PLATE_REFERENCE_NOTE,
    build_frame_prompt,
    video_reference_set,
    wants_first_frame,
)

HARBOUR = "rain-soaked cargo harbour at night with a row of tall floodlight poles"
BLACKOUT = "every floodlight pole along the harbour goes dark"
SHEET = "https://cdn/mira_sheet.jpg"
PLATE = "https://cdn/harbour_plate.jpg"


# --- the grin ---------------------------------------------------------------


def test_wariness_alone_with_a_thing_is_not_a_poker_face():
    beat = acting.resolve("wary curiosity")
    assert beat.label == "wariness"
    for text in (beat.onset, beat.peak):
        assert "smile" not in text.replace("no trace of a smile", "")
        assert "social face" not in text
        assert "the other" not in text, "there is nobody else in the shot"


def test_the_turkish_words_for_it_land_there_too():
    for tag in ("temkinli merak", "tedirgin"):
        assert acting.resolve(tag).label == "wariness"


def test_suspicion_of_a_person_keeps_its_poker_face():
    for tag in ("suspicion", "quiet mistrust", "doubt", "şüphe"):
        assert acting.resolve(tag).label == "suspicion"


# --- the lights --------------------------------------------------------------


class _Shot:
    visual_desc = "Mira stands in the container's light."
    motion_desc = ""
    shot_type = "medium shot"
    lens = "35mm"
    camera_movement = "static"
    audio_desc = ""


MIRA = CharacterInScene(idx=0, name="Mira", static_features="woman, late thirties")


def _frame(**kw):
    return build_frame_prompt(
        "Cinematic", _Shot(), setting_location=HARBOUR, setting_time_of_day="night",
        characters=[MIRA], matched_char=MIRA, has_location_plate=True,
        has_reference=True, **kw,
    )


def test_after_the_event_the_plate_gives_its_walls_and_not_its_light():
    prompt = _frame(world_change=BLACKOUT)
    assert _CHANGED_PLATE_NOTE in prompt
    assert "materials and light" not in prompt
    # ...and every scene that inherits the changed world, not just the one it happens in.
    assert _CHANGED_PLATE_NOTE in _frame(world_state=BLACKOUT)


def test_a_bridged_scene_after_the_event_gets_the_same_correction():
    prompt = _frame(world_state=BLACKOUT, has_bridge_frame=True)
    assert "previous scene in this same place" in prompt
    assert _CHANGED_PLATE_NOTE in prompt
    assert "materials and light" not in prompt


def test_before_the_event_the_plate_is_still_the_light():
    assert _PLATE_REFERENCE_NOTE in _frame()
    assert _BRIDGE_AND_PLATE_NOTE in _frame(has_bridge_frame=True)


def test_a_take_that_starts_from_the_changed_frame_is_not_shown_the_lit_plate():
    refs, labels = video_reference_set(
        [SHEET, PLATE], ["Mira", "the empty set"],
        location_plate_url=PLATE, world_changed=True, starts_from_frame=True,
    )
    assert refs == [SHEET] and labels == ["Mira"]


def test_a_reference_only_take_keeps_the_plate_for_its_walls():
    refs, labels = video_reference_set(
        [SHEET, PLATE], ["Mira", "the empty set"],
        location_plate_url=PLATE, world_changed=True, starts_from_frame=False,
    )
    assert refs == [SHEET, PLATE]
    assert labels == ["Mira", CHANGED_PLATE_LABEL]
    assert "never its light" in CHANGED_PLATE_LABEL


def test_before_the_event_the_take_gets_the_set_it_always_got():
    refs, labels = video_reference_set(
        [SHEET, PLATE], ["Mira", "the empty set"],
        location_plate_url=PLATE, world_changed=False, starts_from_frame=True,
    )
    assert refs == [SHEET, PLATE] and labels == ["Mira", "the empty set"]


def test_the_climax_s_one_shot_is_told_to_be_the_moment_after():
    from pipelines.idea2video import _format_scene_direction

    direction = _format_scene_direction(
        ScriptScene(action="She hauls the doors open.", world_change=BLACKOUT)
    )
    assert "moment AFTER it lands" in direction
    assert "never the moment before" in direction


# --- the faces ---------------------------------------------------------------


class _FrameCapableBackend:
    can_start_from_frame = True


class _MediumShot:
    shot_type = "medium shot"


class _CloseUp:
    shot_type = "close-up"


def test_with_a_sheet_every_shot_of_a_person_starts_from_a_drawn_face(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    assert wants_first_frame(_MediumShot(), _FrameCapableBackend(), has_character=True)


def test_an_empty_shot_does_not_pay_for_a_face_it_does_not_have(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    assert not wants_first_frame(_MediumShot(), _FrameCapableBackend(), has_character=False)


def test_without_a_sheet_only_the_close_up_is_frame_started(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_CHARACTER_SHEET", raising=False)
    assert not wants_first_frame(_MediumShot(), _FrameCapableBackend(), has_character=True)
    assert wants_first_frame(_CloseUp(), _FrameCapableBackend(), has_character=True)


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    monkeypatch.setenv("MUSEFORGE_SHEET_FIRST_FRAME", "0")
    assert not wants_first_frame(_MediumShot(), _FrameCapableBackend(), has_character=True)


def test_a_backend_that_cannot_start_from_a_frame_is_never_asked_to():
    assert not wants_first_frame(_CloseUp(), object(), has_character=True)


# --- the job, again ----------------------------------------------------------


class _MiniMaxLike:
    """Declares what the H3 generator declares in reference mode."""

    accepts_reference_set = True
    can_start_from_frame = True
    uses_character_reference_to_video = True

    def __init__(self):
        self.calls = []

    async def generate_video_from_image(self, prompt, image_url, duration=5,
                                        aspect_ratio="16:9", plan="free",
                                        is_cancelled=None, shot_profile=None,
                                        **kwargs):
        self.calls.append({"prompt": prompt, "image_url": image_url, **kwargs})
        return "https://cdn/video.mp4"


@pytest.mark.asyncio
async def test_the_dock_again(monkeypatch, tmp_path):
    """Mira's two scenes on the rebuilt pipeline: every shot of her starts from
    a drawn frame, and the blackout's take is not shown the lit plate."""
    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    drawn = []

    async def fake_generate_image(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        return PLATE if "Empty location plate" in prompt else SHEET

    async def fake_ref(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        drawn.append(prompt)
        return f"https://cdn/frame_{len(drawn)}.jpg"

    class _Shot2:
        def __init__(self, text):
            self.idx = 0
            self.visual_desc = text
            self.motion_desc = "Mira leans on the lever."
            self.audio_desc = ""
            self.shot_type = "medium shot"
            self.camera_movement = "static"
            self.lens = "35mm"
            self.duration_seconds = 5.0
            self.frame_url = None
            self.video_url = None

        def model_dump(self, **kw):
            return {"idx": 0, "visual_desc": self.visual_desc, "motion_desc": self.motion_desc,
                    "duration_seconds": 5.0, "frame_url": self.frame_url,
                    "video_url": self.video_url}

    async def fake_storyboard(self, script, characters, *a, **kw):
        return [_Shot2(script)]

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(path, "wb").write(b"v")
        return path

    async def fake_concat(paths, out_path):
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        open(out_path, "wb").write(b"c")
        return out_path

    import agents.storyboard_artist as storyboard_mod
    import pipelines.idea2video as idea2video_mod
    import pipelines.script2video as script2video_mod
    import tools.muapi_image_generator as image_mod

    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image", fake_generate_image)
    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_ref)
    monkeypatch.setattr(storyboard_mod.StoryboardArtist, "design_storyboard", fake_storyboard)
    monkeypatch.setattr(script2video_mod, "download_video", fake_download)
    monkeypatch.setattr(script2video_mod, "concatenate_videos", fake_concat)
    monkeypatch.setattr(idea2video_mod, "concatenate_videos", fake_concat)

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    backend = _MiniMaxLike()
    pipeline.script2video.video_gen = backend

    script = DramaScript(
        title="Harbour",
        logline="x",
        setting_location=HARBOUR,
        setting_time_of_day="night",
        characters=[CharacterProfile(name="Mira", description="woman, late thirties", role="protagonist")],
        scenes=[
            ScriptScene(action="Mira crouches at the container's locking bar."),
            ScriptScene(action="Mira hauls the doors open.", world_change=BLACKOUT),
        ],
    )
    await pipeline.continue_from_script(script=script, working_dir=str(tmp_path / "job"))

    calls = sorted(backend.calls, key=lambda c: "hauls" in c["prompt"] or "dark" in c["prompt"])
    assert len(calls) == 2
    for call in calls:
        assert call["by_reference"] is False, "a sheet must not be the only face"
        assert call["image_url"].startswith("https://cdn/frame_"), "the take starts from a drawn face"
    blackout = next(c for c in backend.calls if BLACKOUT in c["prompt"])
    assert PLATE not in blackout["reference_images"]
    steady = next(c for c in backend.calls if BLACKOUT not in c["prompt"])
    assert PLATE in steady["reference_images"]
