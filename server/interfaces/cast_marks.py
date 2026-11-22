"""A mark that tells one face from another across a cut.

WHY THIS EXISTS. A delivered 30-second drama about three sailors came back with
five faces: the man in a red headband in the fourth second was nobody who had
been in the wide shot before it. The pipeline locks a face to a portrait, and a
portrait is only half of what holds a person together -- the other half is one
thing a viewer can see in any frame, at any size, in the dark, that says WHICH
of the people on the raft this is. A short-form series that keeps its cast
recognisable across twenty-odd episodes does it the same way: a moustache, a
braid, a headband. A feature the picture cannot lose.

The mark travels INSIDE ``wardrobe``, in front. That is the one channel every
consumer already reads -- the portrait prompt, every frame prompt, the take's
cast clause, a saved series cast -- so nothing downstream has to learn a new
field. It goes first because ``scene_take._fit_wardrobe`` cuts an outfit from
the end: when the cast clause runs out of room the last garment is what
goes, and the mark is the one part that must not.

This module only folds and checks. It never writes a mark: inventing one for a
character the model left plain would be a guess dressed up as a design, and a
wrong guess is worse than none.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

#: Longer than this and a mark is a costume, which is what ``wardrobe`` is for.
MAX_MARK_CHARS = 60

#: Two looks that share at least this fraction of their words read as one look.
SAME_LOOK = 0.6


def _words(text: str) -> set:
    return set(re.findall(r"[^\W_]+", (text or "").lower()))


def _clip(mark: str) -> str:
    """The mark on a word boundary, at most MAX_MARK_CHARS."""
    mark = " ".join((mark or "").split()).strip(" ,;:.")
    if len(mark) <= MAX_MARK_CHARS:
        return mark
    cut = mark[:MAX_MARK_CHARS].rsplit(" ", 1)[0]
    return cut.strip(" ,;:.")


def fold(mark: str, wardrobe: str) -> str:
    """``wardrobe`` with ``mark`` in front of it, unless it already says it."""
    mark = _clip(mark)
    wardrobe = (wardrobe or "").strip()
    if not mark:
        return wardrobe
    mark_words = _words(mark)
    if mark_words and mark_words <= _words(wardrobe):
        return wardrobe
    return f"{mark}, {wardrobe}" if wardrobe else mark


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def same_look(a, b) -> bool:
    """Whether two characters would be told apart by what they are given.

    Marks decide it when both have one. Otherwise their wardrobes do: three
    sailors in one beige tunic are one look three times, and nothing but a
    face -- the thing that drifts -- separates them.
    """
    mark_a, mark_b = _words(_clip(getattr(a, "mark", ""))), _words(_clip(getattr(b, "mark", "")))
    if mark_a and mark_b:
        return _jaccard(mark_a, mark_b) >= SAME_LOOK
    return _jaccard(_words(getattr(a, "wardrobe", "")), _words(getattr(b, "wardrobe", ""))) >= SAME_LOOK


def collisions(characters: Sequence) -> List[Tuple[str, str]]:
    """Pairs of characters who share a look."""
    found = []
    chars = list(characters or [])
    for i, a in enumerate(chars):
        for b in chars[i + 1 :]:
            if same_look(a, b):
                found.append((a.name, b.name))
    return found


def unmarked(characters: Iterable) -> List[str]:
    """Names with no mark, in a cast where one is needed to tell them apart.

    A lone character has nobody to be mistaken for.
    """
    chars = list(characters or [])
    if len(chars) < 2:
        return []
    return [c.name for c in chars if not _clip(getattr(c, "mark", ""))]
