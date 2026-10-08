"""What a frame judge's scores mean, decided without any model in the loop.

Phase 0 of best-of-N frame selection only MEASURES: one frame is scored and the
verdict is logged, nothing is regenerated. The verdict lives here, apart from
the vision call, so the number it produces -- "would this frame have been
thrown away" -- is the same number a later phase will act on, and so it can be
tested without a network.
"""

from __future__ import annotations

from typing import Dict, Mapping, Optional

#: Scored 0-3 by the judge. 3 = unmistakably right, 0 = plainly wrong.
DIMENSIONS = ("identity", "outfit", "setting", "face_readable", "cast_closed")

#: A frame below this on ANY of these is one the take should not be built on.
#: identity and face_readable are the two a later stage cannot repair: a
#: different face is a different film, and a mouth that cannot be seen cannot
#: be lip-synced. The rest are real faults but the take can still ship.
HARD_FLOORS: Dict[str, int] = {"identity": 2, "face_readable": 1}
SOFT_FLOORS: Dict[str, int] = {"outfit": 2, "setting": 2, "cast_closed": 2}


def clean_scores(raw: Optional[Mapping]) -> Optional[Dict[str, int]]:
    """The judge's reply as ints clamped to 0-3, or None if any dimension is
    missing -- a partial verdict is not a verdict."""
    if not isinstance(raw, Mapping):
        return None
    out: Dict[str, int] = {}
    for key in DIMENSIONS:
        try:
            out[key] = max(0, min(3, int(raw[key])))
        except (KeyError, TypeError, ValueError):
            return None
    return out


def would_reject(scores: Optional[Mapping[str, int]]) -> Optional[bool]:
    """True when a frame fails a hard floor. None when there is no verdict, so a
    missing measurement is never counted as a pass in the tally."""
    if not scores:
        return None
    return any(scores.get(dim, 3) < floor for dim, floor in HARD_FLOORS.items())


def weak_dimensions(scores: Optional[Mapping[str, int]]) -> list:
    """Every dimension under its floor, hard or soft, in a stable order."""
    if not scores:
        return []
    floors = {**HARD_FLOORS, **SOFT_FLOORS}
    return [d for d in DIMENSIONS if d in floors and scores.get(d, 3) < floors[d]]
