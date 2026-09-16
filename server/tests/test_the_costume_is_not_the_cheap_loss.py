"""The half of an entry with a picture behind it is the half that can afford
to lose words.

`_describe_characters` compacts the identity clause when a crowded scene
cannot afford it in full, and its first step used to delete the wardrobe
outright -- the whole garment, every character, before a single word of a face
was touched. The reasoning was written down: the costume lock is still in the
prompt and still covers drift.

It does not. With no garment named, the lock can only say "everyone wears the
EXACT outfit from the reference image", and the reference is a
photograph of a FACE (interfaces/character.wardrobe; both shipped reference
models bind identity from it, and flux-pulid is an identity model outright).
Job 8b8fce47-445 is what the sentence is worth on its own: one face,
consistent across six shots, wearing a slicker that buttoned, then zipped,
then hung open, went matte then glossy PVC, grew flap pockets then patch
pockets then none, and put its reflective band on the chest, then the
sleeves, then nowhere.

So the ladder now shortens both halves and deletes neither, and it spends the
face first, because the face is the half that is also being held by a picture.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from interfaces.character import CharacterInScene  # noqa: E402
from pipelines.script2video import _describe_characters  # noqa: E402


MARA_FACE = (
    "woman in her fifties, weathered face, close-cropped grey hair, "
    "deep-set brown eyes, a strong jaw"
)
#: Settled head down, the way the screenwriter prompt demands.
MARA_COAT = (
    "hood up, matte yellow hooded rain slicker, zipped to the throat, two "
    "flap pockets at the hip, one blue reflective band across the chest, "
    "nothing on her back"
)
KEL_FACE = "man in his forties, broad shoulders, buzzed dark hair, a broken nose"
KEL_COAT = (
    "bare-headed, navy quilted work jacket, snap-fastened, one square orange "
    "patch on the left breast, nothing on his back"
)


def _cast():
    return [
        CharacterInScene(
            idx=0, name="Mara Voss", static_features=MARA_FACE, wardrobe=MARA_COAT
        ),
        CharacterInScene(
            idx=1, name="Kel Ryan", static_features=KEL_FACE, wardrobe=KEL_COAT
        ),
    ]


def _fits(described, limit):
    return sum(len(d) + 2 for d in described) <= limit


#: Every budget from "everything fits" down to the floor build_frame_prompt
#: refuses to go below (``max(identity_budget, 200)``).
BUDGETS = [900, 700, 500, 420, 380, 320, 260, 200]


@pytest.mark.parametrize("limit", BUDGETS)
def test_the_clause_actually_fits_the_budget(limit):
    assert _fits(_describe_characters(_cast(), limit), limit)


@pytest.mark.parametrize("limit", BUDGETS)
def test_every_character_is_still_named_and_still_dressed(limit):
    """The garment survives all the way down to the floor."""
    described = _describe_characters(_cast(), limit)

    assert len(described) == 2
    for entry, garment in zip(described, ("slicker", "jacket")):
        assert ", wearing " in entry, entry
        assert garment in entry, entry


@pytest.mark.parametrize("limit", BUDGETS)
def test_every_character_still_opens_with_who_they_are(limit):
    """Gender and age lead a description because the screenwriter prompt says
    so -- it is the only text an image model is given about who this person
    is -- so that is the part trimming is never allowed to reach."""
    described = _describe_characters(_cast(), limit)

    assert "woman in her fifties" in described[0]
    assert "man in his forties" in described[1]


def test_the_wardrobe_is_never_trimmed_down_to_its_headwear():
    """A wardrobe is written head DOWN, so a cut taken at the last comma that
    fits keeps the hood and throws away the coat -- "wearing hood up", which
    reads as a character wearing nothing else. A ragged word boundary is worth
    more than a tidy clause boundary here."""
    tight = _describe_characters(_cast(), 200)

    assert "hood up," in tight[0], tight[0]
    assert "yellow" in tight[0], tight[0]
    assert not tight[0].rstrip(")").endswith("hood up")


def test_nothing_is_compacted_when_nothing_has_to_be():
    full = _describe_characters(_cast(), None)

    assert MARA_COAT in full[0]
    assert MARA_FACE in full[0]
    assert KEL_COAT in full[1]
    assert KEL_FACE in full[1]


def test_the_face_is_spent_before_the_coat():
    """The ordering, stated as the thing it is: one character over budget,
    and it is the tail of the description that pays while the garment is
    still whole. Under the old ladder this same budget deleted both coats."""
    full = _describe_characters(_cast(), None)
    trimmed = _describe_characters(_cast(), sum(len(d) + 2 for d in full) - 1)

    assert MARA_COAT in trimmed[0], "the coat paid for a cut it did not have to"
    assert MARA_FACE not in trimmed[0], "something had to give"
    assert "woman in her fifties" in trimmed[0]


def test_a_character_with_no_wardrobe_is_unchanged():
    """Nothing here invents a costume for a character the script did not
    dress -- that warning is _lock_character_portraits' to give."""
    bare = CharacterInScene(idx=0, name="Mara Voss", static_features=MARA_FACE)
    described = _describe_characters([bare], 200)

    assert len(described) == 1
    assert ", wearing " not in described[0]
    assert described[0].startswith("Mara Voss (woman in her fifties")
