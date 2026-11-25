"""Where each scene is, and which places get a set built.

A drama used to have exactly one place. The script carried one
``setting_location``, one empty plate was drawn from it
(pipelines/idea2video._lock_location_plate) and every frame prompt of every
scene announced it ("Setting: ... The EXACT SAME location as the opening
shot"). That is the right lock for a two-hander in a kitchen, and a wrong one
for any story that moves: the screenwriter's own instructions said "if the
story needs somewhere else, it is a different scene with a different
location", and the script had no field to write that location in. So the
second place was either squeezed into the first one or described in the action
line -- where the setting clause, the lighting plan and the plate all still
insisted on the first room, and the model drew a compromise of the two that
neither scene was set in.

A scene now says where it is (ScriptScene.location) when it is not the
drama's own place, and each such place gets a plate of its own, drawn ONCE and
reused by every scene set there -- the same lock, applied per place.

WHAT THIS MODULE DOES NOT DO. It does not let a drama wander. Every extra
place is a set that has to be built (a plate is one image generation, ~$0.05 at
the frame model's price) and, worse, a place the viewer has to be shown before
they can recognise it again. A thirty-second drama with a new place every scene
has no room to return to, which is the continuity this whole lock exists for.
So the number of extra places is capped (MAX_EXTRA_LOCATIONS), and a scene
naming a place beyond the cap keeps its words but gets no plate.
"""

from __future__ import annotations

from typing import Any, List

#: Places a drama may visit besides its own setting_location.
#:
#: Two, so a three-scene drama CAN be in three places and a longer one has to
#: come back to somewhere it has been. The screenwriter's prompt states the same
#: number in words (agents/screenwriter: "At most two places besides"); a test
#: holds the two together.
MAX_EXTRA_LOCATIONS = 2


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def scene_location(scene: Any, main_location: str) -> str:
    """The place this scene is set in.

    Its own ``location`` when it names a different place, the drama's
    otherwise. A scene that restates the drama's place in its own field --
    which a model told "only when it is somewhere else" still does -- is the
    drama's place, not a second set with the same name.
    """
    main = _clean(main_location)
    own = "" if isinstance(scene, str) else _clean(getattr(scene, "location", ""))
    if not own or own.casefold() == main.casefold():
        return main
    return own


def extra_locations(scenes: List[Any], main_location: str) -> List[str]:
    """The places beyond the drama's own that get a plate, in story order.

    First appearance wins and the cap cuts from the END: the places the story
    reaches first are the ones it establishes, and a later scene is likelier
    to be the one that should have gone back to a room already built.
    """
    seen: List[str] = []
    keys = {_clean(main_location).casefold()}
    for scene in scenes or []:
        place = scene_location(scene, main_location)
        if place and place.casefold() not in keys:
            keys.add(place.casefold())
            seen.append(place)
    return seen[:MAX_EXTRA_LOCATIONS]
