"""The drama's event has to be visible, not only audible.

`world_change` is the only field that lets a scene break the drama's locked
lighting. A script that leaves it empty renders its climax under the opening
scene's lamps, however well the rest is written -- and a VOICED script makes
the failure easy, because a character can simply say the thing happened.

_apply_brief_event already restored the event when the USER'S BRIEF stated it.
It did nothing when the brief did not and the script invented one. Delivered
drama, three scenes, `world_change` empty everywhere, the climax spoken as

    "Denny — Denny, see this? The grid just—"

and rendered with every streetlight, container lamp and lit doorway in the
yard still burning. The event of the film was audible and invisible.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.character import DramaScript, ScriptScene  # noqa: E402


def _scene(function, action="", dialogue=None, world_change=""):
    return ScriptScene(
        action=action,
        dramatic_function=function,
        dialogue=dialogue or [],
        world_change=world_change,
        tension=5,
    )


def _script(scenes, brief=""):
    script = DramaScript(title="T", logline="L", scenes=scenes)
    script.user_brief = brief
    return script


def _apply(script):
    ScreenwriterAgent._apply_brief_event(script)
    return script


# ── the delivered failure ───────────────────────────────────────────────────


def test_an_event_stated_only_in_dialogue_reaches_world_change():
    script = _script([
        _scene("setup", action="Mara walks the container rows."),
        _scene("rising_action", action="She reaches Bay 9."),
        _scene(
            "climax",
            action="Mara keys the radio.",
            dialogue=[{"character": "Mara", "line": "Denny, see this? The power goes out across the whole yard."}],
        ),
    ])

    _apply(script)

    assert script.scenes[2].world_change, "the event never reached the picture"
    assert "power goes out" in script.scenes[2].world_change


def test_an_event_stated_only_in_an_action_line_also_counts():
    """The same failure without dialogue: prose the image step never reads."""
    script = _script([
        _scene("setup", action="Mara walks the rows."),
        _scene("climax", action="She throws the latch and every light goes out."),
    ])

    _apply(script)

    assert script.scenes[1].world_change


def test_it_lands_on_the_climax_not_wherever_it_was_said():
    """A character can mention the blackout a scene before it happens. The
    field belongs on the scene where the world actually changes."""
    script = _script([
        _scene(
            "rising_action",
            dialogue=[{"character": "Mara", "line": "If the power fails we lose the cameras."}],
        ),
        _scene("climax", action="She opens the door."),
    ])

    _apply(script)

    assert script.scenes[1].world_change
    assert not script.scenes[0].world_change


# ── the refusals, which are the point ───────────────────────────────────────


def test_a_script_that_named_its_own_change_is_left_alone():
    """The model read the whole story; this reads a word list."""
    script = _script([
        _scene("setup", action="Mara walks."),
        _scene(
            "climax",
            action="She opens it.",
            world_change="the harbour is now black except for the container's glow",
            dialogue=[{"character": "Mara", "line": "The power's gone."}],
        ),
    ])

    _apply(script)

    assert script.scenes[1].world_change == (
        "the harbour is now black except for the container's glow"
    )


def test_two_different_events_are_not_guessed_between():
    """Choosing which of two changes is THE event is a judgement a word list
    has no business making, so it defers rather than picking."""
    script = _script([
        _scene("setup", dialogue=[{"character": "A", "line": "The lights go out at ten."}]),
        _scene("climax", dialogue=[{"character": "B", "line": "The water floods the pier."}]),
    ])

    _apply(script)

    assert not any((s.world_change or "").strip() for s in script.scenes)


def test_a_drama_with_no_stated_event_gains_nothing():
    """Most dramas have no world-scale change at all, and inventing one would
    break the locked lighting for a story that never asked."""
    script = _script([
        _scene("setup", action="Mara walks the rows."),
        _scene("climax", dialogue=[{"character": "Mara", "line": "I'm opening it."}]),
    ])

    _apply(script)

    assert not any((s.world_change or "").strip() for s in script.scenes)


def test_the_brief_still_wins_when_it_states_the_event():
    """The user's own words outrank the model's paraphrase of them."""
    script = _script(
        [
            _scene("setup", action="Mara walks."),
            _scene("climax", dialogue=[{"character": "Mara", "line": "The grid just failed."}]),
        ],
        brief="A dock worker opens a container and the power dies across the city.",
    )

    _apply(script)

    assert "power dies" in script.scenes[1].world_change
