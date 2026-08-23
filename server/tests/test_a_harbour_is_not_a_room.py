"""The lighting plan was written for a room, and the drama is on a dock.

Every plan in interfaces/lighting names where the key light comes from, and
every one of them answered as if the camera were indoors -- "through a
window", "from warm practical lamps inside the room", "raking across the
room". The module derives the plan from the locked HOUR alone, and an hour
cannot tell you whether there is a wall.

Two delivered dramas set in a rain-soaked cargo harbour therefore carried, on
every frame, 325 characters instructing the model to light an exterior from
practicals inside a room and moonlight through windows it does not have --
direction that is wrong, that argues with the setting clause in the same
prompt, and that was sitting ABOVE the closed-cast rule in the budget while
the budget was over.

The second delivered job dropped the cast rule to keep it:

    dropping 262 chars ... (Shot on 35mm film, natural filmic grain ...)
    dropping 248 chars ... (The cast is closed: only Yara appears in this ...)

and a man in a green jacket is standing at the end of the container row in
shot two, in a one-hander.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.lighting import (  # noqa: E402
    is_interior,
    resolve_lighting,
)
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_CHARS,
    build_frame_prompt,
)

HARBOUR = "rain-soaked cargo harbour, stacked shipping containers, dock lamps"


# ── where the drama is standing ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "location",
    [HARBOUR, "a rooftop car park", "the towpath beside the canal", "EXT. ALLEY"],
)
def test_a_place_with_no_walls_is_not_interior(location):
    assert is_interior(location) is False


@pytest.mark.parametrize(
    "location",
    ["a cramped tenement kitchen", "the hospital ward at 3am", "INT. LOBBY"],
)
def test_a_room_is(location):
    assert is_interior(location) is True


def test_the_slug_line_wins_over_the_nouns():
    """Screenwriting answers this in the first three characters, and it is
    answering about the CAMERA -- a scene shot from inside a car looking at a
    dock is INT., whatever the nouns say."""
    assert is_interior("INT. PORTAKABIN overlooking the dock and the harbour") is True
    assert is_interior("EXT. WAREHOUSE LOADING BAY") is False


def test_a_location_that_says_both_says_neither():
    """"The yard behind the workshop" is a guess either way, and a wrong
    guess puts a window in a harbour. Unstated costs a vaguer sentence."""
    assert is_interior("the yard behind the workshop") is None
    assert is_interior("") is None
    assert is_interior("somewhere") is None


# ── what the plan then says ─────────────────────────────────────────────────


def test_out_of_a_room_the_night_key_is_not_a_window():
    clause = resolve_lighting("night").as_clause(interior=False)
    assert "window" not in clause
    assert "inside the room" not in clause
    assert "street, dock" in clause


def test_in_a_room_the_night_key_is_exactly_what_it_always_was():
    """The interior wording is the one every previously delivered interior
    drama was lit by; it does not move."""
    clause = resolve_lighting("night").as_clause(interior=True)
    assert "warm practical lamps inside the room" in clause
    assert "moonlight through the windows" in clause


def test_an_unstated_place_asserts_no_window():
    """None reads as "not a room": a sentence naming no window is right in
    both places, one naming a window is wrong in half of them."""
    assert "window" not in resolve_lighting("night").as_clause(interior=None)
    assert "window" not in resolve_lighting("night").as_clause()


def test_the_hour_still_decides_everything_else():
    """Only the KEY's origin moves. Quality and temperature are the hour's."""
    plan = resolve_lighting("night")
    for clause in (plan.as_clause(True), plan.as_clause(False)):
        assert "low key, strong falloff" in clause
        assert "warm tungsten key against cool blue moonlight" in clause
        assert "Do not change" in clause


def test_a_daylight_hour_reads_the_same_in_both_places():
    """The sun is the key indoors and out; only the hours whose key is a lamp
    or a window needed a second sentence."""
    plan = resolve_lighting("midday")
    assert plan.as_clause(True) == plan.as_clause(False)


# ── and what that buys in the frame prompt ──────────────────────────────────


def _harbour_prompt():
    yara = CharacterInScene(
        idx=0,
        name="Yara",
        static_features=(
            "a woman in her early thirties, oval face, long dark hair worn loose "
            "under the hood, olive skin, dark brown eyes, full brows, a small mole "
            "on the right cheekbone, a narrow nose and a faint scar through one brow"
        ),
        wardrobe=(
            "a yellow hooded rain slicker with a reflective blue band across the "
            "chest, black gloves, dark waterproof trousers, steel-capped dock boots"
        ),
    )
    shot = StoryboardShot(
        idx=0,
        shot_type="wide shot",
        lens="35mm",
        motion_desc="slow push in",
        expression_desc="wary, jaw set, eyes searching the dark between the stacks",
        visual_desc=(
            "Yara advances down the container corridor with her torch raised, the "
            "beam splitting the rain and picking out the ribbed steel walls on "
            "either side of her as the sodium lamps recede into the fog behind "
            "her, puddles throwing the light back up at the stacks and the far end "
            "of the row lost in weather"
        ),
    )
    return build_frame_prompt(
        "Sci-Fi",
        shot,
        setting_location=HARBOUR,
        setting_time_of_day="night",
        setting_era="near future",
        has_dialogue=True,
        lipsync_enabled=True,
        characters=[yara],
        matched_char=yara,
    )


def test_the_harbour_frame_is_not_lit_through_a_window():
    prompt = _harbour_prompt()
    assert "moonlight through the windows" not in prompt
    assert "lamps inside the room" not in prompt


def test_the_closed_cast_survives_the_frame_that_lost_it():
    """The delivered job's own shape: a one-hander, a full description, a
    real storyboard sentence, and a prompt over budget."""
    prompt = _harbour_prompt()
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS
    assert "The cast is closed" in prompt, "a stranger can walk into this frame"
    assert "mouth is fully visible" in prompt


def test_the_lighting_lock_goes_before_the_closed_cast():
    """Ranked deliberately: a shot lit slightly differently reads as a
    lighting change, a person nobody wrote reads as a different film."""
    from pipelines.script2video import fit_image_prompt

    squeezed = fit_image_prompt(
        [
            (0, "x" * 2900),
            (5, "LIGHTING " * 20),
            (3, "The cast is closed: only Yara. "),
        ]
    )
    assert "The cast is closed" in squeezed
    assert "LIGHTING" not in squeezed
