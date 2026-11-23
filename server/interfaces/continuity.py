"""What one scene hands to the next.

Scenes are storyboarded and rendered independently and in parallel, so a scene
knows what happened before it (``story_so_far`` carries the earlier TURNS) but
not the physical state those turns left behind: where everyone ended up, who is
wet or hurt, what is in whose hands, how much time has gone by, what the light
is doing. The writer is the one who knows. It states it twice per scene --
``starts_with`` and ``ends_with`` -- and this module holds the two to each
other, because a model asked for both will occasionally write a scene that
opens on a dry deck after the one before it ended in the sea.

The repair is deterministic and takes the earlier scene's ``ends_with`` as the
truth: it is what the writer committed to first, and re-asking an LLM to
reconcile two of its own sentences costs a call to get an answer this can
reach by itself.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List

logger = logging.getLogger(__name__)

#: Words that name a physical state a scene can leave behind, grouped so that
#: two members of DIFFERENT sides of one pair contradict each other. Only
#: states a camera can see and that an unmarked jump would silently reset.
_OPPOSED = (
    (r"\b(?:wet|soaked|drenched|dripping|sodden)\b", r"\b(?:dry|dried|dry-clothed)\b"),
    (r"\b(?:night|midnight|moonlit|dark)\b", r"\b(?:day|daylight|noon|midday|sunlit)\b"),
    (r"\b(?:dusk|sunset|twilight)\b", r"\b(?:dawn|sunrise|morning)\b"),
    (r"\b(?:injured|bleeding|wounded|limping)\b", r"\b(?:unhurt|unharmed|uninjured)\b"),
    (r"\b(?:on the boat|aboard|at sea|adrift)\b", r"\b(?:on the shore|ashore|on land|on the beach)\b"),
    (r"\b(?:alone)\b", r"\b(?:together|all (?:five|four|three|of them))\b"),
)

#: A writer who MEANS the jump says so, and then there is nothing to repair.
_DECLARED_JUMP = re.compile(r"^\s*(?:jump|later|time\s*cut|cut\s*to)\b", re.IGNORECASE)


def _field(scene: Any, name: str) -> str:
    if isinstance(scene, dict):
        value = scene.get(name, "")
    else:
        value = getattr(scene, name, "")
    return (value or "").strip() if isinstance(value, str) else ""


def _contradicts(left: str, right: str) -> bool:
    left, right = left.lower(), right.lower()
    for side_a, side_b in _OPPOSED:
        if (re.search(side_a, left) and re.search(side_b, right) and not re.search(side_a, right)) or (
            re.search(side_b, left) and re.search(side_a, right) and not re.search(side_b, right)
        ):
            return True
    return False


def opening_state(scenes: List[Any], index: int) -> str:
    """The state scene ``index`` must open in, or "" for the first scene."""
    if index <= 0 or index >= len(scenes):
        return ""
    own = _field(scenes[index], "starts_with")
    previous = _field(scenes[index - 1], "ends_with")
    if own and _DECLARED_JUMP.match(own):
        return own
    return previous or own


def reconcile(scenes: List[Any]) -> List[str]:
    """Make every scene open in the state the one before it ended in.

    Returns one note per repair, for the log. Legacy string scenes carry
    neither field and are left alone.
    """
    notes: List[str] = []
    for index in range(1, len(scenes)):
        scene = scenes[index]
        if isinstance(scene, str):
            continue
        previous = _field(scenes[index - 1], "ends_with")
        own = _field(scene, "starts_with")
        if not previous or (own and _DECLARED_JUMP.match(own)):
            continue
        if own and not _contradicts(previous, own):
            continue
        try:
            scene.starts_with = previous
        except (AttributeError, ValueError):
            continue
        notes.append(
            f"Scene {index + 1} opened on a state that contradicts how scene "
            f"{index} ended; it now opens on {previous!r}."
            if own
            else f"Scene {index + 1} stated no opening; it now opens on how scene {index} ended."
        )
    for note in notes:
        logger.warning("Continuity: %s", note)
    return notes
