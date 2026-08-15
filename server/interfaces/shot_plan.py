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
from typing import List

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
    is actually about -- and withheld in three cases:

    * the feature is off, or the scene is not a peak (tension below
      REACTION_TENSION);
    * the scene is too short to hold two beats;
    * LIP SYNC is on for this scene. The lip-sync pass drives a mouth across
      the whole scene clip, and a clip containing a cut asks it to carry a
      performance over an edit it cannot see. A desynced mouth is a worse
      defect than a missing angle, so the angle is what gives.
    """
    try:
        seconds = float(scene_seconds or 0.0)
    except (TypeError, ValueError):
        seconds = 0.0

    master_only = [PlannedShot(role=MASTER, generate_seconds=seconds)]
    if seconds <= 0:
        return master_only
    if not is_reaction_enabled() or lipsync_enabled:
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


def delivered_seconds(plan: List[PlannedShot]) -> float:
    """What this plan puts on the timeline -- which must equal the scene's
    budget, or the drama delivers less film than the credit bought."""
    return sum(
        shot.deliver_seconds if shot.deliver_seconds > 0 else shot.generate_seconds
        for shot in plan
    )
