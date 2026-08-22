"""The clause lip sync depends on is not direction, and cannot be dropped.

`build_frame_prompt` ranks its clauses so an over-long prompt loses the least
important one first (fit_image_prompt). The mouth-visibility line -- "their
lips will be animated to the dialogue" -- was ranked alongside the 180-degree
rule as optional direction, and on a ONE-HANDER that made it the first real
casualty: build_screen_direction_clause only fires for exactly two visible
characters, so a solo drama reaches the cap with nothing above the mouth to
sacrifice.

From the delivered job (one dock worker on screen, a dispatcher on the radio),
four of six frames:

    dropping 262 chars ... (Shot on 35mm film, natural filmic grain ...)
    dropping 186 chars ... (The speaking character's mouth is fully visible ...)

Its middle scene then plays a five-second line over a closed mouth: the sync
was requested, billed, returned at 5.21s and composited -- onto a frame with
no mouth presented to camera for it to drive.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_CHARS,
    build_frame_prompt,
    fit_image_prompt,
)

MOUTH = "mouth is fully visible"

LEAD = CharacterInScene(
    idx=0,
    name="Mara Voss",
    static_features=(
        "a woman in her late thirties, sharp angular face, dark shoulder-length "
        "hair pulled back into a short wet crop, pale skin with a faded scar "
        "across the left eyebrow, deep-set grey eyes, thin lips, high cheekbones"
    ),
    wardrobe=(
        "a yellow high-visibility rain jacket over a navy work fleece, heavy "
        "waterproof trousers, black gloves, a laminated dock pass at the chest"
    ),
)
#: Heard on the radio, never in the picture -- so the frame has one visible
#: character and no screen-direction axis to spend budget on.
RADIO = CharacterInScene(
    idx=1,
    name="Control",
    static_features="a dispatcher on the harbour radio net",
    wardrobe="",
    is_visible=False,
)

#: Long enough to put the prompt over the provider's cap on its own, which is
#: what a real storyboard description does once a scene has anything in it.
LONG_DESC = (
    "Mara Voss crouches at the container's locking bar with the handset raised "
    "to her mouth, her torch beam raking across the wet corrugated steel and "
    "throwing her shadow twenty feet down the row of stacked boxes; rain sheets "
    "through the sodium glare behind her and pools between the rails, the "
    "painted serial number half scoured off the plate above the door, the seal "
    "hanging cut and swinging just inside the light, and a slick of something "
    "dark running out from under the door sill toward the toes of her boots "
    "while the yard behind her stands empty in every direction"
)


def _prompt(cast, desc=LONG_DESC, lipsync_enabled=True):
    shot = StoryboardShot(
        idx=0,
        visual_desc=desc,
        motion_desc="slow push in",
        shot_type="medium shot",
        lens="35mm",
        expression_desc="jaw set hard, eyes narrowed against the rain",
    )
    return build_frame_prompt(
        "Sci-Fi",
        shot,
        setting_location=(
            "rain-soaked cargo harbour, rows of shipping containers under "
            "sodium floodlights"
        ),
        setting_time_of_day="night",
        setting_era="near future",
        has_dialogue=True,
        lipsync_enabled=lipsync_enabled,
        characters=cast,
        matched_char=LEAD,
    )


def test_a_one_hander_keeps_the_mouth_when_the_prompt_runs_long():
    """The delivered job's own shape: one face on screen, prompt over budget."""
    prompt = _prompt([LEAD, RADIO])
    assert len(prompt) > MAX_IMAGE_PROMPT_CHARS - 400, (
        "this frame no longer squeezes the budget, so it no longer tests it"
    )
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS
    assert MOUTH in prompt, "the clause the sync pass depends on was dropped"


def test_the_mouth_outranks_every_clause_that_is_only_direction():
    """Whatever else has to go, this stays -- and something did have to go."""
    prompt = _prompt([LEAD, RADIO])
    assert "Shot on 35mm film" not in prompt, "nothing was dropped; no squeeze"
    assert MOUTH in prompt


def test_a_runaway_description_cannot_truncate_the_mouth_off_the_end():
    """The last resort trims the longest clause, not the assembled tail --
    where the shortest required clauses happen to sit."""
    prompt = _prompt([LEAD, RADIO], desc=LONG_DESC + " " + ("wet steel " * 400))
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS
    assert MOUTH in prompt
    assert "Shot type: medium shot" in prompt


def test_the_no_sync_dodge_is_still_optional():
    """Without lip sync the clause asks for the OPPOSITE -- hide the mouth --
    and that one is worth exactly what it costs. It may still be dropped."""
    prompt = _prompt([LEAD, RADIO], lipsync_enabled=False)
    assert MOUTH not in prompt
    over_budget = fit_image_prompt(
        [(0, "x" * (MAX_IMAGE_PROMPT_CHARS - 10)), (6, "naturally obscured ")]
    )
    assert "naturally obscured" not in over_budget


@pytest.mark.parametrize("cast", ([LEAD], [LEAD, RADIO]))
def test_the_frame_still_fits_whatever_the_cast(cast):
    assert len(_prompt(cast)) <= MAX_IMAGE_PROMPT_CHARS
