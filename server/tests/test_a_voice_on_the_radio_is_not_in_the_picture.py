"""A character the film only ever HEARS is not part of its picture.

``is_visible`` is the field that says so, and nothing ever set it: every
character came back visible. Delivered against a brief with one dock worker in
it -- and a script whose only other presence is "Her radio crackles" -- a
second character spoke through all three scenes, appeared in none, and still:

  * had a portrait generated for a face that is never on screen;
  * took a place in the closed-cast clause, which tells the image model "X and
    Y appear in this story";
  * held one end of the 180-degree axis, which tells EVERY frame which way the
    other person is facing -- an axis drawn to somebody who is not there.

Seen is read from the action lines with the same rule that picks each shot's
reference portrait, so the cast-level answer and the frame-level one cannot
disagree.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import (  # noqa: E402
    CharacterProfile,
    DramaScript,
    ScriptScene,
)
from pipelines.idea2video import Idea2VideoPipeline  # noqa: E402


def _script(*scenes, cast=(("Mara", "woman, thirties"), ("Tomas", "man, fifties"))):
    return DramaScript(
        title="T",
        logline="L",
        scenes=list(scenes),
        characters=[CharacterProfile(name=n, description=d) for n, d in cast],
    )


def _visibility(script):
    cast = Idea2VideoPipeline("test-key")._characters_from_script(script)
    return {c.name: c.is_visible for c in cast}


# ── the delivered shape ─────────────────────────────────────────────────────


def test_a_voice_that_never_appears_is_marked_invisible():
    """The delivered drama: Mara in every action line, Tomas in none of them
    and in all of the dialogue."""
    script = _script(
        ScriptScene(
            action="Rain hammers the containers. Mara sweeps her flashlight along Bay 14.",
            dialogue=[{"character": "Tomas", "line": "Keep moving, Voss."}],
        ),
        ScriptScene(
            action="Mara crouches at the release lever. Her radio crackles.",
            dialogue=[
                {"character": "Mara", "line": "Bay 14 is humming."},
                {"character": "Tomas", "line": "Say again?"},
            ],
        ),
        ScriptScene(
            action="Mara throws her weight against the lever.",
            dialogue=[{"character": "Mara", "line": "The whole city's out."}],
        ),
    )

    assert _visibility(script) == {"Mara": True, "Tomas": False}


def test_a_name_that_appears_only_as_a_voice_still_counts_as_heard():
    """Same rule the reference portrait is chosen by: being named in an action
    line is not the same as being in the picture."""
    script = _script(
        ScriptScene(
            action="Mara works the seal as Tomas's voice crackles over the radio.",
            dialogue=[{"character": "Tomas", "line": "Get out of there."}],
        )
    )

    assert _visibility(script) == {"Mara": True, "Tomas": False}


def test_a_two_hander_on_camera_is_untouched():
    """The path almost every drama takes has to stay exactly as it was."""
    script = _script(
        ScriptScene(
            action="Mara and Tomas haul the door open together.",
            dialogue=[{"character": "Tomas", "line": "Now."}],
        )
    )

    assert _visibility(script) == {"Mara": True, "Tomas": True}


def test_a_silent_character_nobody_names_is_left_alone():
    """This fires on evidence of being HEARD, not on absence. A character with
    no lines and no mention is under-written, and the storyboard may still
    stage them -- taking their portrait away would render a stranger."""
    script = _script(
        ScriptScene(
            action="Mara walks the rows.",
            dialogue=[{"character": "Mara", "line": "Hm."}],
        ),
        cast=(("Mara", "woman"), ("Deniz", "man")),
    )

    assert _visibility(script) == {"Mara": True, "Deniz": True}


def test_action_lines_that_name_nobody_never_empty_the_cast():
    """A script written without names in its action ("They argue in the rain")
    proves nothing about who is on screen, and marking the whole cast
    invisible would leave every frame with no identity lock at all."""
    script = _script(
        ScriptScene(
            action="They argue in the rain.",
            dialogue=[
                {"character": "Tomas", "line": "No."},
                {"character": "Mara", "line": "Yes."},
            ],
        )
    )

    assert _visibility(script) == {"Mara": True, "Tomas": True}


# ── what being invisible actually buys ──────────────────────────────────────


def test_the_closed_cast_stops_claiming_they_appear():
    from interfaces.character import CharacterInScene
    from pipelines.script2video import build_cast_closure_clause

    mara = CharacterInScene(idx=0, name="Mara", static_features="woman, thirties")
    tomas = CharacterInScene(
        idx=1, name="Tomas", static_features="man, fifties", is_visible=False
    )

    clause = build_cast_closure_clause([mara, tomas])
    assert "only Mara appears in this story" in clause
    assert "Tomas" not in clause


def test_the_180_degree_axis_is_not_drawn_to_someone_who_is_not_there():
    """The rule locks frame-left and frame-right for the whole drama,
    including in singles -- so an axis drawn to an absent character aims every
    shot's eyeline at nobody."""
    from interfaces.character import CharacterInScene
    from pipelines.script2video import build_screen_direction_clause

    mara = CharacterInScene(idx=0, name="Mara", static_features="woman, thirties")
    tomas = CharacterInScene(
        idx=1, name="Tomas", static_features="man, fifties", is_visible=False
    )

    assert build_screen_direction_clause([mara, tomas]) == ""
    tomas.is_visible = True
    assert "Mara" in build_screen_direction_clause([mara, tomas])


def test_no_portrait_is_generated_for_a_face_that_is_never_seen():
    """A generated portrait is a paid image call. Reading the guard rather
    than running it: _lock_character_portraits skips invisible cast."""
    import inspect

    source = inspect.getsource(Idea2VideoPipeline._lock_character_portraits)
    assert "if not char.is_visible:" in source
    assert "continue" in source


def test_the_shot_designer_is_told_the_voice_is_a_voice():
    """Removing them from the cast list is not enough on its own: that list is
    what the designer is given to DESCRIBE, so a voice dropped from it simply
    vanishes -- and the designer, reading a scene where the name plainly
    speaks, is free to stage a person nobody described. The marker is
    screenwriting's own, and one the frame step already reads."""
    from pipelines.idea2video import _format_scene_dialogue

    lines = [
        {"character": "Mara", "line": "Bay 14 is humming."},
        {"character": "Tomas", "line": "Keep moving, Voss."},
    ]

    block = _format_scene_dialogue(lines, off_screen={"tomas"})

    assert "Mara: Bay 14 is humming." in block
    assert "Tomas (O.S." in block
    assert "never in frame" in block
    assert "do not stage them" in block


def test_a_scene_with_everyone_on_camera_reads_exactly_as_before():
    from pipelines.idea2video import _format_scene_dialogue

    lines = [{"character": "Mara", "line": "Now."}]
    assert _format_scene_dialogue(lines) == "Mara: Now."
    assert _format_scene_dialogue(lines, off_screen=set()) == "Mara: Now."
