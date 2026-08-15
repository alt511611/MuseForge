"""The moment of contact: flash, shake, and the frame that sells a slap.

Generated video is bad at impact. A model that renders a hand arriving at a
face renders the arrival smoothly, because smooth is what its training rewards
— and the result is a slap with no slap in it. Every physical beat a
micro-drama is built on (the hand, the door, the glass, the papers hitting the
table) lands soft.

Editors have fixed this since before digital: at the frame of contact you cut,
you flash, and you shake the camera. None of it is in the footage; all of it
is in the cut. That is why this is free — it is three ffmpeg filters on a
frame we already have, not a better generation of it.

Where the frame IS. Until a scene could hold two angles, this module could not
have existed: the impact frame is the CUT, and there was no cut inside a
scene to put it on. Now there is one, at a time the shot plan computes rather
than guesses (interfaces/shot_plan), so the flash lands on the join between
the master and the cutaway — which is exactly where an editor would put it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}

#: Only the hardest beats. At tension 8 a scene is a confrontation; at 10 it is
#: the moment the story turns on, and that is the one the audience should feel
#: in their chest. Applying this to every cut makes a film that flinches
#: constantly, which reads as a broken player rather than as drama.
IMPACT_TENSION = 10

#: ONE frame. Two is 83ms at 24fps, which the eye stops reading as a flash and
#: starts reading as a dropped frame.
FLASH_FRAMES = 1

#: How hard the flash is, as an ffmpeg `eq` brightness offset. Full white
#: (1.0) on a dark night scene is a strobe; this lifts the frame most of the
#: way there and lets the picture underneath show through.
FLASH_BRIGHTNESS = 0.75

#: How long the camera keeps ringing after the hit, and how far it moves. The
#: shake decays over this window -- a constant wobble reads as a handheld
#: operator, while a decaying one reads as a blow.
SHAKE_SECONDS = 0.22
SHAKE_PIXELS = 9

#: Chromatic aberration on the impact frame only: a couple of pixels of red /
#: blue separation, which is what a physical lens does under stress and what
#: every action film adds back digitally.
ABERRATION_PIXELS = 2

#: The picture is cropped by this fraction before shaking so the frame has
#: somewhere to move without exposing black edges, then scaled back.
SHAKE_HEADROOM = 0.03


@dataclass(frozen=True)
class ImpactBeat:
    """One hit, at ``at_seconds`` into the scene."""

    at_seconds: float
    flash: bool = True
    shake: bool = True
    aberration: bool = True


def _flag(name: str) -> str:
    return os.environ.get(name, "").strip().lower()


def mode() -> str:
    """``on`` / ``off`` / ``auto``. Auto means "only where the cut is"."""
    raw = _flag("MUSEFORGE_IMPACT")
    if raw in TRUTHY:
        return "on"
    if raw in FALSY:
        return "off"
    return "auto"


def plan_impacts(
    cut_seconds: Optional[float],
    tension: int = 0,
    duration: float = 0.0,
) -> List[ImpactBeat]:
    """Where to hit, given where the scene cuts. Empty means "leave it alone".

    ``cut_seconds`` is the join between the master and the cutaway. Without
    one there is no impact frame -- a hit placed in the middle of a continuous
    take has nothing to punctuate and reads as a glitch, which is why this
    returns nothing rather than inventing a position.
    """
    setting = mode()
    if setting == "off" or cut_seconds is None:
        return []
    try:
        beat = int(tension or 0)
    except (TypeError, ValueError):
        beat = 0
    if setting != "on" and beat < IMPACT_TENSION:
        return []

    at = float(cut_seconds)
    if at <= 0:
        return []
    # The ring-out has to fit inside the clip, or the shake is cut off
    # mid-wobble by the end of the scene -- which looks like a broken encode.
    if duration and at + SHAKE_SECONDS > duration:
        return []
    return [ImpactBeat(at_seconds=at)]


def build_impact_filters(
    beats: List[ImpactBeat],
    width: int,
    height: int,
    fps: float = 24.0,
) -> List[str]:
    """ffmpeg video filters for these beats, in application order.

    Returns [] when there is nothing to apply, so the caller can skip the
    re-encode entirely.
    """
    if not beats or width <= 0 or height <= 0:
        return []

    frame = 1.0 / max(1.0, float(fps))
    filters: List[str] = []

    shake_beats = [b for b in beats if b.shake]
    if shake_beats:
        # Crop in slightly so the frame has room to move, then offset that
        # window per frame.
        #
        # No `eval=frame` here, unlike scale/pad/overlay: crop has no such
        # option and rejects it outright ("Option not found"), because it
        # already re-evaluates x and y for every frame -- `t` and `n` are in
        # its expression vocabulary by definition. Adding the option that
        # every OTHER geometry filter needs is how this chain failed its first
        # real encode.
        crop_w = _even(width * (1 - SHAKE_HEADROOM))
        crop_h = _even(height * (1 - SHAKE_HEADROOM))
        base_x = (width - crop_w) / 2.0
        base_y = (height - crop_h) / 2.0
        x_terms = [base_x]
        y_terms = [base_y]
        for index, beat in enumerate(shake_beats):
            start = beat.at_seconds
            end = start + SHAKE_SECONDS
            # (1 - progress) decays the amplitude to zero by the end of the
            # window; random() is seeded differently per axis and per beat so
            # the two axes do not move as one diagonal line.
            decay = f"(1-(t-{start:.3f})/{SHAKE_SECONDS})"
            x_terms.append(
                f"if(between(t,{start:.3f},{end:.3f}),"
                f"(random({index * 2 + 1})-0.5)*2*{SHAKE_PIXELS}*{decay},0)"
            )
            y_terms.append(
                f"if(between(t,{start:.3f},{end:.3f}),"
                f"(random({index * 2 + 2})-0.5)*2*{SHAKE_PIXELS}*{decay},0)"
            )
        filters.append(
            f"crop={crop_w}:{crop_h}:x='{'+'.join(str(t) for t in x_terms)}'"
            f":y='{'+'.join(str(t) for t in y_terms)}'"
        )
        filters.append(f"scale={width}:{height}:flags=bilinear")
        filters.append("setsar=1")

    flash_windows = [
        f"between(t,{b.at_seconds:.3f},{b.at_seconds + frame * FLASH_FRAMES:.3f})"
        for b in beats
        if b.flash
    ]
    if flash_windows:
        filters.append(
            f"eq=brightness={FLASH_BRIGHTNESS}:enable='{'+'.join(flash_windows)}'"
        )

    aberration_windows = [
        f"between(t,{b.at_seconds:.3f},{b.at_seconds + frame * 2:.3f})"
        for b in beats
        if b.aberration
    ]
    if aberration_windows:
        filters.append(
            f"rgbashift=rh={ABERRATION_PIXELS}:bh=-{ABERRATION_PIXELS}"
            f":enable='{'+'.join(aberration_windows)}'"
        )

    return filters


def _even(value: float) -> int:
    """yuv420p halves both axes, so x264 refuses odd dimensions."""
    return max(2, int(value) // 2 * 2)
