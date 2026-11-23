"""Job 82c56e88, scenes 2 and 4.

"tense confrontation" lived on the suspicion beat, whose peak is "the smile
staying on the mouth": Tomas grinned over the table while begging to go for help.
And scene 4's empty dawn room was told "the dead radio's light glows red and
fills the silent hut with a live voice" -- scene 3's event, inherited as a
standing fact -- and drew a burning stove in a room the script says is cold.
Two cast members drawn twice (a second Mira at the stove) is the third thing.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces import acting  # noqa: E402
from interfaces.character import CharacterInScene, ScriptScene  # noqa: E402
from pipelines.idea2video import _world_state  # noqa: E402
from pipelines.script2video import build_cast_closure_clause  # noqa: E402


def test_a_confrontation_is_not_acted_with_a_smile():
    for tag in ("tense confrontation", "tense", "heated argument", "gergin yüzleşme"):
        beat = acting.resolve(tag)
        assert beat.label == "confrontation"
        assert "smile" not in beat.peak.replace("no trace of a smile", "")


def test_suspicion_still_has_its_poker_face():
    assert acting.resolve("suspicion").label == "suspicion"
    assert "smile" in acting.resolve("wary").peak


def _scene(**kw):
    base = dict(idx=0, environment="hut", characters=[], story="x", action="y")
    base.update(kw)
    return ScriptScene(**base)


def test_a_scene_that_states_how_it_opens_does_not_inherit_the_last_events_aftermath():
    scenes = [
        _scene(),
        _scene(world_change="the dead radio's light glows red and fills the hut with a live voice"),
        _scene(starts_with="Dawn, storm passed, the stove cold, the radio silent."),
    ]
    _, standing = _world_state(scenes, 2)
    assert "glows red" not in standing
    assert "cold" in standing


def test_without_a_stated_opening_the_earlier_change_still_stands():
    scenes = [_scene(world_change="the power dies"), _scene()]
    _, standing = _world_state(scenes, 1)
    assert standing == "the power dies"


def _c(name):
    return CharacterInScene(idx=0, name=name, static_features="a person", wardrobe="coat")


def test_a_cast_of_several_is_told_each_appears_once():
    assert "each exactly once" in build_cast_closure_clause([_c("Mira"), _c("Tomas")])


def test_a_lone_character_clause_is_unchanged():
    clause = build_cast_closure_clause([_c("Mira")])
    assert clause.startswith("Cast is closed: only Mira appears.")
