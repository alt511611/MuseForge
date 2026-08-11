"""MuAPI rejects a prompt outside 2..3000 chars with a 400 — at generation
time, not on submit, so the job pays for the round trip and then dies.

This only started biting once the screenwriter worked: a real script names
several characters with described faces AND wardrobe, and every one of them
is restated in the identity clause of every single frame. The deterministic
template's one undescribed "Alex" never got near the limit.
"""

import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_CHARS,
    build_frame_prompt,
    fit_image_prompt,
)
from tools.muapi_image_generator import (  # noqa: E402
    MAX_PROMPT_CHARS,
    MuAPIImageGenerator,
    clamp_prompt,
)

RICH_FEATURES = (
    "a woman in her early thirties, sharp cheekbones, dark hair pulled back "
    "in a wet knot, tired grey eyes, lean build, a faded scar across her left "
    "eyebrow"
)
RICH_WARDROBE = (
    "a soaked navy dock parka over a charcoal crew-neck sweater, steel-toed boots"
)


def _character(i, wardrobe=RICH_WARDROBE):
    return CharacterInScene(
        idx=i, name=f"Character{i}", static_features=RICH_FEATURES,
        dynamic_features="", is_visible=True, wardrobe=wardrobe,
    )


def _shot(visual_desc="They crouch at the container seal under the sodium lamp."):
    return StoryboardShot(
        idx=0, visual_desc=visual_desc, motion_desc="slow push in",
        expression_desc="jaw set, eyes narrowed against the rain",
        shot_type="medium", lens="35mm",
    )


def _frame_prompt(characters, shot=None):
    return build_frame_prompt(
        style="Sci-Fi",
        shot=shot or _shot(),
        setting_location="a rain-soaked cargo harbour, container stacks and gantry cranes",
        setting_time_of_day="night",
        setting_era="present day",
        has_dialogue=True,
        lipsync_enabled=True,
        characters=characters,
        matched_char=characters[0] if characters else None,
    )


# --- the prompt fits, however many characters the script names ----------


@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 8, 12])
def test_frame_prompt_stays_within_the_provider_limit(count):
    prompt = _frame_prompt([_character(i) for i in range(count)])
    assert 2 <= len(prompt) <= MAX_IMAGE_PROMPT_CHARS, len(prompt)


@pytest.mark.parametrize("count", [1, 4, 8, 12])
def test_character_lock_survives_trimming(count):
    """Trimming must never cost the character lock — a frame that renders a
    stranger is worse than one without filmic grain."""
    characters = [_character(i) for i in range(count)]
    prompt = _frame_prompt(characters)

    assert "IDENTICAL to previous scenes" in prompt
    for c in characters:
        assert c.name in prompt, f"{c.name} dropped from the identity clause"


def test_the_shot_itself_always_survives():
    visual = "She cuts the seal as the skyline behind her goes black"
    prompt = _frame_prompt([_character(i) for i in range(10)], _shot(visual))
    assert visual in prompt
    assert "Shot type: medium" in prompt


def test_polish_is_dropped_before_continuity():
    """Drop order matters: losing grain is survivable, losing the setting
    means the room changes between scenes.

    Forced over budget with a long visual_desc rather than a crowded cast —
    the identity clause compacts itself, so characters alone no longer
    overflow.
    """
    long_shot = _shot("She cuts the seal " + "under the sodium lamp " * 60)
    crowded = _frame_prompt([_character(i) for i in range(4)], long_shot)

    assert "Setting:" in crowded, "continuity must outlive polish"
    assert "Shot on 35mm film" not in crowded, "quality suffix should go first"


# --- fit_image_prompt itself -------------------------------------------


def test_fit_keeps_everything_when_it_fits():
    out = fit_image_prompt([(0, "core. "), (1, "a. "), (2, "b. ")], limit=100)
    assert out == "core. a. b. "


def test_fit_drops_the_worst_priority_first_not_the_last_segment():
    """Reading order and drop order are separate concerns: the opening of an
    image prompt carries the most weight, so it stays put while a trailing
    lower-priority clause goes."""
    out = fit_image_prompt(
        [(0, "core. "), (4, "polish. "), (1, "keep. ")], limit=14
    )
    assert "core. " in out and "keep. " in out
    assert "polish. " not in out


def test_fit_preserves_reading_order():
    out = fit_image_prompt([(0, "first. "), (4, "second. "), (0, "third. ")])
    assert out.index("first.") < out.index("second.") < out.index("third.")


def test_fit_truncates_on_a_word_boundary_as_a_last_resort():
    out = fit_image_prompt([(0, "word " * 100)], limit=50)
    assert len(out) <= 50
    assert not out.endswith("wor"), "must not cut mid-word"


# --- the provider-boundary backstop ------------------------------------


def test_clamp_truncates_an_overlong_prompt():
    assert len(clamp_prompt("word " * 2000)) <= MAX_PROMPT_CHARS


def test_clamp_substitutes_for_an_empty_prompt(caplog):
    """An empty prompt is an upstream bug, but failing the render on it helps
    nobody — MuAPI rejects "" just as hard as 3001 chars."""
    with caplog.at_level(logging.ERROR):
        assert clamp_prompt("   ") == "a cinematic film still"
    assert "empty or too short" in caplog.text


def test_clamp_leaves_a_normal_prompt_alone():
    prompt = "Sci-Fi style. She cuts the seal."
    assert clamp_prompt(prompt) == prompt


@pytest.mark.parametrize("aspect_ratio", ["16:9", "9:16"])
def test_payloads_never_carry_an_illegal_prompt(aspect_ratio):
    """Every payload builder must clamp — a caller that skips
    fit_image_prompt still must not put a job in front of a 400."""
    gen = MuAPIImageGenerator(api_key="test")

    text_payload = gen._text_to_image_payload("word " * 2000, aspect_ratio)
    assert len(text_payload["prompt"]) <= MAX_PROMPT_CHARS

    legacy_payload = gen._legacy_size_payload("word " * 2000, aspect_ratio)
    assert len(legacy_payload["prompt"]) <= MAX_PROMPT_CHARS

    empty_payload = gen._text_to_image_payload("", aspect_ratio)
    assert len(empty_payload["prompt"]) >= 2


def test_prompt_still_opens_with_style_and_subject():
    """Regression: an early version of the budget logic emitted every
    optional clause before the core, so prompts began with the face-lighting
    instruction instead of the style and the shot. Image models weight the
    opening — the subject has to lead."""
    prompt = _frame_prompt([_character(0)], _shot("Maya walks the pier"))
    assert prompt.startswith("Sci-Fi style. ")
