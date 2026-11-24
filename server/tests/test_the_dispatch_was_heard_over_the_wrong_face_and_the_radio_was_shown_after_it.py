"""Job 82c56e88: the picture did not follow the sound.

Scene 3 played Mira's "Tell them to stop the search" over eight seconds of
Tomas, "listening, not speaking" -- the derived reaction cut assumed whoever the
master shot named was the one the scene was about, not the one whose line was
still running. The radio that Lena's voice comes out of was shown last, after
the voice had finished, because every empty beat was reinserted at the end of
the scene instead of where the designer had put it.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402

MIRA = CharacterInScene(idx=0, name="Mira", static_features="a rescuer", wardrobe="orange jacket")
TOMAS = CharacterInScene(idx=1, name="Tomas", static_features="a bearded man", wardrobe="green parka")
CAST = [MIRA, TOMAS]

DIALOGUE = (
    "Lena (O.S. — a voice only, heard over comms and never in frame; do not stage them): "
    "Refuge, this is dispatch. Is Mira there?\n"
    "Mira: I'm here. Tell them to stop the search."
)


def _shot(visual, shows=None, dur=5.0):
    return StoryboardShot(
        idx=0, visual_desc=visual, motion_desc="still", duration_seconds=dur, shows_people=shows
    )


def _plan(shots, dialogue, monkeypatch):
    monkeypatch.setenv("MUSEFORGE_REACTION_SHOTS", "1")
    return StoryboardArtist._apply_shot_plan(
        shots, "stunned relief", 8, CAST, False, 12.0,
        last_speaker=StoryboardArtist._last_visible_speaker(dialogue),
    )


def test_a_voice_only_line_is_not_the_last_speaker():
    assert StoryboardArtist._last_visible_speaker(DIALOGUE) == "Mira"
    only_radio = "Lena (O.S.): Say again, is Mira there?"
    assert StoryboardArtist._last_visible_speaker(only_radio) == ""


def test_the_master_carries_the_whole_scene_when_its_subject_speaks_last(monkeypatch):
    out = _plan([_shot("Mira's face fills the frame as she keys the radio")], DIALOGUE, monkeypatch)
    # No cutaway at all: neither Tomas under Mira's words, nor a one-person
    # "extreme close-up on the eyes and mouth" the model drew as a full body
    # (job 21a87c5a).
    assert len(out) == 1
    assert out[0].deliver_seconds == 0.0
    assert out[0].duration_seconds == 12.0
    assert "Extreme close-up" not in out[0].visual_desc


def test_the_cutaway_still_goes_to_the_listener_when_the_speaker_is_done(monkeypatch):
    out = _plan(
        [_shot("Mira's face fills the frame")], "Mira: Wait.\nTomas: I can't.", monkeypatch
    )
    assert "Tomas" in out[1].visual_desc


def test_an_empty_beat_in_the_middle_stays_in_the_middle(monkeypatch):
    shots = [
        _shot("Mira kneels at the stove", shows=True),
        _shot("the radio glows red on the table", shows=False, dur=3.0),
        _shot("Tomas stares at it", shows=True),
    ]
    out = StoryboardArtist._apply_shot_plan(shots, "dread", 3, CAST, False, 12.0)
    order = [s.shows_people is False for s in out]
    assert order.index(True) not in (0, len(order) - 1) or len(out) == 2
    assert "radio" in out[order.index(True)].visual_desc


def test_an_empty_beat_before_every_face_still_leads(monkeypatch):
    shots = [
        _shot("the hut in the blizzard", shows=False, dur=3.0),
        _shot("Mira kneels at the stove", shows=True),
    ]
    out = StoryboardArtist._apply_shot_plan(shots, "dread", 3, CAST, False, 9.0)
    assert out[0].visual_desc == "the hut in the blizzard"


def test_the_storyboard_prompt_tells_the_artist_to_open_on_the_source_of_a_voice():
    import inspect

    source = inspect.getsource(sys.modules[StoryboardArtist.__module__])
    assert "THE PICTURE FOLLOWS THE SOUND" in source
    assert "Open the scene on the source of the first voice" in source
