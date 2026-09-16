"""Every frame prompt cleared the validator and none of them was read to the end.

MuAPI rejects a `positivePrompt` outside 2..3000 characters, so that is the
budget this module was fitted to, and `fit_image_prompt` enforced it exactly.
It is the wrong budget. FLUX conditions on T5, which truncates at 512 TOKENS
and does it in silence -- no error, no log line, no failed render. The frame
comes back, bills, and looks fine. It was drawn from part of its prompt.

DELIVERED JOB 01a0a502, the harbour drama: three frames at 2761, 2798 and 2883
characters, every one inside 3000, every one about 710 tokens against a cap of
512. A third of each prompt was discarded before the model saw it, and the same
block fell off all three times -- the closed cast, the setting lock, the
lighting lock. The frames say so: two hard-hatted strangers in the background
of a ONE-HANDER, and a set that moves from a container lane to a quayside to
the inside of the container across three consecutive shots.

THE FIRST ATTEMPT AT THIS FIX REASONED FROM CHARACTER COUNTS and got the
arithmetic wrong in both directions at once. It assumed 3.5 characters per
token; the real figure on this repo's prose is 3.98. So the window it defended
was ~250 characters too tight while the prompts themselves were ~200 tokens too
long, and because the number was a guess it could not honestly drop anything --
it reordered, warned, and shipped. Job 94a0aff7 is what that delivered: the set
holds across all three scenes, and there is still a stranger standing in the
first frame.

So the tokenizer is vendored and the budget is measured (tools/t5_budget). What
follows from having a real number is that clauses can be dropped on it, and the
fixed clauses could be compressed against it with the trade visible: the
identity block alone was 281 of 710 tokens -- 44% of everything the model read,
on a one-hander -- and it is the one clause with a PICTURE also holding it.
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
    MAX_IMAGE_PROMPT_TOKENS,
    build_character_identity_clause,
    build_frame_prompt,
    build_no_unnamed_items_clause,
)
from tools.t5_budget import count_tokens, tokenizer_is_real  # noqa: E402

HARBOUR = "rain-soaked cargo harbour, container stacking yard beside the docks"

#: Job 01a0a502's own cast, as the character library held her.
MARA = dict(
    idx=0,
    name="Mara Voss",
    static_features=(
        "woman in her mid-thirties, angular weathered face, strong wiry build"
    ),
    wardrobe=(
        "hood up on a yellow rain slicker, knee-length, zip-fastened, matte "
        "rubberized material, a reflective blue band across the chest, two flap "
        "pockets at the hips, a handheld radio clipped to her left shoulder "
        "strap, a flashlight gripped in her right hand"
    ),
)


def _mara():
    return CharacterInScene(**MARA)


def _harbour_prompt(has_location_plate=True, **kwargs):
    """Frame one of the delivered job, as it was actually ordered."""
    mara = _mara()
    shot = StoryboardShot(
        idx=0,
        shot_type="wide",
        lens="35mm",
        motion_desc="slow push in",
        expression_desc=(
            "brow tightening from routine focus into unsettled curiosity, lips "
            "parting slightly"
        ),
        visual_desc=(
            "Mara Voss walks a narrow container lane, flashlight raised in her "
            "right hand, rain slicing through the beam. Behind her a container's "
            "seams bleed cold blue-white light, its hum cutting under the rain "
            "against the towering stacked steel walls"
        ),
    )
    return build_frame_prompt(
        "Sci-Fi",
        shot,
        setting_location=HARBOUR,
        setting_time_of_day="night",
        setting_era="near future",
        has_dialogue=True,
        picture_speaks=True,
        characters=[mara],
        matched_char=mara,
        has_location_plate=has_location_plate,
        **kwargs,
    )


# ── the budget is measured, not inferred ────────────────────────────────────


def test_the_tokenizer_is_the_real_one():
    """Everything below is only as good as this. A fallback estimate is a
    supported degradation, not a supported test: a suite that passes on an
    approximation would go green on exactly the deployment where the budget
    has stopped applying."""
    assert tokenizer_is_real(), (
        "sentencepiece or assets/t5_spiece.model is missing; the frame budget "
        "is being estimated and these assertions mean nothing"
    )


def test_the_two_budgets_are_not_the_same_budget():
    """The whole defect in one assertion. 3000 characters is what the provider
    ACCEPTS; 512 tokens is what the model READS, and a prompt can clear the
    first by a wide margin while failing the second by 200 tokens."""
    assert MAX_IMAGE_PROMPT_TOKENS == 512
    assert count_tokens("word " * 900) > MAX_IMAGE_PROMPT_TOKENS


def test_the_delivered_prompt_was_over_and_is_now_under():
    """THE TEST THIS FILE EXISTS FOR.

    Job 01a0a502's frame one, rebuilt from the character library entry and the
    storyboard line it actually carried. It went to flux-kontext-pro-i2i at 710
    tokens.
    """
    prompt = _harbour_prompt()
    used = count_tokens(prompt)
    assert used <= MAX_IMAGE_PROMPT_TOKENS, (
        f"{used} tokens: the tail is truncated silently and the frame is drawn "
        "from part of its instructions"
    )
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS


@pytest.mark.parametrize(
    "clause, what",
    [
        ("Appearance is FIXED", "the face is re-invented every scene"),
        ("wearing hood up on a yellow rain slicker", "the costume drifts"),
        ("The first reference", "the anchor portrait goes unexplained"),
        ("The last reference", "the set photograph goes unexplained"),
        ("The EXACT SAME location", "the set moves between shots"),
        ("Cast is closed", "a stranger can walk into this frame"),
        ("never on the lens", "the cast stares down the barrel"),
        ("Facial expression and body language", "the performance is a photograph"),
    ],
)
def test_every_continuity_lock_is_inside_the_window(clause, what):
    """Not "is it in the prompt" -- it always was, on all three delivered
    frames. Whether the model reads it.

    Each of these is a clause some delivered drama is the argument for, and on
    job 01a0a502 the last four were past the cap on every frame.
    """
    prompt = _harbour_prompt()
    assert clause in prompt, what
    head = prompt[: prompt.index(clause) + len(clause)]
    assert count_tokens(head) <= MAX_IMAGE_PROMPT_TOKENS, (
        f"{clause!r} ends past the {MAX_IMAGE_PROMPT_TOKENS}-token window: "
        f"{what}, and nothing in the render will say so"
    )


def test_what_is_given_up_is_what_the_ladder_gives_up_first():
    """Something has to go -- the clauses above come to more than 512 tokens
    with a full character description in front of them. What goes is rank 5
    and rank 7, which is what the ladder has always said goes first.

    The lighting plan is the one that stings, and it is not unbacked: the plate
    note carries "take its architecture, materials and light from it", so the
    frame is still pointed at a photograph of how this place is lit rather than
    at prose about it.
    """
    prompt = _harbour_prompt()
    assert "Shot on 35mm film" not in prompt, "rank 7 goes first"
    assert "Lighting continuity" not in prompt, "rank 5 follows it"
    assert "architecture, materials and light" in prompt


def test_the_shot_itself_still_opens_the_prompt():
    """An image model weights the opening, and a delivered close-up whose
    prompt began "windowless basement card room" is why this rule exists."""
    prompt = _harbour_prompt()
    assert prompt.startswith("Sci-Fi style. Mara Voss walks a narrow container lane")
    assert prompt.index("Shot type: wide") < prompt.index("Appearance is FIXED")


def test_the_character_description_is_what_pays_for_the_rules():
    """The trade, stated so it cannot be reversed by accident.

    The identity block was 281 of 710 tokens. Compacting the DESCRIPTION is the
    cheap side: the reference portrait is still holding that face, and
    flux-pulid is an identity model outright. The rules have no picture behind
    them -- there is no photograph of "only Mara Voss appears".

    So the wardrobe may be trimmed; the locks may not disappear.
    """
    prompt = _harbour_prompt()
    for lock in ("Appearance is FIXED", "Costume is LOCKED", "Cast is closed"):
        assert lock in prompt
    # ...and enough of the outfit survives to be a garment rather than a colour.
    assert "yellow rain slicker" in prompt


# ── the costume lock, no longer arguing with the costume ────────────────────


def test_the_ban_does_not_forbid_the_outfit_it_just_issued():
    """Mara's slicker is worn hood-up with a radio on a shoulder strap. The
    prompt used to say "no ... hood ... strap or harness" underneath it."""
    clause = build_character_identity_clause([_mara()], _mara())
    ban = clause.split("Wear NOTHING not named above")[1]
    assert "hood" not in ban
    assert "strap" not in ban


def test_and_still_forbids_everything_she_is_not_wearing():
    """A filter, not an off switch. The list exists because a harbour reads to
    an image model as "put a hard hat on him" -- and job 01a0a502's third frame
    has two of them standing in the background."""
    clause = build_character_identity_clause([_mara()], _mara())
    ban = clause.split("Wear NOTHING not named above")[1]
    for item in ("hard hat", "helmet", "goggles", "backpack", "mask"):
        assert item in ban


def test_a_synonym_counts_as_naming_it():
    """The outfit says "satchel"; the list says "bag". Both are in the
    conditioning and the model is not reading the exemption between them."""
    ban = build_no_unnamed_items_clause("a yellow slicker and a canvas satchel")
    assert "bag" not in ban.split("Wear NOTHING not named above")[1]
    assert "backpack" in ban


def test_an_outfit_that_names_everything_still_forbids_additions():
    """The categorical sentence is the half that was always true. It survives
    an outfit that empties the enumeration."""
    worn = (
        "hat cap beanie helmet hood mask goggles glasses headset scarf badge "
        "backpack bag strap harness hard hat"
    )
    ban = build_no_unnamed_items_clause(worn)
    assert "Wear NOTHING not named above" in ban
    assert "Markings are shapes, not words" in ban


def test_the_markings_backstop_survives_either_shape():
    """It rides on this clause rather than having a sentence of its own, so a
    filter that empties the list must not take it with it."""
    for worn in ("", "a plain coverall", "hat cap hood strap"):
        assert "Markings are shapes" in build_no_unnamed_items_clause(worn)


# ── the second reference image, named ───────────────────────────────────────


def test_the_plate_is_not_described_when_it_was_not_sent():
    """A sentence about "the last reference" in a payload that has one image
    points the model at a photograph it never received -- the same failure as
    the singular note, pointed the other way."""
    prompt = _harbour_prompt(has_location_plate=False)
    assert "The last reference" not in prompt
    assert "The first reference is Mara Voss" in prompt


def test_the_plate_note_does_not_outrank_the_promise_it_carries():
    """They are one thing said twice -- a promise and its evidence -- so a
    frame must not keep either alone."""
    prompt = _harbour_prompt(has_location_plate=True)
    assert ("The EXACT SAME location" in prompt) == ("The last reference" in prompt)


# ── a crowded frame still fits ──────────────────────────────────────────────


def test_a_two_hander_fits_the_window_too():
    """The one-hander above is the EASY case. Two described characters is what
    pushed the identity clause to 1147 characters on a delivered job, and it is
    the shape the budget has to survive."""
    mara = _mara()
    dockhand = CharacterInScene(
        idx=1,
        name="Teo Ranan",
        static_features=(
            "man in his fifties, heavy-set, close-cropped grey hair, a broken "
            "nose and deep-set brown eyes"
        ),
        wardrobe=(
            "an orange hi-vis jacket over navy overalls, steel-capped boots and "
            "fingerless gloves"
        ),
    )
    shot = StoryboardShot(
        idx=0,
        shot_type="medium two-shot",
        lens="50mm",
        motion_desc="static",
        expression_desc="wary, weighing each other up",
        visual_desc=(
            "Mara Voss and Teo Ranan face each other across the open container "
            "door, rain running off both their hoods as the blue-white glow "
            "throws their shadows back down the lane"
        ),
    )
    prompt = build_frame_prompt(
        "Sci-Fi",
        shot,
        setting_location=HARBOUR,
        setting_time_of_day="night",
        setting_era="near future",
        has_dialogue=True,
        lipsync_enabled=True,
        characters=[mara, dockhand],
        matched_char=mara,
        has_location_plate=True,
    )
    used = count_tokens(prompt)
    assert used <= MAX_IMAGE_PROMPT_TOKENS, f"{used} tokens on a two-hander"
    # Both faces still locked, which is the clause a two-hander exists to test.
    assert "Mara Voss" in prompt and "Teo Ranan" in prompt
    assert "Cast is closed" in prompt
