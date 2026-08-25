"""A shot description that runs long is paid for by the rules around it.

`visual_desc` is priority REQUIRED in the frame prompt -- it is the shot, so
it can never be dropped -- and the storyboard artist was never told what it
costs. Job b6722d22-78c wrote 700-800 characters a shot, and its log shows
the bill, on every one of six frames:

    dropping 262 chars ... (Shot on 35mm film, natural filmic grain ...)
    dropping 332 chars ... (Lighting continuity (identical in every shot ...)
    dropping 182 chars ... (The face is lit and readable — not a silhouette ...)

That third one carries the eyeline: "the eyes stay inside the scene, on the
other character or on the object in their hands — never on the lens." It went
from ALL SIX frames, and twenty-two of the delivered thirty seconds are one
composition -- the character centred, symmetrical, and looking down the barrel
of the lens, held like a passport photograph. Two frames also lost the closed
cast, and one lost the acted expression it was built around.

Measured on this module's own clauses, for a one-hander with a settled
wardrobe: at 330 characters only the film-look note drops, at 400 the lighting
lock goes with it, and at 700 the eyeline and the closed cast follow.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_CHARS,
    MAX_VISUAL_DESC_CHARS,
    build_frame_prompt,
    fit_visual_desc,
)

SHORT = "Mara Vosk crouches at the container seal, torch raised into the rain."
SENTENCES = (
    "Mara Vosk crouches at the container locking bar with her torch raised. "
    "The beam splits the rain and rakes the wet corrugated steel, throwing her "
    "shadow twenty feet down the row. Behind her the sodium lamps recede into "
    "fog, puddles throwing the light back up at the stacks, and the far end of "
    "the row is lost in weather entirely."
)
#: What the delivered job actually wrote, in length.
DELIVERED = SENTENCES + " " + SENTENCES[:420]


# ── the trim ────────────────────────────────────────────────────────────────


def test_a_description_that_fits_is_untouched():
    """The overwhelming majority, and the path that must not move."""
    assert fit_visual_desc(SHORT) == SHORT
    assert fit_visual_desc("") == ""


@pytest.mark.parametrize("desc", [SENTENCES, DELIVERED, "word " * 400])
def test_a_description_that_does_not_fit_is_cut_to_the_budget(desc):
    trimmed = fit_visual_desc(desc)
    assert len(trimmed) <= MAX_VISUAL_DESC_CHARS
    assert trimmed, "a shot with no description is not a shot"


def test_it_never_ends_mid_word():
    for desc in (SENTENCES, DELIVERED, "word " * 400):
        assert desc.startswith(fit_visual_desc(desc).split(",")[0][:20])
        assert not fit_visual_desc(desc).endswith(" ")


def test_it_keeps_what_it_can_rather_than_the_last_full_stop():
    """The last sentence break can be halfway up the description; losing a
    whole sentence to save eight characters trades a long shot for half one."""
    kept = fit_visual_desc(SENTENCES)
    assert len(kept) > MAX_VISUAL_DESC_CHARS * 3 // 4


def test_the_subject_survives_the_cut():
    """Whatever else goes, the frame still has to know who is in it."""
    assert "Mara Vosk" in fit_visual_desc(DELIVERED)


def test_the_shot_itself_is_not_narrowed():
    """The untrimmed description is what the character matcher and the shot
    classifier read; narrowing what THEY see would be a different bug."""
    shot = StoryboardShot(idx=0, visual_desc=DELIVERED, motion_desc="push in")
    build_frame_prompt("Sci-Fi", shot, setting_location="a harbour")
    assert shot.visual_desc == DELIVERED


# ── what it buys back ───────────────────────────────────────────────────────


def _prompt(desc):
    mara = CharacterInScene(
        idx=0, name="Mara Vosk",
        static_features=(
            "a woman in her forties, narrow face, sharp cheekbones, short dark "
            "hair under the hood, pale skin, deep-set green eyes, a thin scar "
            "along the jaw"
        ),
        wardrobe=(
            "hood up, a glossy yellow PVC storm slicker zipped to the throat, a "
            "wide blue reflective band across the chest and one on each sleeve, a "
            "rectangular patch on the left breast, nothing on her back; black "
            "gloves, dark waterproof trousers"
        ),
    )
    shot = StoryboardShot(
        idx=0, visual_desc=desc, motion_desc="push in",
        shot_type="medium shot", lens="35mm",
        expression_desc="eyes stretching wide with dawning horror, jaw slack",
    )
    return build_frame_prompt(
        "Sci-Fi", shot,
        setting_location=(
            "rain-soaked cargo harbour, rows of stacked shipping containers, dock lamps"
        ),
        setting_time_of_day="night", setting_era="near future",
        has_dialogue=True, lipsync_enabled=True,
        characters=[mara], matched_char=mara,
    )


def test_the_eyeline_survives_the_description_that_cost_it():
    prompt = _prompt(DELIVERED)
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS
    assert "never on the lens" in prompt, "the film is a passport photograph again"


@pytest.mark.parametrize("desc", [SHORT, SENTENCES, DELIVERED, "word " * 400])
def test_no_description_however_long_can_cost_the_rules(desc):
    """The point of a cap rather than an instruction: it holds whatever the
    storyboard artist writes."""
    prompt = _prompt(desc)
    assert "never on the lens" in prompt
    assert "The cast is closed" in prompt
    assert "Facial expression and body language" in prompt


# ── and the instruction, so it rarely comes to that ─────────────────────────


def test_the_storyboard_artist_is_told_what_a_long_description_costs():
    prompt = StoryboardArtist.SYSTEM_PROMPT
    assert "WRITE SHORT" in prompt
    assert "about 45 words" in prompt
    assert "3,000-character budget" in prompt


def test_it_is_told_which_rules_it_is_spending():
    """"Be concise" reads as a style note. Naming what is lost, in the order
    it is lost, is a reason."""
    prompt = StoryboardArtist.SYSTEM_PROMPT
    assert "eyes off the lens" in prompt
    assert "strangers out of the frame" in prompt
