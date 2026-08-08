"""Which cut goes between two scenes — decided per boundary, not globally.

Film grammar has a default and it is the straight CUT. A dissolve is not a
prettier cut; it means *time has passed*. Applying one uniformly between every
scene (the previous behaviour of MUSEFORGE_SCENE_TRANSITIONS) tells the
audience that time passes at every join, which reads as a slideshow — and
applying none tells them nothing ever elides, which makes a jump in time land
as a continuity error.

So each boundary is decided from the two scenes' own dramatic functions:

* Into a **resolution** — the aftermath. Time has passed since the climax;
  this is the one dissolve almost every short film earns.
* Across a big **tension drop** — a beat landed and the story moved on
  somewhere else. Same elision, arrived at from the numbers rather than the
  labels, which covers scripts that leave dramatic_function unset.
* Everything else — a cut.

Returning all-zeros is the common case, and callers use that to skip the
expensive compositing concat entirely.
"""

from typing import Any, List, Sequence

#: Seconds of overlap for a dissolve. Long enough to read as an elision,
#: short enough not to eat a 6-second scene.
DISSOLVE_SECONDS = 0.6

#: A fall of this much on the 1-10 tension scale reads as "we have moved on".
TENSION_DROP_FOR_DISSOLVE = 4

_DEFAULT_TENSION = 5


def _function(scene: Any) -> str:
    if isinstance(scene, dict):
        value = scene.get("dramatic_function")
    else:
        value = getattr(scene, "dramatic_function", "")
    return str(value or "").strip().lower()


def _tension(scene: Any) -> int:
    if isinstance(scene, dict):
        value = scene.get("tension")
    else:
        value = getattr(scene, "tension", None)
    try:
        return max(1, min(10, int(value)))
    except (TypeError, ValueError):
        return _DEFAULT_TENSION


def plan_transitions(scenes: Sequence[Any]) -> List[float]:
    """One overlap duration per boundary. ``len(scenes) - 1`` entries.

    0.0 means a straight cut. Anything else is a cross-dissolve of that many
    seconds.
    """
    if len(scenes) < 2:
        return []

    plan: List[float] = []
    for i in range(len(scenes) - 1):
        outgoing, incoming = scenes[i], scenes[i + 1]
        dissolve = False

        if _function(incoming) == "resolution":
            dissolve = True
        elif _tension(outgoing) - _tension(incoming) >= TENSION_DROP_FOR_DISSOLVE:
            dissolve = True

        plan.append(DISSOLVE_SECONDS if dissolve else 0.0)
    return plan
