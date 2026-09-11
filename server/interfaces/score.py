"""How loud the score sits, scene by scene, instead of once for the film.

Delivered drama 10e143bb runs thirty seconds through three scenes the
screenwriter gave rising tension, and its music is one level from the first
frame to the last. Measured on the delivered master: loudness range 5.4 LU
over the whole film -- a number that says the mix has no shape at all. The
dramatic curve the script agent wrote, the one every other stage reads
(scene length, shot scale, acting beats), stops at the soundtrack.

Nothing about that was cheap to get wrong and expensive to fix. The tension
is already in the script, the mixer already builds the music bus as its own
filter chain, and ffmpeg's volume filter already takes an expression in `t`.
What was missing was somebody deciding the number.

WHY THE CONTROL POINTS SIT AT SCENE MIDPOINTS. The obvious design -- one
level per scene, changed at the cut -- is wrong for a continuous bed. A score
that steps at a cut reads as an edit error, because a real cue either changes
with the music's own phrase or does not change at all; what a mixer writes
instead is a slow ride between the moments that matter. Putting the control
point in the MIDDLE of each scene and drawing straight lines between them
gives exactly that: the level is honest where the scene is most itself, and
everywhere else it is on its way somewhere, which is what a swell is.

WHAT THIS REFUSES TO DO. A film whose scenes are all one tension gets no
curve at all, and neither does a film whose script carried no tension. An
automation that moves for nothing is worse than a flat bed: flat is a choice,
and 2% of drift is a fault.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

#: What the quietest and the loudest scene do to the mixer's music level.
#:
#: Deliberately narrow, and deliberately not symmetric. Music under dialogue
#: is already being ducked by the sidechain; this rides on top of that, so a
#: wide range would fight the compressor for the same decibels. The range is
#: read as: a tension-1 scene sits a third under the level the mix was tuned
#: at, and a tension-10 scene a fifth over it. Across a film that is a swell
#: a listener feels and cannot point at, which is the whole trick.
QUIETEST = 0.68
LOUDEST = 1.22

#: Tension values the script agent emits, and the midpoint the scale turns on.
MIN_TENSION = 1
MAX_TENSION = 10

#: Below this spread between the film's quietest and loudest scene there is
#: nothing to express, and the caller keeps its flat level.
#:
#: Two tension points on a ten-point scale. One point is inside the noise of
#: an agent that writes "6" where it could as easily have written "5"; asking
#: the mixer to ride a fader for that produces movement with no cause, which
#: a listener reads as a fault rather than as drama.
MIN_TENSION_SPREAD = 2


@dataclass(frozen=True)
class Level:
    """The score's gain at one instant, as a multiple of the mixer's level."""

    at: float
    gain: float


def gain_for(tension: int) -> float:
    """Where a single scene's tension sits between QUIETEST and LOUDEST."""
    clamped = min(MAX_TENSION, max(MIN_TENSION, int(tension)))
    span = MAX_TENSION - MIN_TENSION
    return QUIETEST + (LOUDEST - QUIETEST) * ((clamped - MIN_TENSION) / span)


def plan_score_levels(
    spans: Sequence[Tuple[float, float]], tensions: Sequence[int]
) -> List[Level]:
    """Control points for the score's ride, or [] for a film with no curve.

    ``spans`` is each scene's (start, end) in the finished master and
    ``tensions`` its dramatic tension, in the same order. The first and last
    points are pinned to the ends of the film so the curve holds rather than
    running off its own control points.
    """
    usable = [
        (float(start), float(end), int(tension))
        for (start, end), tension in zip(spans or (), tensions or ())
        if end > start and MIN_TENSION <= int(tension) <= MAX_TENSION
    ]
    if len(usable) < 2:
        return []
    scale = [tension for _, _, tension in usable]
    if max(scale) - min(scale) < MIN_TENSION_SPREAD:
        return []

    points = [
        Level(at=(start + end) / 2.0, gain=gain_for(tension))
        for start, end, tension in usable
    ]
    # Pinned at both ends: before the first scene's middle and after the
    # last's, the ride holds instead of extrapolating off the curve.
    film_start, film_end = usable[0][0], usable[-1][1]
    if points[0].at > film_start:
        points.insert(0, Level(at=film_start, gain=points[0].gain))
    if points[-1].at < film_end:
        points.append(Level(at=film_end, gain=points[-1].gain))
    return points


def gain_at(levels: Sequence[Level], at: float) -> float:
    """The ride's gain at one instant, as a multiple of the mixer's level.

    The function ``level_expression`` renders for ffmpeg, written once in
    Python so the two cannot drift: a curve that reads one way in a test and
    another way in the mix is a curve nobody can reason about.
    """
    points = list(levels or ())
    if not points:
        return 1.0
    if at <= points[0].at:
        return points[0].gain
    if at >= points[-1].at:
        return points[-1].gain
    for left, right in zip(points, points[1:]):
        if left.at <= at <= right.at:
            span = right.at - left.at
            if span <= 0:
                return right.gain
            return left.gain + (right.gain - left.gain) * ((at - left.at) / span)
    return points[-1].gain


def level_expression(levels: Sequence[Level], base: float) -> str:
    """``levels`` as one ffmpeg expression for the volume filter.

    The same piecewise-linear function ``gain_at`` evaluates, multiplied
    through by the mixer's own level so the caller keeps one place where "how
    loud is music" is decided and this only says "relative to that, and when".

    Evaluated per frame of audio, so it is written to be cheap: a nested
    chain of comparisons and one interpolation, no function calls.
    """
    points = list(levels or ())
    if len(points) < 2:
        return f"{base:.4f}"

    expression = f"{base * points[-1].gain:.4f}"
    for index in range(len(points) - 2, -1, -1):
        left, right = points[index], points[index + 1]
        span = right.at - left.at
        if span <= 0:
            continue
        start_gain = base * left.gain
        slope = (base * right.gain - start_gain) / span
        ramp = f"{start_gain:.4f}+{slope:.6f}*(t-{left.at:.3f})"
        expression = f"if(lt(t,{right.at:.3f}),{ramp},{expression})"
    # Before the first control point the film has not started; hold.
    first = points[0]
    return f"if(lt(t,{first.at:.3f}),{base * first.gain:.4f},{expression})"
