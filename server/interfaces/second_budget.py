"""Fixed per-drama second budget, distributed across scenes by tension.

The product sells CREDITS per scene. Left unlinked from what a scene actually
is, the two units drift apart: the storyboard agent chose each scene's length
independently, so an identical 1-credit charge bought anywhere from 5 to 9
seconds of screen time -- a swing the customer, not the operator, decided.

This module ties them together. A drama gets a total budget of
``SECONDS_PER_CREDIT x scenes`` seconds, fixed and known BEFORE any credit is
charged. Dramatic tension then decides how that total is *distributed* -- a
climax still runs long and a quiet setup still runs short -- but it can no
longer change the total. The delivered product is deterministic at charge
time, while the pacing benefit survives.

WHAT A SECOND COSTS (this is the whole reason the numbers below are what they
are). The video endpoint this pipeline runs on --
``kling-v3.0-standard/pro-image-to-video`` via MuAPI -- is billed **per
generation, not per second**: $0.72 for one clip, whether that clip is 3
seconds or 15. So the unit we buy is a SCENE, and seconds within a scene are
free until the provider's 15-second ceiling. A budget set below that ceiling
is not saving money; it is declining video we have already paid for.

That is a fact about one price list, not a law, and it points the opposite way
from the per-second endpoints in the same family (``*-omni-*``, $0.084/sec)
where every extra second is real money. If this pipeline is ever pointed at a
per-second endpoint, SECONDS_PER_CREDIT stops being free and has to come back
down -- see tests/test_pricing_coherence.py, which pins the cost model these
constants assume.
"""

from typing import List, Sequence

#: Seconds of finished video one credit buys.
#:
#: Was 8.0, matching the average the previous free-choice behaviour happened
#: to produce. Under per-generation billing that average was leaving a third
#: of each paid clip on the table: 8 seconds and 12 seconds cost the operator
#: the same $0.72. Raised to 10 -- which, with the ceiling below, is 25% more
#: film for the customer at IDENTICAL cost and identical margin. Not a
#: discount: nothing about what we pay changes.
#:
#: Deliberately short of the ceiling. Pushing the average to the cap would pin
#: the top scenes there (see the ceiling note) and flatten the very tension
#: spread this module exists to express.
SECONDS_PER_CREDIT = 10.0

#: Floor and ceiling for any single scene, whatever the tension says. The
#: floor keeps a beat from becoming an unreadable flash (and keeps the fixed
#: per-scene cost -- frame + storyboard call -- from dominating); the ceiling
#: stops one scene from eating a short drama's entire budget.
#:
#: The ceiling was briefly the provider's own limit (Kling v3 accepts 3-15,
#: see tools/muapi_video_generator.clamp_duration) on the reasoning that a
#: second we are not billed for is a second worth having. The first drama
#: rendered under it says otherwise. Its climax got the ceiling -- 15 of 30
#: seconds -- and MEASURED half the movement of the other two scenes:
#:
#:     scene 1   6s   mean inter-frame motion 10.77
#:     scene 2   9s                           10.66
#:     scene 3  15s                            5.07
#:
#: Framing barely changed from second 16 to second 29; only the subtitle did.
#: The model does not fill a longer clip with more film, it fills it with more
#: of the same frame, so past ~12 seconds the extra time is spent on the shot
#: standing still. Free seconds are still not free if they are dull ones.
#:
#: 12 keeps the whole budget (the total is set by SECONDS_PER_CREDIT, not by
#: this) and spreads it: the same three-scene drama becomes 8/10/12 instead of
#: 6/10/14 -- no inert 15-second take, and the opening scene gets 8 seconds
#: instead of 6.
#:
#: The floor rose with the budget so the spread keeps its shape rather than
#: the extra seconds all piling onto the climax -- and a 6-second floor is
#: what lets a two-line scene hold its captions without them being squeezed
#: (pipelines/idea2video._lay_out_scene_captions).
MIN_SCENE_SECONDS = 6.0
MAX_SCENE_SECONDS = 12.0

#: Tension assumed for a scene that does not declare one, so legacy scripts
#: distribute evenly instead of collapsing to the floor.
DEFAULT_TENSION = 5


def total_budget_seconds(num_scenes: int) -> float:
    """Total seconds a job of this many scenes is entitled to."""
    return max(1, int(num_scenes)) * SECONDS_PER_CREDIT


def distribute_budget(
    tensions: Sequence[int], seconds_per_credit: float = SECONDS_PER_CREDIT
) -> List[float]:
    """Split the drama's fixed budget across scenes, weighted by tension.

    Returns one duration per scene. The sum equals the total budget (within
    floating-point tolerance) unless the [MIN, MAX] clamps make that
    impossible -- with N scenes the reachable range is N*MIN to N*MAX, and
    SECONDS_PER_CREDIT sits inside it by construction.

    Weighting is by tension directly, so a tension-10 climax gets twice the
    screen time of a tension-5 scene before clamping.
    """
    weights = [
        max(1, min(10, int(t) if t else DEFAULT_TENSION)) for t in tensions
    ]
    count = len(weights)
    if count == 0:
        return []

    total = count * float(seconds_per_credit)
    # Clamp the achievable total to what MIN/MAX allow, so the loop below
    # always terminates with a consistent answer.
    total = max(count * MIN_SCENE_SECONDS, min(total, count * MAX_SCENE_SECONDS))

    # Proportional first pass, then clamp.
    weight_sum = sum(weights)
    durations = [
        min(MAX_SCENE_SECONDS, max(MIN_SCENE_SECONDS, total * w / weight_sum))
        for w in weights
    ]

    # Clamping breaks the total, in BOTH directions: a tension spread like
    # [1,10,1,10,1] pins three scenes at the floor and two at the ceiling,
    # leaving budget the customer paid for unspent. Water-fill the residual
    # into (or out of) whichever scenes still have headroom, until the total
    # is met or every scene is pinned.
    for _ in range(count + 2):
        residual = total - sum(durations)
        if abs(residual) < 1e-6:
            break
        if residual > 0:
            movable = [i for i in range(count) if durations[i] < MAX_SCENE_SECONDS]
            if not movable:
                break  # genuinely cannot spend more: every scene at ceiling
            headroom = {i: MAX_SCENE_SECONDS - durations[i] for i in movable}
        else:
            movable = [i for i in range(count) if durations[i] > MIN_SCENE_SECONDS]
            if not movable:
                break  # cannot give back more: every scene at floor
            headroom = {i: durations[i] - MIN_SCENE_SECONDS for i in movable}

        # Share the residual in proportion to each scene's remaining room, so
        # tension ordering is preserved rather than flattened.
        room_sum = sum(headroom.values())
        if room_sum <= 0:
            break
        for i in movable:
            durations[i] += residual * headroom[i] / room_sum
            durations[i] = min(MAX_SCENE_SECONDS, max(MIN_SCENE_SECONDS, durations[i]))

    return _to_whole_seconds(durations, total)


def _to_whole_seconds(durations: List[float], total: float) -> List[float]:
    """Round to whole seconds while preserving the total exactly.

    The pipeline sends an INTEGER duration to the provider, and the invoice
    follows that integer -- so fractional seconds are not merely cosmetic:
    truncating 4.3 -> 4 across five scenes silently delivers less video than
    the customer was charged for. Largest-remainder assignment keeps the sum
    on target and hands the spare seconds to the scenes that lost the most in
    rounding (which, given tension weighting, are the dramatic peaks).
    """
    target = int(round(total))
    floors = [int(d) for d in durations]
    shortfall = target - sum(floors)

    if shortfall > 0:
        # Scenes with the largest fractional part, and room to grow, get +1s.
        order = sorted(
            range(len(durations)),
            key=lambda i: (durations[i] - floors[i]),
            reverse=True,
        )
        for i in order:
            if shortfall <= 0:
                break
            if floors[i] + 1 <= MAX_SCENE_SECONDS:
                floors[i] += 1
                shortfall -= 1
    elif shortfall < 0:
        order = sorted(range(len(durations)), key=lambda i: (durations[i] - floors[i]))
        for i in order:
            if shortfall >= 0:
                break
            if floors[i] - 1 >= MIN_SCENE_SECONDS:
                floors[i] -= 1
                shortfall += 1

    return [float(f) for f in floors]


def billable_seconds(durations: Sequence[float]) -> int:
    """Whole seconds actually requested from the video provider.

    The pipeline sends an integer duration, so this is what the invoice will
    reflect -- kept here so the estimate and the charge agree with the call.
    """
    return sum(int(d) for d in durations)
