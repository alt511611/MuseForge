"""What the wardrobe does not name, the render invents afresh every shot.

The screenwriter prompt already knows this and already says it -- and then
applies it to the head alone: name the hat or write "bare-headed", because
"the render only holds what the wardrobe named". The delivered evidence says
the rule is right and its scope was wrong.

Job 8b8fce47-445 dressed its lead in

    a yellow hooded rain slicker with a reflective blue band across the chest,
    black gloves, dark waterproof trousers

and across six shots her HOOD -- the part that was named -- never moved,
while the slicker:

    buttoned, then zipped, then hung open
    went matte, then glossy PVC
    grew flap pockets, then patch pockets, then none
    put the band on her chest, then her sleeves, then nowhere
    printed lettering on the breast in one shot
    and carried a backpack in exactly one shot of six

Every one of those is a property the wardrobe never settled. None of them can
be fixed downstream: the frame prompt restates the wardrobe verbatim, so an
underspecified garment is underspecified in all six prompts, and the reference
portrait binds a face rather than an outfit.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_CHARS,
    build_character_identity_clause,
    build_frame_prompt,
)


# ── what the writer is asked for ────────────────────────────────────────────


def test_the_head_rule_still_stands():
    """It works -- the hood is the one thing that held across all six shots.
    This is the rule being extended, not replaced."""
    assert "HEAD DOWN" in ScreenwriterAgent.SYSTEM_PROMPT
    assert "bare-headed" in ScreenwriterAgent.SYSTEM_PROMPT


@pytest.mark.parametrize(
    "settled",
    ["how it fastens", "what pockets", "material", "marking or lettering", "back"],
)
def test_the_garment_is_settled_the_same_way(settled):
    """Each of these is a property that visibly changed shot to shot."""
    assert settled in ScreenwriterAgent.SYSTEM_PROMPT


def test_the_rule_is_kept_to_a_phrase():
    """A wardrobe is restated in full on every frame prompt, which is already
    fighting for room -- so this asks for settled, not verbose."""
    assert "a phrase and not a paragraph" in ScreenwriterAgent.SYSTEM_PROMPT


def test_the_schema_asks_for_it_where_the_field_is_filled_in():
    """The paragraph is far from the JSON; the field description is what the
    model is reading at the moment it writes the value."""
    assert '"wardrobe": "what they wear"' not in ScreenwriterAgent.SYSTEM_PROMPT
    for asked in ("fastening", "pockets", "material", "markings"):
        assert asked in ScreenwriterAgent.SYSTEM_PROMPT


# ── and what the frame forbids ──────────────────────────────────────────────


def _clause(wardrobe="a yellow hooded rain slicker, black gloves"):
    char = CharacterInScene(
        idx=0, name="Yara", static_features="a woman in her early thirties",
        wardrobe=wardrobe,
    )
    return build_character_identity_clause([char], matched_char=char)


@pytest.mark.parametrize("item", ["backpack", "bag", "strap", "harness"])
def test_nothing_is_carried_that_was_not_named(item):
    """A pack changes the SILHOUETTE, which is what a costume reads as at any
    distance the face does not. "Wear NOTHING not named above" already
    forbade it; the enumeration is what the model attends to, and nothing in
    it was a bag."""
    assert item in _clause()


def test_the_headwear_the_list_was_written_for_is_still_in_it():
    for item in ("hat", "helmet", "hood", "goggles", "scarf"):
        assert item in _clause()


def test_a_named_bag_is_still_allowed():
    """Same escape the named hat has: the ban is on what the outfit did not
    name, not on bags."""
    clause = _clause("a yellow slicker and a canvas satchel on her hip")
    assert "canvas satchel" in clause
    assert "unless the outfit names one" in clause


# ── the room it costs ───────────────────────────────────────────────────────


SETTLED = (
    "hood up, matte yellow PVC slicker zipped to the throat, two hip flap "
    "pockets, one reflective blue band across the chest only, nothing on her "
    "back; black gloves, dark waterproof trousers"
)
REYES = (
    "bare-headed, dark green oilskin coat buttoned to the collar, two patch "
    "pockets, matte finish, no markings, nothing on his back; knitted "
    "fingerless gloves, steel-toed boots"
)


SINGLE = (
    "Yara advances down the container corridor with her torch raised, the beam "
    "splitting the rain and picking out the ribbed steel walls on either side of "
    "her as the sodium lamps recede into the fog behind her"
)
TWO_SHOT = (
    "Yara crouches at the container's locking bar with her torch raised as Reyes "
    "watches from the gangway behind her, rain sheeting through the sodium glare "
    "and the row of stacks receding into the fog"
)


def _prompt(*characters, visual_desc=SINGLE):
    shot = StoryboardShot(
        idx=0, shot_type="wide shot", lens="35mm", motion_desc="slow push in",
        expression_desc="wary, jaw set, eyes searching the dark",
        visual_desc=visual_desc,
    )
    return build_frame_prompt(
        "Sci-Fi", shot,
        setting_location=(
            "rain-soaked cargo harbour, stacked shipping containers, dock lamps"
        ),
        setting_time_of_day="night", setting_era="near future",
        has_dialogue=True, lipsync_enabled=True,
        characters=list(characters), matched_char=characters[0],
    )


def _yara(wardrobe=SETTLED):
    return CharacterInScene(
        idx=0, name="Yara",
        static_features=(
            "a woman in her early thirties, oval face, long dark hair worn loose "
            "under the hood, olive skin, dark brown eyes, full brows, a small mole "
            "on the right cheekbone, a narrow nose and a faint scar through one brow"
        ),
        wardrobe=wardrobe,
    )


def test_a_settled_garment_still_reaches_the_frame():
    """A wardrobe nobody can read is worth nothing: _describe_characters drops
    wardrobe FIRST when it compacts, so a longer one that gets dropped is
    strictly worse than the short one that drifted."""
    prompt = _prompt(_yara())
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS
    assert "matte yellow PVC slicker zipped to the throat" in prompt


def test_it_does_not_cost_the_rules_the_last_two_fixes_bought():
    prompt = _prompt(_yara())
    assert "The cast is closed" in prompt
    assert "mouth is fully visible" in prompt
    assert "eyes stay inside the scene" in prompt


def test_two_settled_wardrobes_still_fit():
    """The crowded case, and the one that decides whether this is affordable
    at all: a two-shot, so both are described (a single names only one --
    see test_the_frame_describes_who_is_in_it), both dressed head down."""
    reyes = CharacterInScene(
        idx=1, name="Reyes",
        static_features=(
            "a man in his fifties, broad build, weathered brown skin, "
            "close-cropped greying beard, heavy brow, tired brown eyes"
        ),
        wardrobe=REYES,
    )
    prompt = _prompt(_yara(), reyes, visual_desc=TWO_SHOT)
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS
    assert "matte yellow PVC" in prompt
    assert "dark green oilskin" in prompt
    assert "The cast is closed" in prompt
