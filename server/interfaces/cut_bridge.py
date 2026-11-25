"""What the frame after a cut is shown of the frame before it.

Every scene's opening frame was drawn from the same three things: the locked
portraits, the empty-set plate and the prompt. None of them is the scene that
was just on screen. So two scenes in the same room, back to back, were two
independent drawings of that room -- the same architecture (the plate held
it) under different light, from a different side, with the props wherever
the model put them this time. The plate is a picture of the set EMPTY, at no
particular moment; what a viewer compares across a cut is the moment before.

The obvious fix was already in this repo and is switched off for a reason.
``MUSEFORGE_DYNAMIC_REFERENCE`` feeds each character's latest generated frame
forward as their IDENTITY reference, and a generated frame is only an
approximation of its reference -- so the face does a random walk, a little
further from the portrait every scene ("the mother and daughter look like
different people in different scenes"). The lesson is not "never send a
generated frame". It is "never let one bind a face".

So the bridge goes in as a SET reference, never as an anchor:

* second to last in the reference set, after every portrait and before the
  plate (script2video.resolve_frame_references), so the face is still bound
  to the locked portrait ahead of it and "the last reference is the set" is
  still true;
* named for what it carries -- the light and the layout, "not its people,
  pose or framing" (script2video._BRIDGE_AND_PLATE_NOTE) -- in the same
  sentence that names the plate, so it costs the identity reserve the
  difference between two sentences and no more;
* only on the opening frame of the scene. The later angles of a scene are
  already held to one another by the plate and the scene's own lighting plan.

WHEN THERE IS NO BRIDGE. Only consecutive scenes in the same place, and not
across a declared jump ("JUMP: three days later" -- the light the writer
moved on purpose), and not into the scene where the world itself changes
(its opening frame would be told to match a state the scene is about to
destroy). A scene whose place has no plate gets none either: the sentence the
bridge rides on is the plate's.

WHAT IT COSTS. Nothing in money -- it is one more reference on a call already
being made. In time, one frame: scenes render in parallel, and a bridged
scene's opening frame waits for the previous scene's opening frame. Only that
frame waits. The storyboard before it and the video after it do not, and
BRIDGE_WAIT_SECONDS caps the wait so a stalled scene never holds its
neighbour hostage -- a bridge that does not arrive is a frame drawn exactly
as before.
"""

from __future__ import annotations

import os
from typing import Any, List

from interfaces.continuity import is_declared_jump

#: How long a scene's opening frame waits for the previous scene's.
#:
#: A frame is tens of seconds; five minutes is a frame that is not coming. The
#: cost of giving up is one unbridged cut, so this errs on letting go.
BRIDGE_WAIT_SECONDS = 300.0

def is_enabled() -> bool:
    """On unless ``MUSEFORGE_CUT_BRIDGE`` turns it off."""
    return os.environ.get("MUSEFORGE_CUT_BRIDGE", "").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _field(scene: Any, name: str) -> str:
    if isinstance(scene, str):
        return ""
    value = scene.get(name, "") if isinstance(scene, dict) else getattr(scene, name, "")
    return value.strip() if isinstance(value, str) else ""


def bridges(scenes: List[Any], index: int, places: List[str], has_plate: bool) -> bool:
    """Whether scene ``index`` opens on a frame bridged from the scene before.

    ``places`` is each scene's place, as interfaces/places.scene_location
    resolved it, in scene order.
    """
    if not is_enabled() or index <= 0 or index >= len(scenes) or not has_plate:
        return False
    if index >= len(places) or not places[index] or places[index] != places[index - 1]:
        return False
    if is_declared_jump(_field(scenes[index], "starts_with")):
        return False
    if _field(scenes[index], "world_change"):
        return False
    return True
