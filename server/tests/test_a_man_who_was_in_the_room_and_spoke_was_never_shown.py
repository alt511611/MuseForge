"""Job 21a87c5a: Ilya has a portrait, a place in the cast and a line -- and no shot.

The storyboard wrote "Tomas hears Ilya's voice answer from the shadowed
doorway", so "Nobody goes out in this" played over Tomas's face. The prompt
already tells the artist the picture follows the sound; a model can ignore a
prompt, so the pipeline checks.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402

TOMAS = CharacterInScene(idx=0, name="Tomas", static_features="a bearded man", wardrobe="parka")
MIRA = CharacterInScene(idx=1, name="Mira", static_features="a rescuer", wardrobe="orange jacket")
ILYA = CharacterInScene(idx=2, name="Ilya", static_features="an old man", wardrobe="felt hat")
CAST = [TOMAS, MIRA, ILYA]
DIALOGUE = "Tomas: Someone has to go down for help.\nIlya: Nobody goes out in this."


def _shot(visual, shows=None):
    return StoryboardShot(idx=0, visual_desc=visual, motion_desc="still", shows_people=shows)


def _scene():
    return [
        _shot("Tomas lowers the radio at the table while Mira feeds the stove"),
        _shot("Tomas's bearded face fills the frame as he hears Ilya's voice answer from the shadowed doorway"),
        _shot("the radio's dial light flickers on the table", shows=False),
    ]


def test_a_speaker_the_storyboard_wrote_as_a_voice_is_put_on_screen():
    shots = StoryboardArtist._ensure_speakers_are_shown(_scene(), CAST, DIALOGUE, "tense confrontation")
    text = " ".join(s.visual_desc for s in shots)
    assert "Close-up on Ilya's face" in text
    assert "Nobody goes out in this" in text


def test_the_empty_shot_and_the_master_are_left_alone():
    shots = StoryboardArtist._ensure_speakers_are_shown(_scene(), CAST, DIALOGUE, "")
    assert shots[0].visual_desc.startswith("Tomas lowers the radio")
    assert shots[2].shows_people is False
    assert shots[2].visual_desc == "the radio's dial light flickers on the table"


def test_a_speaker_who_is_already_shown_changes_nothing():
    scene = _scene()
    scene[1].visual_desc = "Ilya sits across the table, hat low, answering Tomas"
    before = [s.visual_desc for s in scene]
    StoryboardArtist._ensure_speakers_are_shown(scene, CAST, DIALOGUE, "")
    assert [s.visual_desc for s in scene] == before


def test_a_voice_only_speaker_is_never_put_on_screen():
    dialogue = "Tomas: Hello?\nLena (O.S.): Refuge, this is dispatch."
    scene = _scene()
    before = [s.visual_desc for s in scene]
    StoryboardArtist._ensure_speakers_are_shown(scene, CAST + [], dialogue, "")
    assert [s.visual_desc for s in scene] == before


def test_a_one_shot_scene_is_not_rewritten():
    scene = [_shot("Tomas stares at the radio")]
    StoryboardArtist._ensure_speakers_are_shown(scene, CAST, DIALOGUE, "")
    assert scene[0].visual_desc == "Tomas stares at the radio"


def test_it_runs_as_the_last_step_of_every_storyboard():
    shots = StoryboardArtist._finish_shots(
        _scene(), "tense confrontation", False, 3, 10.0,
        characters=CAST, scene_dialogue=DIALOGUE,
    )
    assert any("Ilya" in s.visual_desc and "Close-up" in s.visual_desc for s in shots)
