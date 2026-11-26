"""Job d9682326: the voice on the radio was given a face.

Sol was written "heard only over the radio, never seen on screen". The script
also said "her radio crackles with Sol's warning", which the visibility check
read as Sol being present. So: a portrait, two of Mara's designed shots
replaced by "Close-up on Sol's face", an old man on screen at 16 s, and both
dialogue scenes refused lip sync as two-handers.

And the climax -- now carried across one take, before to after -- was undone
three more ways: its first frame was drawn from the storyboard's line about
the event (door already open, light already out); the lip sync redrew its
first 5.4 s from that frame; and Mara said "every light on the dock just
dropped" six seconds before any light did.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene, DramaScript, ScriptScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.idea2video import (  # noqa: E402
    EVENT_LINE_TAIL_SECONDS,
    _carries_the_event,
    _declared_voice_only,
    _heard_but_never_seen,
    _scene_opening,
    plan_scene_speech_anchors,
)
from pipelines.script2video import shot_at_the_opening  # noqa: E402

MARA = CharacterInScene(idx=0, name="Mara", static_features="woman in her late thirties")
SOL = CharacterInScene(
    idx=1,
    name="Sol",
    static_features="man in his sixties, heard only over the radio, never seen on screen",
    wardrobe="a battered steel radio handset, not applicable, voice only",
)


def _script():
    return DramaScript(
        title="Harbour",
        logline="x",
        scenes=[
            ScriptScene(
                action="Mara trudges between the containers, flashlight sweeping wet steel.",
                dialogue=[{"character": "Sol", "line": "Mara, you there?"},
                          {"character": "Mara", "line": "Yeah, copy."}],
                starts_with="Night, floodlights lit, Mara mid-patrol.",
            ),
            ScriptScene(
                action="Mara kneels at the locking bar; her radio crackles with Sol's warning but she keeps cutting.",
                dialogue=[{"character": "Sol", "line": "Leave the lock alone."}],
                ends_with="Mara's hand closing on the door handle, floodlights still lit.",
            ),
            ScriptScene(action="Mara hauls the door open.", world_change="every floodlight goes dark"),
        ],
    )


# --- who is seen -------------------------------------------------------------


def test_the_writer_s_own_words_hide_the_voice():
    assert _declared_voice_only(SOL)
    assert not _declared_voice_only(MARA)


def test_they_outrank_a_possessive_in_an_action_line():
    """"her radio crackles with Sol's warning" is not Sol in the frame."""
    assert "sol" in _heard_but_never_seen(_script(), [MARA, SOL])
    assert "mara" not in _heard_but_never_seen(_script(), [MARA, SOL])


@pytest.mark.parametrize(
    "description",
    [
        "a man who has never seen the sea",
        "an old sailor, unseen by the guards as he slips aboard",
        "woman, fifties, voice like gravel",
    ],
)
def test_words_that_merely_contain_the_phrase_do_not(description):
    assert not _declared_voice_only(CharacterInScene(idx=2, name="X", static_features=description))


@pytest.mark.parametrize(
    "description",
    ["a dispatcher, never seen", "woman, voice only", "harbourmaster, off-screen throughout"],
)
def test_the_ways_a_writer_says_it(description):
    assert _declared_voice_only(CharacterInScene(idx=2, name="X", static_features=description))


# --- the event's first frame --------------------------------------------------


def test_the_first_frame_of_the_event_take_is_the_scene_s_opening():
    shot = StoryboardShot(
        idx=0,
        visual_desc="Mara hauls the door wide, a seam exploding into blinding light",
        motion_desc="the door swings open",
        shot_type="close-up",
        lens="50mm",
    )
    opening = "Mara's hand closing on the door handle, floodlights still lit"
    before = shot_at_the_opening(shot, opening)
    assert before.visual_desc == opening
    assert before.shot_type == "close-up" and before.lens == "50mm"
    assert shot.visual_desc.startswith("Mara hauls"), "the storyboard's own shot is untouched"
    assert shot_at_the_opening(shot, "") is shot


def test_the_opening_is_how_the_scene_before_ended():
    scenes = _script().scenes
    assert _scene_opening(scenes, 2) == "Mara's hand closing on the door handle, floodlights still lit."
    assert _scene_opening(scenes, 0) == "Night, floodlights lit, Mara mid-patrol."


# --- the redraw and the line -----------------------------------------------------


def test_a_take_carrying_the_event_is_known_by_its_record():
    assert _carries_the_event([{"event_in_take": True}])
    assert not _carries_the_event([{"event_in_take": False}, {}])
    assert not _carries_the_event(None)


def _tracks(scene_index, seconds, after_event=False):
    track = {"scene_index": scene_index, "line": "every light on the dock just dropped",
             "end_seconds": seconds}
    if after_event:
        track["after_event"] = True
    return [track]


def test_the_reaction_is_said_after_the_event_not_before_it():
    """The climax runs 18 s to 30 s; its 4.8 s line ends just before the film does."""
    anchors = plan_scene_speech_anchors(_tracks(2, 4.8, after_event=True), [0.0, 10.0, 18.0], 30.0)
    assert anchors[2] == pytest.approx(30.0 - 4.8 - EVENT_LINE_TAIL_SECONDS)


def test_a_scene_in_the_middle_ends_its_line_before_the_next_one_starts():
    anchors = plan_scene_speech_anchors(_tracks(1, 3.0, after_event=True), [0.0, 10.0, 18.0], 30.0)
    assert anchors[1] == pytest.approx(18.0 - 3.0 - EVENT_LINE_TAIL_SECONDS)


def test_a_line_longer_than_the_scene_still_starts_with_the_picture():
    anchors = plan_scene_speech_anchors(_tracks(2, 13.0, after_event=True), [0.0, 10.0, 18.0], 30.0)
    assert anchors[2] == pytest.approx(18.0)


def test_every_other_scene_speaks_where_it_always_did():
    anchors = plan_scene_speech_anchors(_tracks(2, 4.8), [0.0, 10.0, 18.0], 30.0)
    assert anchors[2] == pytest.approx(18.0)


# --- the climax, end to end ----------------------------------------------------------


class _MiniMaxLike:
    accepts_reference_set = True
    can_start_from_frame = True
    uses_character_reference_to_video = True

    async def generate_video_from_image(self, prompt, image_url, duration=5,
                                        aspect_ratio="16:9", plan="free",
                                        is_cancelled=None, shot_profile=None, **kwargs):
        return "https://cdn/video.mp4"


@pytest.mark.asyncio
async def test_the_climax_s_first_frame_shows_the_door_still_shut(monkeypatch, tmp_path):
    from pipelines.script2video import Script2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    drawn = []

    async def fake_ref(self, prompt, references, aspect_ratio="16:9", is_cancelled=None, **kw):
        drawn.append(prompt)
        return f"https://cdn/drawn_{len(drawn)}.jpg"

    async def fake_design(self, script, characters, *a, **kw):
        return [StoryboardShot(
            idx=0,
            visual_desc="Mara hauls the container door wide, a seam exploding into blinding light",
            motion_desc="The container door swings fully open",
            shot_type="close-up",
            duration_seconds=12.0,
        )]

    async def fake_download(url, path):
        open(path, "wb").write(b"v")
        return path

    async def fake_trim(path, out_path, seconds, from_head=True):
        return path

    monkeypatch.setattr("agents.storyboard_artist.StoryboardArtist.design_storyboard", fake_design)
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image_with_reference", fake_ref
    )
    monkeypatch.setattr("pipelines.script2video.download_video", fake_download)
    monkeypatch.setattr("pipelines.script2video.trim_to_duration", fake_trim)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    pipeline.video_gen = _MiniMaxLike()
    await pipeline.run(
        script="Mara hauls the container door open; every floodlight goes black.",
        characters=[MARA],
        working_dir=str(tmp_path),
        character_portraits={"Mara": "https://cdn/mara_sheet.jpg"},
        location_plate_url="https://cdn/plate.jpg",
        setting_location="rain-soaked cargo harbour dock",
        setting_time_of_day="night",
        world_change="every floodlight on the dock goes dark",
        scene_duration=12.0,
        scene_opening="Mara's hand closing on the container's door handle, floodlights still lit",
    )

    opening = drawn[0]
    assert "door handle, floodlights still lit" in opening
    assert "exploding into blinding light" not in opening
