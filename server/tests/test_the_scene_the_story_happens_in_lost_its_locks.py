"""The one scene the brief is about is the one that gave up its rules.

Job cfed7701-884, the harbour drama again, with the frame budget already
measured against T5 rather than guessed. Two of its three scenes behaved
exactly as the ladder promises: over the window, film-look note dropped,
lighting plan dropped, everything else read. The third did not.

    dropping 262 chars ... (Shot on 35mm film, natural filmic grain...)
    dropping 100 chars ... (The face is lit and readable, not a silhouette...)
    dropping 144 chars ... (Cast is closed: only Renata Kade appears...)
    dropping 244 chars ... (Facial expression and body language: eyes widening...)

The third scene is the one where the city's power dies -- the event the whole
brief is written around, the shot with the most to get right -- and it is the
only one that went to the model without an eyeline rule, without a closed cast
and without the acted expression the storyboard computed for it.

TWO THINGS WERE SPENDING ITS WINDOW, and neither of them is information.

* The changed-world clause said the building stands still TWICE. The
  continuity sentence already reads "identical architecture and fixtures";
  the change appended to it opened "The FIXTURES and architecture are
  unchanged, but their STATE is not". 82 tokens over the steady form of the
  same clause, at rank 1, where the eyeline and the cast cannot outbid it.

* The costume ban list was built from the COMPACTED wardrobe. Squeezed, this
  dock worker's "a hard hat with a headlamp, work gloves" fell out of her
  description -- and the enumeration, reading only the words that survived,
  went back to forbidding the hard hat she wears in the reference sheet the
  next sentence orders the model to match exactly. The tighter the window,
  the more of her own costume the prompt bans.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_TOKENS,
    build_character_identity_clause,
    build_frame_prompt,
)
from tools.t5_budget import count_tokens  # noqa: E402

HARBOUR = (
    "rain-soaked cargo harbour, stacked shipping containers under sodium "
    "floodlights"
)

#: The event the brief is written around, as the screenwriter wrote it.
BLACKOUT = (
    "every light in the city dies at once; the harbour drops to pitch black "
    "lit only by the container's white glare"
)

#: Job cfed7701-884's cast, as the character library held her -- the hard hat
#: and the gloves at the end of the wardrobe are the ones compaction drops.
RENATA = dict(
    idx=0,
    name="Renata Kade",
    static_features=(
        "woman in her late thirties, broad shoulders, close-cropped dark "
        "hair, weathered face"
    ),
    wardrobe=(
        "high-visibility orange dock jacket over a navy work shirt, heavy "
        "canvas trousers, steel-toed boots, a hard hat with a headlamp, "
        "work gloves"
    ),
)

#: Every lock that has to survive, and what its absence delivered.
LOCKS = (
    ("Cast is closed", "a one-hander came back with strangers in it"),
    ("The eyes stay inside", "the cast played the scene down the lens"),
    ("Facial expression", "the beat the storyboard computed is not acted"),
    ("Costume is LOCKED", "the outfit changes shot to shot"),
    ("Appearance is FIXED", "the frame renders somebody else"),
    ("Setting:", "the set moves between shots"),
    ("speaking mouth", "the lip-sync pass is paid for and has no mouth"),
)


def _renata():
    return CharacterInScene(**RENATA)


def _frame(shot_type, change):
    renata = _renata()
    shot = StoryboardShot(
        idx=0,
        shot_type=shot_type,
        lens="50mm",
        motion_desc="slow push in",
        expression_desc="eyes widening in stunned disbelief, mouth falling open",
        visual_desc=(
            "Renata Kade shoves the container doors wide, white light "
            "exploding out across the flooded yard and throwing her shadow "
            "fifty metres down the lane"
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
        characters=[renata],
        matched_char=renata,
        world_change=change,
        has_location_plate=True,
    )


def test_the_scene_the_event_happens_in_keeps_every_lock_the_quiet_ones_keep():
    """THE TEST THIS FILE EXISTS FOR. Scene three of the delivered job, and
    the clauses its log says it dropped."""
    prompt = _frame("medium shot", BLACKOUT)

    used = count_tokens(prompt)
    assert used <= MAX_IMAGE_PROMPT_TOKENS, f"{used} tokens: the tail is unread"
    for lock, consequence in LOCKS:
        assert lock in prompt, consequence


def test_a_close_up_of_the_event_keeps_them_too():
    """The tightest prompt this pipeline assembles: the event has to be scaled
    to the framing AND the framing has to be defended against it, so the
    changed-world clause is at its longest exactly where the window is at its
    most crowded."""
    prompt = _frame("close-up", BLACKOUT)

    used = count_tokens(prompt)
    assert used <= MAX_IMAGE_PROMPT_TOKENS, f"{used} tokens: the tail is unread"
    for lock, consequence in LOCKS:
        assert lock in prompt, consequence


def test_the_walls_are_told_to_stand_still_once():
    """Two sentences said it, and the second cost more than the closed cast.

    Measured on this frame: 82 tokens for the doubled form against the steady
    clause, 21 of them pure repetition. The eyeline rule it displaced is 27,
    the closed cast 38.
    """
    prompt = _frame("medium shot", BLACKOUT)

    assert prompt.count("identical architecture and fixtures") == 1, (
        "the continuity promise and the change that qualifies it are one "
        "sentence; saying it twice is paid for out of the cast clause"
    )
    assert "FIXTURES and architecture are unchanged" not in prompt
    assert "in a changed STATE" in prompt, "the event still has to happen"


def test_the_ban_list_does_not_forbid_the_costume_she_is_wearing():
    """The compacted wardrobe is not the wardrobe. The picture still has the
    hard hat in it, and the sentence after this one says to match it."""
    renata = _renata()
    squeezed = build_character_identity_clause([renata], renata, limit=150)

    assert "wearing high-visibility orange" in squeezed, "this is the squeezed rung"
    assert "hard hat" not in squeezed.split("Wear NOTHING")[1], (
        "compaction dropped the hard hat from her description and the "
        "enumeration then banned it -- in the same clause that orders the "
        "model to match the reference outfit exactly"
    )
    assert "gloves" not in squeezed.split("Wear NOTHING")[1]


def test_an_item_she_does_not_own_is_still_banned():
    """The enumeration is not being disarmed, only aimed. What she does not
    wear is still forbidden -- that is the drift it was written against."""
    renata = _renata()
    squeezed = build_character_identity_clause([renata], renata, limit=150)

    banned = squeezed.split("Wear NOTHING")[1]
    assert "scarf" in banned and "goggles" in banned
