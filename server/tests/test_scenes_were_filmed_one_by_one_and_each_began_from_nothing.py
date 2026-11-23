"""Scenes are storyboarded and rendered in parallel, each knowing only its own action.

``story_so_far`` carries the earlier scenes' TURNS, not the physical state they
left: the crew who ended scene 2 soaked on a boat at night opened scene 3 dry on
a beach at dusk. The writer now states ``ends_with`` / ``starts_with`` per
scene, the pipeline holds them to each other, and the storyboard is told the
state its scene opens in.
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.character import DramaScript, ScriptScene  # noqa: E402
from interfaces.continuity import opening_state, reconcile  # noqa: E402
from pipelines.idea2video import _format_story_state  # noqa: E402


def _scenes(*pairs):
    return [ScriptScene(action=f"a{i}", turn=f"t{i}", starts_with=s, ends_with=e) for i, (s, e) in enumerate(pairs)]


def test_the_fields_are_optional_so_stored_scripts_still_load():
    scene = ScriptScene(action="x")
    assert scene.starts_with == "" and scene.ends_with == ""


def test_the_writer_is_asked_for_both_and_told_to_chain_them():
    prompt = ScreenwriterAgent.SYSTEM_PROMPT
    assert '"starts_with"' in prompt and '"ends_with"' in prompt
    assert "previous scene's \"ends_with\"" in prompt
    assert "JUMP:" in prompt


def test_a_scene_that_opens_dry_after_one_that_ended_soaked_is_repaired():
    scenes = _scenes(
        ("five castaways on the shingle", "all five soaked, adrift on the boat at night"),
        ("five castaways dry on the shore at dawn", "they huddle"),
    )
    notes = reconcile(scenes)
    assert scenes[1].starts_with == "all five soaked, adrift on the boat at night"
    assert len(notes) == 1


def test_a_scene_with_no_opening_gets_the_previous_ending():
    scenes = _scenes(("a", "Yusuf holds the flare, wet to the skin"), ("", "x"))
    reconcile(scenes)
    assert scenes[1].starts_with == "Yusuf holds the flare, wet to the skin"


def test_a_consistent_pair_is_left_alone():
    scenes = _scenes(("a", "soaked on the boat"), ("still soaked, the boat drifting", "x"))
    assert reconcile(scenes) == []
    assert scenes[1].starts_with == "still soaked, the boat drifting"


def test_a_declared_time_jump_is_respected():
    scenes = _scenes(("a", "soaked at night"), ("JUMP: three days later, dry and sunburnt", "x"))
    assert reconcile(scenes) == []
    assert scenes[1].starts_with.startswith("JUMP:")


def test_legacy_string_scenes_are_ignored():
    assert reconcile(["one", "two"]) == []


def test_the_script_is_reconciled_on_every_path():
    script = DramaScript(
        title="t", logline="l",
        scenes=_scenes(("a", "soaked at night"), ("dry at noon", "x")),
    )
    ScreenwriterAgent._with_brief(script, "a brief", 0)
    assert script.scenes[1].starts_with == "soaked at night"


def test_the_storyboard_is_told_the_state_its_scene_opens_in():
    scenes = _scenes(("a", "soaked at night"), ("", "x"))
    before, _ = _format_story_state(scenes, 1)
    assert "THIS SCENE OPENS IN THIS STATE" in before
    assert "soaked at night" in before


def test_the_first_scene_is_told_nothing_it_cannot_know():
    scenes = _scenes(("opening situation", "soaked"), ("", "x"))
    before, _ = _format_story_state(scenes, 0)
    assert "OPENS IN THIS STATE" not in before
    assert opening_state(scenes, 0) == ""
