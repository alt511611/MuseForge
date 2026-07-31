"""Fixed per-drama second budget, distributed across scenes by tension.

The provider bills per SECOND of generated video; the product sells CREDITS
per scene. Left unlinked, those two units drift apart: the storyboard agent
chose each scene's length independently, so an identical 1-credit charge
bought anywhere from 5 to 9 seconds -- a 24-point swing in gross margin that
the customer, not the operator, decided.

This module ties them together. A drama gets a total budget of
``SECONDS_PER_CREDIT x scenes`` seconds, fixed and known BEFORE any credit is
charged. Dramatic tension then decides how that total is *distributed* -- a
climax still runs long and a quiet setup still runs short -- but it can no
longer change the total. Cost becomes deterministic at charge time, so margin
is flat regardless of what the story does, while the pacing benefit survives.
"""

from typing import List, Sequence

#: Seconds of finished video one credit buys.
#:
#: Set to match the average scene length the previous free-choice behaviour
#: actually produced (measured: 39s across 5 scenes = 7.8s), so moving to a
#: budget is revenue-neutral -- customers get the same video for the same
#: credits, they just get a promise the system can keep. Lowering this is a
#: real price rise per second of output; raising it is a discount. It is a
#: business number, deliberately a single constant.
SECONDS_PER_CREDIT = 8.0

#: Floor and ceiling for any single scene, whatever the tension says. The
#: floor keeps a beat from becoming an unreadable flash (and keeps the fixed
#: per-scene cost -- frame + storyboard call -- from dominating); the ceiling
#: stops one scene from eating a short drama's entire budget.
MIN_SCENE_SECONDS = 4.0
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
