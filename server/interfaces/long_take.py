"""A long take is drawn at both ends, not just the first.

An image-to-video model is anchored at frame 0 and nowhere else. Everything
after it is the model's own continuation, and a continuation drifts: the
references are still in the request, but they are evidence, not a constraint,
and the further the clip runs from its first frame the more the model's prior
wins over them.

Job 6efbb788 measured where that bites. Its scenes were 9 and 11 seconds, one
generation each, on MiniMax H3:

* scene 3, the blackout, opened on a correct frame -- Mira, the floodlights
  out -- and held both for about six seconds. From 26.5 s the floodlights were
  lit again, and from 28 s the woman at the lever was somebody younger with a
  different face. Nothing in the request changed; the clip simply ran out of
  first frame.
* the short shots of scene 1 (3-4 s) did not drift inside themselves at all.

The endpoints this pipeline uses take an END frame as well (``last_image`` on
the per-shot path, ``end_image_url`` on the multi-shot take), and an end frame
is the same kind of anchor as the first one: the clip has to arrive at it. So
a take long enough to drift has its last frame DRAWN -- from the opening frame
and the character's own reference, by the image model that is measured to hold
a face (Nano Banana) -- and the video model interpolates toward it instead of
wandering away.

WHAT THE END FRAME IS. Not the opening frame again: a take that has to end
where it began is a take that cannot perform its action (the lever stays
unpulled). It is the same shot a few seconds later, at the end of the action
the storyboard wrote, with the same face, clothes, place, camera and light --
and, after the drama's event, the same changed world. The acted peak from
interfaces/acting is where the face lands, when the shot has one.

WHAT IT COSTS. One image generation per long take (about $0.06 on Nano Banana)
and its seconds of latency, against a take billed per second. Shots under
LONG_TAKE_SECONDS are left exactly as they were: they did not drift.
MUSEFORGE_LONG_TAKE_END_FRAME=0 turns it off.
"""

from __future__ import annotations

import os
from typing import Any

#: The length from which a take is given a drawn last frame.
#:
#: Job 6efbb788's blackout held for about six seconds and broke after it; its
#: 3-4 s shots never broke. Seven is past the first and short of the second.
LONG_TAKE_SECONDS = 7.0


def is_enabled() -> bool:
    return (os.environ.get("MUSEFORGE_LONG_TAKE_END_FRAME", "1") or "").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def is_long(seconds: Any) -> bool:
    """Whether a take of ``seconds`` is long enough to be anchored at its end."""
    try:
        value = float(seconds or 0)
    except (TypeError, ValueError):
        return False
    return is_enabled() and value >= LONG_TAKE_SECONDS


def end_frame_prompt(
    action: str = "",
    name: str = "",
    peak: str = "",
    world_state: str = "",
    has_reference: bool = True,
) -> str:
    """The instruction for the take's last frame.

    Image 1 is the take's opening frame; Image 2, when there is one, is the
    character's own reference. Said as a moment, not as an edit: the frame
    has to move on from the opening (the action happens) while everything
    the viewer uses to recognise the shot stays where it was.
    """
    who = name.strip() or "the person"
    parts = [
        "The LAST frame of the same shot as the first image, a few seconds "
        "later -- the same camera position, lens, framing and light, the same "
        "place, the same moment of the story.",
    ]
    if action.strip():
        parts.append(f"It shows the end of this action: {action.strip().rstrip('.')}.")
    identity = (
        f"{who} is the same person as in both images: identical face, hair, age "
        "and clothing."
        if has_reference
        else f"{who} is the same person as in the first image: identical face, "
        "hair, age and clothing."
    )
    parts.append(identity)
    if peak.strip():
        parts.append(f"The face lands on: {peak.strip().rstrip('.')}.")
    if world_state.strip():
        parts.append(
            f"The world has already changed and stays changed: "
            f"{world_state.strip().rstrip('.')}."
        )
    parts.append(
        "Nobody new enters, nothing is added to the set, and nobody looks at "
        "the camera. Photographic, continuous with the first image."
    )
    return " ".join(parts)


def event_spans_take(
    world_change: str,
    shot_count: int,
    seconds: Any,
    has_character: bool,
    draws_frames: bool,
) -> bool:
    """Whether the drama's event should HAPPEN across this take.

    The pipeline treated the scene the event happens in exactly like every
    scene after it: changed from its first frame. That is right for a scene
    that inherits the blackout and wrong for the one that causes it, and two
    delivered jobs show what it costs. Both briefs were "the city's power dies
    the moment she opens it"; both climaxes were one long close-up; in both
    the opening frame was already dark, so the doors never opened, no light
    poured out, and nothing went out -- the film's event was over before the
    shot began. Job d91a4172 then lit the floodlights again mid-take, between
    two dark anchors, because nothing in the take was the change.

    A take with both ends drawn can carry the change itself: open on the
    world BEFORE, end on the world AFTER, and the video model has to
    interpolate the event. That needs a take long enough to hold it, a face
    to anchor its end frame to, frames to draw at all, and a scene that is
    ONE shot -- a scene covered in several is left as it was, every angle
    changed, because which angle the event falls in is not something this
    can know.
    """
    return (
        bool((world_change or "").strip())
        and int(shot_count or 0) == 1
        and has_character
        and draws_frames
        and is_long(seconds)
    )
