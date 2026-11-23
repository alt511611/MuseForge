"""Job 8d082bf7: Tomas was in the room and was treated as a voice.

"Tomas holds a dead radio against his ear" has a device within 30 characters
of his name, and the heard-not-seen reader took the device for evidence that
he was a voice. He lost his portrait and his place in the closed cast, and was
drawn from text alone: in Mira's orange jacket, clean-shaven.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene, DramaScript, ScriptScene  # noqa: E402
from pipelines.idea2video import _heard_but_never_seen  # noqa: E402
from pipelines.script2video import on_screen_name_matches  # noqa: E402

TOMAS = CharacterInScene(idx=0, name="Tomas", static_features="a bearded man", wardrobe="green parka")
MIRA = CharacterInScene(idx=1, name="Mira", static_features="a rescuer", wardrobe="orange jacket")


def _names(text, cast=(TOMAS, MIRA)):
    return [c.name for _, c in on_screen_name_matches(text.lower(), list(cast))]


def test_a_man_holding_a_radio_is_on_screen():
    assert "Tomas" in _names("Tomas holds a dead radio against his ear while Mira feeds the stove.")


def test_a_man_slamming_a_radio_down_is_on_screen():
    assert "Tomas" in _names("Tomas slams the radio down on the table.")


def test_a_voice_over_the_radio_is_still_not_on_screen():
    assert "Tomas" not in _names("Tomas's voice crackles over the radio as Mira presses the seal.")
    assert "Tomas" not in _names("Tomas, on the intercom, warns her.")
    assert "Tomas" not in _names("Tomas (O.S.) calls out.")


def _scene(action, dialogue):
    return ScriptScene(idx=0, environment="hut", characters=["Tomas", "Mira"], story="s",
                       action=action, dialogue=dialogue)


def test_a_speaker_who_handles_the_radio_in_every_scene_keeps_his_face():
    script = SimpleNamespace(scenes=[
        _scene("Tomas holds a dead radio against his ear. Mira feeds the stove.",
               [{"character": "Tomas", "line": "Nothing."}]),
        _scene("Tomas slams the radio on the table and argues with Mira.",
               [{"character": "Tomas", "line": "Someone has to go."}]),
    ])
    assert _heard_but_never_seen(script, [TOMAS, MIRA]) == set()
