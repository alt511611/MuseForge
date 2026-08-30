"""Whose story it is, in one place.

The brief says "she". The screenwriter is free to leave the protagonist's
description gender-neutral ("a dock worker in her thirties" reduced to
"thirties, weathered face"), and once the gender is gone from the text there
is nothing downstream that can put it back: the image model draws its own
default (observed in the wild: a female-led brief rendered as two men), and
voice casting falls through to a hash.

So the marker table lives here rather than inside the voice generator, and
both the writing step and the casting step read the SAME one. A word that
counts as female for a voice must count as female for a face.

Whole words only, deliberately: substring matching is a trap ("the" contains
"he", "woman" contains "man"). Turkish terms are included because briefs are
frequently written in Turkish.
"""

import re
from typing import Optional

FEMALE = "female"
MALE = "male"

FEMALE_MARKERS = (
    "woman", "women", "female", "girl", "mother", "mom", "mum", "daughter",
    "sister", "aunt", "grandmother", "wife", "lady", "she", "her", "hers",
    "kadın", "kadin", "anne", "kız", "kiz", "abla", "teyze", "hala",
    "babaanne", "anneanne", "gelin",
)
MALE_MARKERS = (
    "man", "men", "male", "boy", "father", "dad", "son", "brother", "uncle",
    "grandfather", "husband", "gentleman", "he", "him", "his",
    "adam", "erkek", "baba", "oğul", "ogul", "oğlan", "oglan",
    "abi", "ağabey", "agabey", "amca", "dayı", "dayi", "dede", "damat",
)

_FEMALE = frozenset(FEMALE_MARKERS)
_MALE = frozenset(MALE_MARKERS)

#: Word characters only — keeps "she," and "(woman)" matching, and never
#: splits a Turkish word on its diacritics.
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def infer(text: Optional[str]) -> str:
    """``"female"`` / ``"male"`` / ``""`` for a description or a brief.

    Earliest match wins: a description leads with its defining noun
    ("52-year-old woman, grey coat") and a brief usually names its
    protagonist before anyone else.
    """
    for word in _WORD.findall((text or "").casefold()):
        if word in _FEMALE:
            return FEMALE
        if word in _MALE:
            return MALE
    return ""


def infer_brief(text: Optional[str]) -> str:
    """Whose story it is, or ``""`` when the brief speaks of more than one.

    ``infer`` above answers "earliest match wins", which is right for a
    DESCRIPTION: one person, led by their defining noun. A brief is not one
    person. It introduces a cast, and the first gendered word in it belongs to
    whoever the sentence reaches first — which is not always the protagonist.

    Delivered job 754796ce-c04, brief "A card dealer in a basement game
    realises THE MAN across the table is copying HER own tell": the dealer is
    the protagonist and she is "her", the man across the table is the
    antagonist, and ``infer`` returns male because his noun arrives first.
    _apply_brief_gender would then have written "man, ..." into a female
    protagonist's description — the fault that function exists to repair,
    applied backwards. It survived only because the writer had gendered her
    already, which is the one case that function declines to touch.

    So a brief that names both declines instead. That is exactly what its
    caller already does with a brief that names neither, and it is the
    conservative half of the asymmetry the caller states: guessing wrong is
    worse than not guessing.

    Deliberately NOT used for descriptions. "A woman whose brother died" names
    two genders and one person, and voice casting still has to answer for her.
    """
    seen = set()
    for word in _WORD.findall((text or "").casefold()):
        if word in _FEMALE:
            seen.add(FEMALE)
        elif word in _MALE:
            seen.add(MALE)
        if len(seen) > 1:
            return ""
    return next(iter(seen), "")


def noun(gender: str) -> str:
    """The English noun to write into a character description."""
    return {FEMALE: "woman", MALE: "man"}.get(gender, "")
