"""How many angles a scene gets, and how long each one is generated for.

A micro-drama's most-watched moment is a reaction: the face that hears the
line, not the mouth that says it. One camera cannot show both, so the beat
that carries a scene is precisely the beat one shot cannot cover.

Buying a second angle is a pricing question before it is a filmmaking one, and
the answer is not the obvious one. MuAPI bills two ways (verified, see
tests/test_pricing_coherence.MUAPI_RATES):

    FLAT per generation      kling-v3.0-standard  $0.72 (up to 15s)
                             veo3.1-lite          $0.30
    PER SECOND               kling-v3-turbo       $0.112/s
                             seedance-2.5-480p    $0.17/s

So the endpoints that sound cheap are the expensive ones here: a 2-second
reaction costs $0.22 on turbo and $0.34 on seedance-480p, against $0.30 flat
on veo3.1-lite for a clip of ANY length it will produce. A short clip does not
earn a discount from a per-second rate; it earns a smaller bill from a rate we
are not paying.

Two consequences shape everything below.

**GENERATE LONG, DELIVER SHORT.** Under flat billing the length we ask for and
the length we cut in are different numbers, and only the second one is
dramaturgy. The master is generated at the scene's full second budget exactly
as it always was -- same cost, same render time -- and delivered two seconds
shorter to make room for the reaction. Shortening the REQUEST would save
nothing at all: it would decline video already paid for, which is the mistake
interfaces/second_budget was written to stop.

**WHICH TWO SECONDS ARE DROPPED IS A DIRECTING DECISION.** The head, not the
tail. A generated clip spends its first moments settling into motion, while
its final frame is where the acted peak lands (interfaces/acting) -- so the
master keeps its ending and cuts to the reaction directly off the peak, which
is where a cut belongs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, List, Sequence

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}

MASTER = "master"
REACTION = "reaction"


@dataclass(frozen=True)
class PlannedShot:
    """One angle: what to ask the provider for, and what to cut in."""

    role: str
    #: Seconds requested from the video model. Costs the same anywhere inside
    #: a flat endpoint's range, so this is chosen for what it makes possible,
    #: not for what it costs.
    generate_seconds: float
    #: Seconds that reach the timeline. 0 means "the whole clip" -- the
    #: single-shot case, where nothing is trimmed and the behaviour is exactly
    #: what it was before this module existed.
    deliver_seconds: float = 0.0
    #: Trim from the head rather than the tail. See the module docstring: the
    #: end of a clip is where the performance lands.
    trim_from_head: bool = True


#: Tension at or above this earns a second angle. Deliberately the SAME
#: threshold the router already uses to call a shot an action beat
#: (video_model_router.ACTION_TENSION) -- one dramatic scale, read the same way
#: everywhere. A second 0-1 "intensity" scale alongside the screenwriter's
#: 1-10 tension would drift from it within a release.
REACTION_TENSION = 8

#: How long the reaction is on screen. Long enough to read a face, short
#: enough to be a punctuation mark rather than a scene of its own.
REACTION_SECONDS = 2.0

#: The master may not fall below this after making room. Under it, the scene
#: has no room for two angles and gets one good one instead.
MIN_MASTER_SECONDS = 4.0

#: What the reaction endpoint is asked for. veo3.1-lite's duration is the enum
#: [8] and nothing else (verified on its API reference; enforced in
#: video_model_router.FIXED_DURATION), so this is a request, not a promise --
#: the clip comes back at the model's own length and is trimmed to
#: REACTION_SECONDS. That is not waste: the bill is flat either way.
REACTION_GENERATE_SECONDS = 8.0


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in TRUTHY:
        return True
    if raw in FALSY:
        return False
    return default


def is_reaction_enabled() -> bool:
    """Whether scenes may buy a second angle.

    OFF by default, and this one really is about money rather than caution: a
    reaction shot adds a video generation plus its frame (~$0.34), which takes
    a Pro-plan scene from roughly 78% margin to 68%. That still clears the
    floor the pricing tests enforce, but it is a deliberate business decision
    and not something a deployment should discover by accident.
    """
    return _flag("MUSEFORGE_REACTION_SHOTS", False)


def plan_scene_shots(
    scene_seconds: float,
    tension: int = 0,
    lipsync_enabled: bool = False,
) -> List[PlannedShot]:
    """Angles for one scene, in cut order.

    Returns a single master for the overwhelming majority of scenes. The
    second angle is spent where it is worth its price -- the scene the drama
    is actually about -- and withheld in two cases:

    * the feature is off, or the scene is not a peak (tension below
      REACTION_TENSION);
    * the scene is too short to hold two beats.

    LIP SYNC used to be a third case. The sync pass drives a mouth across the
    clip it is given and cannot see a cut in the middle of one, so a two-angle
    scene was refused the second angle outright whenever sync was on -- which
    flattened every peak scene to a single framing on exactly the runs that
    care most about performance, and made "lip sync" and "reaction shots" a
    choice between two things users ask for together.

    The refusal was aimed at the wrong half of the cut. A reaction shot is the
    other character LISTENING; there is no mouth in it to drive. So the tail is
    now held back from the sync and rejoined afterwards
    (idea2video._reaction_tail_seconds), and ``lipsync_enabled`` no longer
    decides whether the angle exists. It is still accepted, so callers do not
    have to change and an operator can restore the old behaviour by pinning
    MUSEFORGE_REACTION_SHOTS off.
    """
    try:
        seconds = float(scene_seconds or 0.0)
    except (TypeError, ValueError):
        seconds = 0.0

    master_only = [PlannedShot(role=MASTER, generate_seconds=seconds)]
    if seconds <= 0:
        return master_only
    if not is_reaction_enabled():
        return master_only

    try:
        beat = int(tension or 0)
    except (TypeError, ValueError):
        beat = 0
    if beat < REACTION_TENSION:
        return master_only

    master_deliver = seconds - REACTION_SECONDS
    if master_deliver < MIN_MASTER_SECONDS:
        return master_only

    return [
        PlannedShot(
            role=MASTER,
            # Unchanged from the single-shot case on purpose: same request,
            # same cost, same render time. Only the delivered length moves.
            generate_seconds=seconds,
            deliver_seconds=master_deliver,
            trim_from_head=True,
        ),
        PlannedShot(
            role=REACTION,
            generate_seconds=REACTION_GENERATE_SECONDS,
            deliver_seconds=REACTION_SECONDS,
            # The reaction's own head is where the face is still arriving at
            # the emotion; its tail is the emotion. Same rule, same reason.
            trim_from_head=True,
        ),
    ]


#: Shot scales, widest to tightest. The ladder is what makes "vary the
#: framing" a computation rather than a hope: a collision is resolved by
#: stepping along it, in the direction the drama is already moving.
SCALE_LADDER = ("wide shot", "medium shot", "close-up", "extreme close-up")


def _base_scale(function: str, tension: int) -> str:
    """The framing a scene wants on its own, before its neighbours are known."""
    function = (function or "").strip().lower()
    if function == "climax" or tension >= 9:
        return "close-up"
    if function in ("setup", "establishing") or tension <= 4:
        return "wide shot"
    if tension >= 7 or function in ("turning_point", "inciting_incident"):
        return "medium shot"
    return "medium shot"


def plan_shot_scales(scenes: Sequence[Any]) -> List[str]:
    """One framing per scene, guaranteed not to repeat back to back.

    Scenes are storyboarded independently and, by default, in PARALLEL -- so
    nothing tells scene 2 that scene 1 was a medium two-shot. Measured on a
    delivered drama: its first two scenes were the same framing of the same
    two people, eighteen seconds of one setup, and neither shot was wrong on
    its own. Repetition is only visible from outside a scene, which is exactly
    where no part of the pipeline was standing.

    Derived from the SCRIPT rather than from rendered results, for the same
    reason the story-state fence is (see idea2video._format_story_state): the
    results do not exist yet when the decision has to be made, and a plan that
    waits for them would have to give up rendering scenes concurrently.

    A collision is broken by stepping along SCALE_LADDER in the direction the
    story is already going -- tighter when the scene is more tense than the one
    before it, wider when it is calmer. That is not a tie-break dressed up as
    grammar: cutting tighter as a drama escalates is what escalation looks
    like, and a climax pushed from close-up to extreme close-up is a better
    climax, not a compromise.
    """
    scales: List[str] = []
    previous_tension = 0
    for scene in scenes or []:
        function = _scene_attr(scene, "dramatic_function")
        try:
            tension = int(_scene_attr(scene, "tension") or 0)
        except (TypeError, ValueError):
            tension = 0

        scale = _base_scale(function, tension)
        if scales and scale == scales[-1]:
            index = SCALE_LADDER.index(scale)
            step = 1 if tension >= previous_tension else -1
            nudged = index + step
            if not 0 <= nudged < len(SCALE_LADDER):
                nudged = index - step  # at an end of the ladder; go the other way
            if 0 <= nudged < len(SCALE_LADDER):
                scale = SCALE_LADDER[nudged]
        scales.append(scale)
        previous_tension = tension
    return scales


def _scene_attr(scene: Any, field: str) -> str:
    if isinstance(scene, dict):
        return str(scene.get(field) or "")
    return str(getattr(scene, field, "") or "")


def delivered_seconds(plan: List[PlannedShot]) -> float:
    """What this plan puts on the timeline -- which must equal the scene's
    budget, or the drama delivers less film than the credit bought."""
    return sum(
        shot.deliver_seconds if shot.deliver_seconds > 0 else shot.generate_seconds
        for shot in plan
    )


#: A coverage shot shorter than this is a flash frame, not a shot. Only
#: enforced when the scene can afford it for every shot (a 6-second scene
#: covered in four is asking for something this cannot give it).
MIN_COVERAGE_SECONDS = 2.0


def split_scene_seconds(
    scene_seconds: float, proposed: Sequence[Any]
) -> List[float]:
    """Divide one scene's second budget between the shots that cover it.

    ``proposed`` is each shot's own duration as the storyboard designed it,
    used only for its PROPORTIONS -- an establishing wide the designer gave 3
    seconds and a close it gave 7 keep that ratio inside whatever the budget
    turns out to be.

    Coverage (MUSEFORGE_SHOTS_PER_SCENE above 1) is the one place where a
    scene is more than one shot without going through plan_scene_shots, and
    the budget was being applied per SHOT rather than per scene: every shot
    was set to the scene's full length, so a scene covered in two ran twice as
    long as it was costed at. Measured on a delivered job (3 scenes, 30-second
    budget, coverage of 2):

        scene_0/scene_output.mp4   16.08s   budgeted  8
        scene_1/scene_output.mp4   20.08s   budgeted 10
        scene_2/scene_output.mp4   24.08s   budgeted 12

    The prompt already told the model to divide the scene between its shots
    (agents.storyboard_artist.coverage_clause: "Their duration_seconds must
    SUM to the scene's length"), and _clamp_durations then overwrote the
    answer with the whole budget. This is that instruction, in code, where it
    binds.

    Whole seconds, because the pipeline sends the video endpoint an INTEGER
    duration and trims the returned clip to the same number: a fractional
    share would be requested truncated and delivered short. The shares sum to
    the budget exactly.
    """
    count = len(proposed)
    try:
        total = int(round(float(scene_seconds or 0.0)))
    except (TypeError, ValueError):
        total = 0

    # One shot carries the whole scene, which is the overwhelming majority of
    # them and the path that must stay exactly as it was.
    if count <= 1:
        return [float(total)] * count
    if total <= 0:
        return [_seconds(p) for p in proposed]
    if total < count:
        # Unreachable with the real constants (MIN_SCENE_SECONDS is 6 and
        # coverage caps at 4), and not worth returning a zero-length shot over.
        return [total / float(count)] * count

    weights = [_seconds(p) for p in proposed]
    if sum(weights) <= 0:
        weights = [1.0] * count  # the designer said nothing; split it evenly

    weight_sum = sum(weights)
    shares = [total * w / weight_sum for w in weights]
    floor = MIN_COVERAGE_SECONDS if total >= count * MIN_COVERAGE_SECONDS else 1.0
    return _whole_seconds(_lift_to_floor(shares, floor), total)


def _seconds(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _lift_to_floor(shares: List[float], floor: float) -> List[float]:
    """Raise every share to ``floor``, paid for by the shares above it.

    The total is preserved: the caller only calls this when the floor is
    affordable for every share, so what the short ones need is always less
    than what the long ones can give.
    """
    deficits = {i: floor - s for i, s in enumerate(shares) if s < floor}
    if not deficits:
        return shares
    room = {i: s - floor for i, s in enumerate(shares) if s > floor}
    available = sum(room.values())
    owed = sum(deficits.values())
    if available <= 0:
        return shares
    paid = min(owed, available)
    for i, spare in room.items():
        shares[i] -= paid * spare / available
    for i, short_by in deficits.items():
        shares[i] += paid * short_by / owed
    return shares


def _whole_seconds(shares: List[float], total: int) -> List[float]:
    """Round to whole seconds without losing (or inventing) any.

    Largest-remainder assignment, same as second_budget._to_whole_seconds and
    for the same reason: the truncated seconds are film the customer paid for,
    and dropping one from each of three shots is three seconds gone from a
    thirty-second drama.
    """
    whole = [int(s) for s in shares]
    shortfall = total - sum(whole)
    order = sorted(
        range(len(shares)), key=lambda i: shares[i] - whole[i], reverse=True
    )
    for i in order:
        if shortfall <= 0:
            break
        whole[i] += 1
        shortfall -= 1
    return [float(w) for w in whole]
