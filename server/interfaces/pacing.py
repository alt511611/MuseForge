"""Internal cutting: a micro-drama's rhythm out of one paid generation.

A micro-drama is not shot like a film. On a vertical feed no single framing
holds for more than a couple of seconds, and the cut itself is a large part of
why the format works — a scene that sits on one angle for ten seconds reads as
slow before the viewer has judged anything else about it.

The obvious way to get that rhythm is to shoot more angles, and it is the one
this product cannot afford: the video endpoint bills per GENERATION (see
interfaces/second_budget), so every extra angle is another $0.72 against a
credit that sells for a few dollars. Three angles a scene turns a healthy
margin into a loss-making one, and the pricing tests in
tests/test_pricing_coherence.py exist to say so out loud.

So the rhythm is cut, not shot. One generation is delivered as a sequence of
framings taken from its own pixels: a wide-ish master hold, then a punch-in on
the face, then a tighter one. It is real editing grammar — the digital
equivalent of a second camera in a tighter lens — and it costs one ffmpeg
re-encode and nothing else.

Two properties this module guarantees, because everything downstream assumes
them:

* **The segments TILE the clip.** They start at 0, end at the clip's own
  duration and leave no gap, so the scene comes out exactly as long as it went
  in. Duration is the unit credits are sold in and the thing
  check_master_duration validates; a pacing pass that quietly shortened a
  scene would be selling less film than was paid for.
* **No cut in the last second.** The final beat of a shot is where the
  performance lands (see interfaces/acting) and where a dissolve into the next
  scene begins. Cutting across either is how a punchline gets stepped on.

What is deliberately NOT here: cutting on the audio. Speech is generated after
the picture and mixed over it, so this module cannot know where a line ends —
which is exactly why the mixer stopped truncating dialogue at scene borders
(see add_background_music). A cut under a continuing line is a match cut; a
cut that chops the line is a mistake, and only the mixer is in a position to
tell them apart.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Sequence

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Cut:
    """One framing, held from ``start`` to ``end`` seconds of the source clip.

    ``zoom`` is a digital punch-in: 1.0 is the frame untouched, 1.3 keeps the
    middle 77% and scales it back up. ``y_bias`` says where the kept rectangle
    sits vertically, 0.0 being the top of frame and 0.5 dead centre — faces
    live above centre in almost every composition, so a centred crop on a
    medium shot punches in on a sternum.
    """

    start: float
    end: float
    zoom: float = 1.0
    y_bias: float = 0.5

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


#: Below this there is nothing to cut: a 4-second clip broken into two beats
#: gives two beats too short to read, and the re-encode buys nothing.
MIN_CLIP_SECONDS = 5.0

#: How long any one framing may hold. The upper bound is what stops a
#: "dynamic" scene drifting back into one long take; the lower bound is the
#: point below which a cut stops reading as a cut and starts reading as a
#: glitch.
MIN_HOLD_SECONDS = 1.4
MAX_HOLD_SECONDS = 2.8

#: The opening framing gets extra time — the viewer has to understand WHERE
#: they are before a punch-in means anything.
ESTABLISH_SECONDS = 2.2

#: Never place a cut inside the last of these seconds. Protects the landing of
#: the acted peak and any cross-dissolve into the next scene
#: (interfaces/transitions.DISSOLVE_SECONDS is 0.6).
TAIL_GUARD_SECONDS = 1.0

#: Punch-in ladder, applied in order after the establishing hold. Rising and
#: falling rather than monotonic: a staircase of ever-tighter crops burns
#: through the frame's resolution and has nowhere to go, while alternating
#: reads as cutting between two cameras.
ZOOM_LADDER = (1.28, 1.14, 1.45, 1.20)

#: Vertical centre of a punched-in crop, as a fraction of frame height. Eyes
#: sit near the upper third in a conventionally framed shot.
FACE_Y_BIAS = 0.40

#: A wide or establishing frame is about the PLACE, so a crop toward the top
#: of it finds sky and ceiling. Those punch in from the middle.
WIDE_Y_BIAS = 0.50

#: Tension at or above this cuts at the fast end of the hold range.
FAST_TENSION = 8


def _flag(name: str) -> str:
    return os.environ.get(name, "").strip().lower()


def mode() -> str:
    """``on`` / ``off`` / ``auto`` — how internal cutting is decided.

    ``auto`` (the default) hands the decision to the director style: a style
    whose pacing is "fast" is asking for this and a Slow Cinematic one is
    asking for its opposite. Operators who want it everywhere, or nowhere, set
    MUSEFORGE_INTERNAL_CUTS explicitly.
    """
    raw = _flag("MUSEFORGE_INTERNAL_CUTS")
    if raw in TRUTHY:
        return "on"
    if raw in FALSY:
        return "off"
    return "auto"


def is_enabled(pacing: str = "medium") -> bool:
    """Whether this drama's director style wants its scenes cut internally."""
    setting = mode()
    if setting == "on":
        return True
    if setting == "off":
        return False
    return (pacing or "").strip().lower() == "fast"


def _hold_seconds(tension: int) -> float:
    """How long one framing holds, from the scene's dramatic tension.

    A confrontation cuts faster than a kitchen-table beat. Linear across the
    1-10 scale so the whole range is usable rather than two buckets.
    """
    try:
        value = max(1, min(10, int(tension or 0)))
    except (TypeError, ValueError):
        value = 5
    span = MAX_HOLD_SECONDS - MIN_HOLD_SECONDS
    return MAX_HOLD_SECONDS - ((value - 1) / 9.0) * span


def _y_bias(shot_type: str) -> float:
    text = (shot_type or "").strip().lower()
    if "wide" in text or "establish" in text or "aerial" in text:
        return WIDE_Y_BIAS
    return FACE_Y_BIAS


def plan_internal_cuts(
    duration: float,
    tension: int = 0,
    shot_type: str = "",
    pacing: str = "medium",
) -> List[Cut]:
    """Framings to cut this clip into. Empty means "leave it alone".

    Empty is returned for every reason not to bother — the style does not want
    it, the clip is too short, or the arithmetic leaves room for only one
    framing — so the caller can skip the re-encode entirely rather than paying
    a generation loss to change nothing.
    """
    try:
        length = float(duration or 0.0)
    except (TypeError, ValueError):
        return []
    if not is_enabled(pacing) or length < MIN_CLIP_SECONDS:
        return []

    hold = _hold_seconds(tension)
    bias = _y_bias(shot_type)

    # The establishing hold is capped so it cannot eat a short clip whole:
    # on a 5-second scene it takes 2.2s and leaves 2.8s, which is two more
    # framings, not one long tail.
    cuts: List[Cut] = []
    cursor = min(ESTABLISH_SECONDS, max(MIN_HOLD_SECONDS, length / 2.0))
    cuts.append(Cut(start=0.0, end=cursor, zoom=1.0, y_bias=bias))

    # Cut only while a full hold plus the tail guard still fits. Whatever is
    # left over is given to the final framing instead of becoming a stub --
    # this is also what keeps the last TAIL_GUARD_SECONDS free of joins.
    ladder_index = 0
    while length - cursor >= hold + MIN_HOLD_SECONDS + TAIL_GUARD_SECONDS:
        end = cursor + hold
        cuts.append(
            Cut(
                start=cursor,
                end=end,
                zoom=ZOOM_LADDER[ladder_index % len(ZOOM_LADDER)],
                y_bias=bias,
            )
        )
        cursor = end
        ladder_index += 1

    if length - cursor <= 1e-6:
        # The establishing hold consumed the clip: nothing to cut.
        return []

    cuts.append(
        Cut(
            start=cursor,
            end=length,
            zoom=ZOOM_LADDER[ladder_index % len(ZOOM_LADDER)],
            y_bias=bias,
        )
    )

    # One framing is not an edit, and re-encoding to apply a single crop to a
    # whole scene would be a zoom, not a cut.
    if len(cuts) < 2:
        return []
    return cuts


def total_duration(cuts: Sequence[Cut]) -> float:
    """Sum of the planned framings — must equal the source clip's length."""
    return sum(cut.duration for cut in cuts)
