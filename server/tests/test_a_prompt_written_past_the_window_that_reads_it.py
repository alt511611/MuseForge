"""Every frame prompt cleared the validator and none of them was read to the end.

MuAPI rejects a `positivePrompt` outside 2..3000 characters, so that is the
budget this module has always been fitted to, and `fit_image_prompt` enforces
it exactly. It is the wrong budget. FLUX conditions on T5, which truncates at
512 TOKENS and does it in silence -- no error, no log line, no failed render.
The frame comes back, bills, and looks fine. It was simply drawn from part of
its prompt.

DELIVERED JOB 01a0a502, the harbour drama, three frames on
flux-kontext-pro-i2i. 2761, 2798 and 2883 characters: every one of them well
inside 3000, and every one of them about 700-800 tokens against a cap of 512.
The reading order was fixed and editorial -- the shot, then the people, then
"the room, its light and the film's finish" -- so the same block fell past the
cap all three times:

    The cast is closed: only Mara Voss appears in this story.
    Setting: rain-soaked cargo harbour ... The EXACT SAME physical location
    Lighting continuity, identical in every shot ...

and the delivered frames say so. Two hard-hatted strangers stand in the third
frame's background, in a one-hander whose cast clause forbids exactly that.
The set moves from a narrow container lane to an open quayside to the inside
of the container across three consecutive shots. Every one of those clauses
was in every prompt, kept by the ladder, paid for in the payload, and never
read.

The ladder already knew what mattered: the cast is rank 3, the setting rank 1,
the lighting rank 5, against rank 6 for the axis and 7 for the film-look note.
The READING order put all three behind both. Two orders, disagreeing, and the
one that decided what the model saw was the one with no argument behind it.

Two more things fell out of reading the same prompt. The costume lock forbids
sixteen items and exempts "unless the outfit names one" -- and this outfit is
"hood up on a yellow rain slicker ... a radio clipped to her left shoulder
STRAP", so two of its three garments were on the forbidden list, in the same
prompt, a few hundred characters apart. And the payload carried TWO reference
images, the character sheet and the location plate, while the prompt said "The
reference image is Mara Voss" in the singular and then "Take NOTHING else from
it" -- which, read against a set, is an instruction to ignore the one
photograph of the set.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    IMAGE_PROMPT_TOKEN_WINDOW,
    MAX_IMAGE_PROMPT_CHARS,
    MAX_IMAGE_PROMPT_TOKENS,
    build_character_identity_clause,
    build_frame_prompt,
    build_no_unnamed_items_clause,
)

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


# ── the window, and what is inside it ───────────────────────────────────────


def test_the_token_window_is_derived_from_the_cap_not_chosen():
    """Both numbers are provider facts; the third is arithmetic over them. A
    hand-picked character count here is how the 3000 in MAX_IMAGE_PROMPT_CHARS
    came to be mistaken for the budget that matters."""
    assert MAX_IMAGE_PROMPT_TOKENS == 512
    assert IMAGE_PROMPT_TOKEN_WINDOW < MAX_IMAGE_PROMPT_CHARS, (
        "a token window wider than the character gate would mean the gate is "
        "the binding budget, which is the belief this module shipped on"
    )


@pytest.mark.parametrize(
    "clause, what",
    [
        ("The EXACT SAME physical location", "the set can move between shots"),
        ("The last reference image", "the set photograph goes unexplained"),
    ],
)
def test_the_continuity_locks_are_read(clause, what):
    """THE TEST THIS FILE EXISTS FOR.

    Not "is the clause in the prompt" -- it always was, on all three delivered
    frames. Whether it is in the part of the prompt the model reads.

    On job 01a0a502 the setting lock started at character 2257 of a
    2761-character prompt. It now starts inside the window, which is the
    difference between a set that is promised and a set that is held.
    """
    prompt = _harbour_prompt()
    assert clause in prompt, what
    at = prompt.index(clause)
    assert at < IMAGE_PROMPT_TOKEN_WINDOW, (
        f"{clause!r} starts at character {at}, past the ~{IMAGE_PROMPT_TOKEN_WINDOW}"
        f"-character window: {what}, and nothing in the render will say so"
    )


def test_the_closed_cast_is_ahead_of_everything_it_outranks():
    """THE ONE THIS FIX DOES NOT FINISH, pinned so it cannot quietly regress.

    The acted expression (2) and the closed cast (3) still land outside the
    window on a one-hander with a full character description -- 1934 and 2105
    against ~1790. Priority order moved the cast up from 2147 and that is all
    it could do: the clauses ahead of it are the identity block and its
    reference note, the mouth line, and the setting with its plate, and those
    come to more than the window on their own. Closing the last ~300
    characters means shortening them, which is a separate argument with each
    one and not one to settle from a single delivered job.

    So this is the honest half. What IS guaranteed is the ordering: both now
    read ahead of every clause the ladder says is worth less than them. On job
    01a0a502 the cast read behind all three of them.
    """
    prompt = _harbour_prompt()
    assert "The cast is closed" in prompt, "a stranger can walk into this frame"
    cast_at = prompt.index("The cast is closed")
    # The expression outranks the cast (2 against 3) and reads before it.
    assert prompt.index("Facial expression") < cast_at
    for cheaper in ("Lighting continuity", "Shot on 35mm film"):
        if cheaper in prompt:
            assert cast_at < prompt.index(cheaper), (
                f"{cheaper!r} is being read before the closed cast, which the "
                "ladder ranks below it"
            )


def test_the_shot_itself_still_opens_the_prompt():
    """The half of the old reading order that was right, and is untouched: an
    image model weights the opening, and a delivered close-up whose prompt
    began "windowless basement card room" is why this rule exists."""
    prompt = _harbour_prompt()
    assert prompt.startswith("Sci-Fi style. Mara Voss walks a narrow container lane")
    assert prompt.index("Shot type: wide") < prompt.index("Appearance is FIXED")


def test_the_setting_is_no_longer_what_sits_past_the_window():
    """Priority order means the clauses at risk are the ones the ladder would
    have given up first anyway. The set and the photograph of it are not
    those; on the delivered job they were exactly those."""
    prompt = _harbour_prompt()
    if len(prompt) <= IMAGE_PROMPT_TOKEN_WINDOW:
        pytest.skip("this prompt fits the window whole; nothing is at risk")
    tail = prompt[IMAGE_PROMPT_TOKEN_WINDOW:]
    for lock in ("EXACT SAME physical location", "The last reference image"):
        assert lock not in tail


def test_nothing_is_dropped_for_an_estimate():
    """The window is an ESTIMATE, so it reorders and it warns; it does not
    drop. Dropping the lighting plan and the axis for it was tried and
    reverted: neither one sits ahead of the cast clause, so giving them up
    moves nothing into the window, and both are clauses a delivered job is
    the argument for. What the window earns is reading order, which costs
    nothing and cannot be wrong."""
    prompt = _harbour_prompt()
    assert "never on the lens" in prompt
    assert "Lighting continuity" in prompt



def test_the_drop_order_did_not_move():
    """Reading order changed; PRIORITIES did not. Every rank in the ladder is
    the rank its own note argues for, each one written off a delivered job,
    and reordering the read must not quietly re-rank them."""
    prompt = _harbour_prompt()
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS
    # A crowded one-hander keeps its locks and pays with the bottom rung.
    assert "The cast is closed" in prompt
    assert "mouth is visible and unobscured" in prompt


# ── the costume lock, no longer arguing with the costume ────────────────────


def test_the_ban_does_not_forbid_the_outfit_it_just_issued():
    """Mara's slicker is worn hood-up with a radio on a shoulder strap. The
    prompt used to say "no ... hood ... strap or harness" underneath it."""
    clause = build_character_identity_clause([_mara()], _mara())
    assert "hood up on a yellow rain slicker" in clause
    ban = clause.split("Wear NOTHING not named above")[1]
    assert "hood" not in ban
    assert "strap" not in ban


def test_and_still_forbids_everything_she_is_not_wearing():
    """A filter, not an off switch. The list exists because a harbour reads to
    an image model as "put a hard hat on him", and job 01a0a502's third frame
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
    worn = " ".join(
        "hat cap beanie helmet hood mask goggles glasses headset scarf badge "
        "backpack bag strap harness".split()
    )
    ban = build_no_unnamed_items_clause(worn + " hard hat")
    assert "Wear NOTHING not named above" in ban
    assert "Markings are shapes, not words" in ban


def test_the_markings_backstop_survives_either_shape():
    """It rides on this clause rather than having a sentence of its own, so a
    filter that empties the list must not take it with it."""
    for worn in ("", "a plain coverall", "hat cap hood strap"):
        assert "Markings are shapes" in build_no_unnamed_items_clause(worn)


# ── the second reference image, named ───────────────────────────────────────


def test_the_plate_is_introduced_when_it_is_sent():
    prompt = _harbour_prompt(has_location_plate=True)
    assert "The first reference image is Mara Voss" in prompt
    assert "The last reference image is this film's set" in prompt
    at = prompt.index("The last reference image")
    assert at < IMAGE_PROMPT_TOKEN_WINDOW, (
        "a sentence explaining the set photograph, sent past the window that "
        "reads it, is the plate going unexplained all over again"
    )


def test_the_plate_is_not_described_when_it_was_not_sent():
    """A sentence about "the last reference image" in a payload that has one
    image points the model at a photograph it never received -- the same
    failure as the singular note, pointed the other way."""
    prompt = _harbour_prompt(has_location_plate=False)
    assert "The last reference image" not in prompt
    # ...and the anchor is still named as the first, because it still is one
    # among the other faces this shot collects.
    assert "The first reference image is Mara Voss" in prompt


def test_the_plate_note_does_not_outrank_the_promise_it_carries():
    """They are one thing said twice -- a promise and its evidence -- so a
    frame must not keep either alone."""
    prompt = _harbour_prompt(has_location_plate=True)
    assert ("The EXACT SAME physical location" in prompt) == (
        "The last reference image is this film's set" in prompt
    )
