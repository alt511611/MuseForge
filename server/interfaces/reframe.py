"""Where to put the crop window when a wide film becomes a vertical one.

A 16:9 master reframed to 9:16 loses 68% of its width. Until now the pipeline
took that width off the middle, which is the right answer only when the
subject happens to be in the middle, and the endpoint that does it says so in
its own docstring: "a *naive center crop*, not smart subject-aware reframing.
Content near the edges of the original frame may be lost."

The same crop is what job a66acd59 is remembered for. Its takes came back
square on a 9:16 order, every scene was conformed by discarding 44% of its
width, and what lived in that 44% was the second character -- properly staged
over-the-shoulder two-shots delivered as one woman with a stray hand at the
edge of frame. That case is now caught earlier (the take is ordered in the
right shape), but the crop that did the damage is still the crop this product
offers its customers as a feature, and the format it converts INTO is where
the money is: two vertical apps hold roughly 70% of global short-drama
spending.

WHAT THIS MODULE DECIDES, AND WHAT IT REFUSES TO.

It decides, per shot, how far left or right the kept rectangle sits. It does
not pan inside a shot. A reframe that drifts while the shot holds is a camera
move nobody directed, and it reads as one -- a slow push that was not in the
storyboard is worse than an off-centre subject, because the viewer attributes
it to the film rather than to a tool. A human reframe operator picks one
position per shot and holds it, and that is the shape of the answer here.

It is handed a measurement, not a picture: per-shot column energy, which the
caller produces by decoding the master at a thumbnail size. Local contrast is
a coarse stand-in for "where the subject is" -- a face has more of it than a
wall -- and being coarse is exactly why the rules below pull every answer some
way back toward the middle before trusting it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

#: How far the window is allowed to travel from centre, as a share of the
#: slack available to it.
#:
#: Never all of it. The measurement is contrast, not recognition: a lamp, a
#: window frame or a patterned coat all read as interest, and a rule that
#: trusts the centroid completely puts the crop on the lamp. At 0.7 a
#: confident measurement still moves most of the way and a wrong one lands
#: nearer the middle than the edge, which is the failure worth having.
CENTRE_PULL = 0.7

#: Below this much travel, the window does not move at all.
#:
#: Expressed as a share of the crop's own width. Two things ride on it. The
#: honest one: a 3% offset is inside the noise of a contrast measurement, so
#: moving for it is theatre. The practical one: a film whose subjects really
#: are centred exports exactly as it did before this module existed, so the
#: feature cannot regress the case that was already right.
MIN_TRAVEL = 0.04

#: Column energy below this share of the shot's peak is read as background.
#:
#: Without a floor the centroid is dragged by the whole frame -- a textured
#: wall filling two thirds of the picture outvotes the face, and the answer
#: converges on the middle for a reason that has nothing to do with the
#: middle being right. Subtracting the floor first asks a narrower question:
#: of the parts of this frame that stand out at all, where is their weight.
BACKGROUND_FLOOR = 0.35


@dataclass(frozen=True)
class Window:
    """The kept rectangle for one shot: where it starts and how long it holds."""

    start: float
    end: float
    x: int

    @property
    def seconds(self) -> float:
        return max(0.0, self.end - self.start)


def interest_centre(columns: Sequence[float]) -> float:
    """Where this shot's subject sits across the frame, as 0.0 to 1.0.

    0.5 is dead centre, and it is also the answer for anything this cannot
    read: an empty profile, a flat one, a shot whose every column is equally
    busy. Unknown resolves to the behaviour the product already had rather
    than to a guess.
    """
    values = [max(0.0, float(value)) for value in columns or ()]
    if len(values) < 2:
        return 0.5
    peak = max(values)
    if peak <= 0:
        return 0.5

    floor = peak * BACKGROUND_FLOOR
    weights = [value - floor if value > floor else 0.0 for value in values]
    total = sum(weights)
    if total <= 0:
        return 0.5

    # Each column's centre, so the first and last columns are not read as the
    # frame's edges -- a column is a slice with width, not a point.
    span = len(values)
    weighted = sum(
        weight * ((index + 0.5) / span) for index, weight in enumerate(weights)
    )
    return min(1.0, max(0.0, weighted / total))


def window_x(centre: float, source_width: int, crop_width: int) -> int:
    """The crop's left edge in source pixels, pulled toward the middle.

    Even, because yuv420p halves both axes and an odd offset is a filter
    error rather than a one-pixel difference. Clamped inside the frame, so a
    subject standing at the very edge yields the edge-most legal window
    instead of one that hangs off the picture.
    """
    slack = max(0, int(source_width) - int(crop_width))
    if slack <= 0:
        return 0
    middle = slack / 2.0
    wanted = min(1.0, max(0.0, float(centre))) * source_width - crop_width / 2.0
    wanted = min(float(slack), max(0.0, wanted))

    pulled = middle + (wanted - middle) * CENTRE_PULL
    if abs(pulled - middle) < crop_width * MIN_TRAVEL:
        pulled = middle
    return max(0, min(slack, int(round(pulled / 2.0)) * 2))


def plan_windows(
    shots: Sequence[Tuple[float, float, float]],
    source_width: int,
    crop_width: int,
) -> List[Window]:
    """One held window per shot, from ``(start, end, centre)`` per shot.

    Shots arrive in order and cover the film; the windows come back in the
    same order, ready to be read as a stepwise function of time.
    """
    return [
        Window(start=float(start), end=float(end), x=window_x(centre, source_width, crop_width))
        for start, end, centre in shots or ()
    ]


def crop_x_expression(windows: Sequence[Window]) -> str:
    """``windows`` as one ffmpeg expression for the crop filter's ``x``.

    A stepwise function of ``t``, innermost-last, so the whole reframe is a
    single filter in a single pass. The alternative -- cutting the master at
    every shot, cropping each piece and concatenating -- is one extra decode
    and encode of the whole film to express something ffmpeg can already say.

    The LAST window has no test of its own. Every earlier one is entered by
    failing the test before it, so the final branch is "and otherwise", which
    is also what keeps the expression correct past the end of the film: a
    clip a few frames longer than the measurement still has a window.
    """
    held = [window for window in windows or () if window.seconds > 0]
    if not held:
        return "0"
    expression = str(held[-1].x)
    for window in reversed(held[:-1]):
        expression = f"if(lt(t,{window.end:.3f}),{window.x},{expression})"
    return expression


def is_still(windows: Sequence[Window]) -> bool:
    """True when every window sits in the same place.

    The caller uses it to skip the expression entirely: a film that does not
    move gets a plain integer offset, which is one less thing for ffmpeg to
    evaluate per frame and one less thing to be wrong.
    """
    positions = {window.x for window in windows or ()}
    return len(positions) <= 1
