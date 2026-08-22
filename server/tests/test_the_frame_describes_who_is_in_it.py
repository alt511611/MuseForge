"""A frame prompt describes the people in the frame, not the whole cast.

The identity clause restates every character's locked appearance so the ones
the reference image cannot bind still hold their face across the film. It was
built from the SCENE's cast, and a micro-drama's scenes are shot as singles --
so a two-hander spent ~230 characters of a 3,000-character provider budget
describing, in detail, somebody who is not in the picture. On every frame.

That budget is not free. fit_image_prompt drops clauses worst-rank-first to
fit, and the delivered logs show what it dropped from every dialogue frame of
a real job:

    dropping 262 chars ... (Shot on 35mm film, natural filmic grain ...)
    dropping 299 chars ... (Screen direction (LOCKED for the entire story ...)
    dropping 186 chars ... (The speaking character's mouth is fully visible ...)
    dropping 260 chars ... (The cast is closed: Mara Voss, Tomas Reyes ...)

The 180-degree rule, the closed cast, and the mouth-visibility line the
lip-sync pass depends on -- all pushed out by a description of the man who is
not in the shot.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_CHARS,
    build_frame_prompt,
)


def _cast():
    return [
        CharacterInScene(
            idx=0,
            name="Mara Voss",
            static_features=(
                "a woman in her late thirties, sharp angular face, dark "
                "shoulder-length hair pulled back, pale skin with a faded scar "
                "across the left eyebrow, deep-set grey eyes, thin lips"
            ),
            wardrobe=(
                "a yellow high-visibility rain jacket over a navy work fleece, "
                "heavy waterproof trousers, black gloves"
            ),
        ),
        CharacterInScene(
            idx=1,
            name="Tomas Reyes",
            static_features=(
                "a man in his fifties, broad build, weathered brown skin, "
                "close-cropped greying beard, heavy brow, tired brown eyes"
            ),
            wardrobe="a dark green oilskin coat, a knitted cap, steel-toed boots",
        ),
    ]


def _prompt(visual_desc, characters, matched_index=0, **kwargs):
    shot = StoryboardShot(
        idx=0,
        visual_desc=visual_desc,
        motion_desc="slow push in",
        shot_type="medium shot",
        lens="35mm",
        expression_desc="jaw set hard, eyes narrowed against the rain",
    )
    return build_frame_prompt(
        "Sci-Fi",
        shot,
        setting_location=(
            "rain-soaked cargo harbour, stacked shipping containers under "
            "sodium floodlights"
        ),
        setting_time_of_day="night",
        setting_era="near future",
        has_dialogue=True,
        lipsync_enabled=True,
        characters=characters,
        matched_char=characters[matched_index] if characters else None,
        **kwargs,
    )


SINGLE = "Mara Voss crouches beside the container's seal, torchlight raking the wet steel"
TWO_SHOT = (
    "Mara Voss crouches beside the container's seal as Tomas Reyes watches "
    "from the gangway behind her"
)


def test_a_single_does_not_describe_the_character_who_is_not_in_it():
    prompt = _prompt(SINGLE, _cast())
    assert "Mara Voss (a woman in her late thirties" in prompt
    assert "Tomas Reyes (a man in his fifties" not in prompt


def test_a_two_shot_still_describes_both():
    prompt = _prompt(TWO_SHOT, _cast())
    assert "Mara Voss (a woman in her late thirties" in prompt
    assert "Tomas Reyes (a man in his fifties" in prompt


def test_the_room_that_frees_keeps_the_direction_the_scene_needs():
    """What the absent character's description was costing, spent on the
    clauses the delivered job lost instead."""
    prompt = _prompt(SINGLE, _cast())
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS
    assert "180-degree rule" in prompt, "screen direction was dropped again"
    assert "The cast is closed" in prompt
    assert "mouth is fully visible" in prompt, (
        "the clause the lip-sync pass depends on was dropped from a dialogue "
        "frame"
    )


def test_the_closed_cast_still_names_everyone():
    """Narrowing the DESCRIPTION must not narrow the guest list: the clause
    that keeps strangers out of the frame is about the whole story."""
    prompt = _prompt(SINGLE, _cast())
    assert "Mara Voss, Tomas Reyes appear in this story" in prompt


def test_a_shot_that_names_nobody_still_describes_the_whole_cast():
    """An insert or a plate names no one, and the pipeline has already had to
    guess its own anchor there. Guessing again -- in the direction of
    describing fewer of the people who might be on screen -- is how a
    character comes back as a stranger."""
    prompt = _prompt("A gloved hand presses against the container seal", _cast())
    assert "Mara Voss (a woman in her late thirties" in prompt
    assert "Tomas Reyes (a man in his fifties" in prompt


def test_a_name_that_is_only_heard_is_not_a_person_in_the_frame():
    """Same rule the reference portrait is chosen by: a voice on the radio is
    not somebody to describe the face of."""
    prompt = _prompt(
        "Mara Voss works the seal as Tomas Reyes' voice crackles over the radio",
        _cast(),
    )
    assert "Mara Voss (a woman in her late thirties" in prompt
    assert "Tomas Reyes (a man in his fifties" not in prompt


def test_a_shot_naming_only_a_never_seen_character_keeps_the_lock():
    """is_visible=False is the cast-level "not in this film's pictures". A
    shot that names only such a character must not narrow the clause down to
    nobody -- a frame with no appearance lock renders a stranger, which is the
    failure the clause exists for."""
    cast = _cast()
    cast[1] = CharacterInScene(
        idx=1,
        name="Tomas Reyes",
        static_features="a man in his fifties, broad build",
        wardrobe="a dark green oilskin coat",
        is_visible=False,
    )
    prompt = _prompt("Tomas Reyes barks an order", cast, matched_index=0)
    assert "Appearance is FIXED" in prompt
    assert "Mara Voss (a woman in her late thirties" in prompt
