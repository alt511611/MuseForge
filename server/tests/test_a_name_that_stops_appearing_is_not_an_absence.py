"""A character can be at the table and never be named again after page one.

_heard_but_never_seen decided that a speaker whose name appears in no ACTION
line is somebody the film never shows. That is an argument from missing
evidence, and it fails on an ordinary writing habit: a writer names "The
Stranger" once in the cast list and then calls him "the man across the table"
for the rest of the script. The less personal the name, the likelier the
character is a scene partner AND the likelier the name never appears again --
so the rule was wrongest exactly where it was most expensive.

Delivered job 754796ce-c04, brief "A card dealer in a basement game realises
the man across the table is copying her own tell": the man across the table
was marked never-seen. He is opposite her in two scenes of three. Having no
portrait, he was drawn from the only portrait that existed -- hers -- so the
delivered film is two versions of one face at one table, while the closed-cast
clause told the image model that only the dealer appears in this story.

The absence now has to be corroborated: something in the script must actually
stage a voice arriving without a body. The harbour drama that this check was
built for says "Her radio crackles" and keeps its off-screen controller. The
card room says nothing of the kind and keeps its second player.

The change adds a condition and removes none, so its answer is always a subset
of the old one -- it can only ever spare a character the old rule would have
hidden, never hide one it would have spared.
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
from pipelines.idea2video import (  # noqa: E402
    Idea2VideoPipeline,
    _heard_but_never_seen,
)
from pipelines.script2video import (  # noqa: E402
    build_cast_closure_clause,
    mentions_an_off_screen_device,
    on_screen_name_matches,
)


def _script(*scenes, cast):
    return DramaScript(
        title="T",
        logline="L",
        scenes=list(scenes),
        characters=[CharacterProfile(name=n, description=d) for n, d in cast],
    )


def _visibility(script):
    cast = Idea2VideoPipeline("test-key")._characters_from_script(script)
    return {c.name: c.is_visible for c in cast}


#: The delivered card room: the second player is named in the cast and called
#: "the man" in every action line after that.
CARD_ROOM = _script(
    ScriptScene(
        action="Mara deals. Across the table, the man mirrors the gesture exactly.",
        dialogue=[
            {"character": "Mara", "line": "You tap it."},
            {"character": "The Stranger", "line": "That's the game."},
        ],
    ),
    ScriptScene(
        action="Mara's thumb grazes the deck. The man opposite does the same.",
        dialogue=[
            {"character": "Mara", "line": "You're copying me."},
            {"character": "The Stranger", "line": "Not copying. Remembering."},
        ],
    ),
    cast=(("Mara", "woman, fifties"), ("The Stranger", "gaunt, black hat")),
)

#: The delivered harbour: a controller who exists only on a radio.
HARBOUR = _script(
    ScriptScene(
        action="Rain hammers the containers. Mara sweeps her flashlight along Bay 14.",
        dialogue=[{"character": "Tomas", "line": "Keep moving, Voss."}],
    ),
    ScriptScene(
        action="Mara crouches at the release lever. Her radio crackles.",
        dialogue=[
            {"character": "Mara", "line": "Bay 14 is humming."},
            {"character": "Tomas", "line": "Step back."},
        ],
    ),
    cast=(("Mara", "woman, thirties"), ("Tomas", "man, fifties")),
)


# ── the two delivered shapes ────────────────────────────────────────────────


def test_the_man_across_the_table_keeps_his_face():
    assert _visibility(CARD_ROOM) == {"Mara": True, "The Stranger": True}


def test_the_voice_on_the_radio_still_has_none():
    """The fix this replaces, which must survive intact: the corroboration is
    there in "Her radio crackles", so the controller is still hidden."""
    assert _visibility(HARBOUR) == {"Mara": True, "Tomas": False}


def test_the_card_room_cast_clause_stops_lying():
    """The symptom the delivered film showed. With one visible character the
    clause told the image model "only Mara appears in this story" over a shot
    with two people in it, and both were drawn from Mara's portrait."""
    cast = Idea2VideoPipeline("test-key")._characters_from_script(CARD_ROOM)
    for character in cast:
        character.static_features = character.static_features or "described"

    clause = build_cast_closure_clause(cast)
    assert "Mara, The Stranger appear in this story" in clause
    # The one-hander wording is what the delivered job carried into every
    # frame of a two-hander: "only Mara appears in this story".
    assert "only Mara" not in clause


def test_a_radio_staged_in_a_later_scene_still_counts():
    """Read across the whole script, not per scene: a handset established in
    scene 2 explains a voice in scene 1."""
    script = _script(
        ScriptScene(
            action="Mara deals.",
            dialogue=[{"character": "Control", "line": "Hold."}],
        ),
        ScriptScene(
            action="Mara lifts the handset to her ear.",
            dialogue=[{"character": "Mara", "line": "Say again."}],
        ),
        cast=(("Mara", "woman"), ("Control", "a voice")),
    )
    assert _visibility(script) == {"Mara": True, "Control": False}


def test_a_script_that_names_nobody_anywhere_is_still_left_alone():
    """The earlier guard, unchanged: marking the whole cast invisible would
    leave every frame with no identity lock at all."""
    script = _script(
        ScriptScene(
            action="Rain on the roof. A radio hisses.",
            dialogue=[{"character": "Mara", "line": "Anyone?"}],
        ),
        cast=(("Mara", "woman"), ("Tomas", "man")),
    )
    assert _visibility(script) == {"Mara": True, "Tomas": True}


def test_the_decision_is_logged(caplog):
    with caplog.at_level("INFO"):
        _visibility(CARD_ROOM)
    assert any(
        "kept visible" in r.getMessage() and "the stranger" in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


# ── it can only ever spare, never hide ──────────────────────────────────────


def _the_old_rule(script, cast):
    """What _heard_but_never_seen returned before the corroboration."""
    on_screen, speaks = set(), set()
    for scene in script.scenes or []:
        for _, character in on_screen_name_matches(scene.action.lower(), cast):
            on_screen.add(character.name.casefold())
        for line in scene.dialogue or []:
            speaks.add(str(line.character).strip().casefold())
    if not on_screen:
        return set()
    return {name for name in speaks if name not in on_screen}


def test_the_answer_is_always_a_subset_of_the_old_answer():
    """The property that makes this safe to ship: a condition was added and
    none removed, so no character can be hidden now who was visible before."""
    for script in (CARD_ROOM, HARBOUR):
        cast = Idea2VideoPipeline("test-key")._characters_from_script(script)
        # _characters_from_script has already applied the result; read the
        # rule directly against an all-visible cast to compare like with like.
        for character in cast:
            character.is_visible = True
        assert _heard_but_never_seen(script, cast) <= _the_old_rule(script, cast)


# ── which words count as a device ───────────────────────────────────────────


def test_the_things_that_carry_a_voice_without_a_body():
    for text in (
        "Her radio crackles.",
        "Two radios on the crate.",
        "Mara lifts the handset.",
        "A voice on the intercom.",
        "TOMAS (O.S.) somewhere behind the door.",
        "The answer comes over the line.",
        "She puts him on the phone.",
    ):
        assert mentions_an_off_screen_device(text), text


def test_the_words_that_describe_somebody_in_the_room_do_not():
    """The reason this vocabulary is narrower than _OFF_SCREEN_MARKERS: those
    are read in a window after a NAME, where "Priya's voice" settles it. Read
    across a whole script these are all people who are present."""
    for text in (
        "His voice drops to nothing.",
        "The speaker leans in.",
        "The fire crackles in the grate.",
        "Heat ticks through the radiator.",
        "Mara deals. Across the table, the man mirrors the gesture.",
        "",
    ):
        assert not mentions_an_off_screen_device(text), text
