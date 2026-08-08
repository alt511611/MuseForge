"""The texture layer: cadence, grain and scope. Pure ffmpeg, no API cost.

Colour grading already gives each director style its own look. What was still
missing is the part of "looks like film" that has nothing to do with colour:

* **Cadence.** Generated clips arrive at the provider's frame rate (commonly
  30fps). 24fps is the rate the eye reads as cinema; footage that stays clean
  and crisp through a pan reads as phone video instead.
* **Grain.** Diffusion output is unnaturally smooth between edges. A little
  noise is what stops a frame looking like a render.
* **Scope.** 2.39:1 is a format signal all on its own.

Each is separately switchable because they carry different risk, and they are
returned as *filter fragments* so the caller can fold them into the single
finishing encode it already runs rather than paying for another pass.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in TRUTHY:
        return True
    if raw in FALSY:
        return False
    return default


def target_fps() -> Optional[int]:
    """Frame rate to deliver at, or None to leave the source cadence alone.

    Default 24. Worth knowing before changing it: 30 -> 24 is not an integer
    ratio, so ffmpeg drops every fifth frame and motion carries a faint
    unevenness. That trade is deliberate — 24fps judder still reads as film to
    most viewers, while a clean 30fps reads as video to nearly all of them —
    but a deployment whose provider already delivers 24 or 25 should set
    MUSEFORGE_TARGET_FPS to that rate (or to 0) rather than resample for
    nothing.
    """
    raw = os.environ.get("MUSEFORGE_TARGET_FPS", "").strip()
    if not raw:
        return 24
    try:
        value = int(float(raw))
    except ValueError:
        return 24
    return value if value > 0 else None


def grain_strength() -> float:
    """0 disables. The default is deliberately subtle — grain that is visible
    as grain on a first watch is too strong for a 30-second piece."""
    raw = os.environ.get("MUSEFORGE_FILM_GRAIN", "").strip()
    if not raw:
        return 4.0
    try:
        value = float(raw)
    except ValueError:
        return 4.0
    return max(0.0, min(20.0, value))


def letterbox_enabled() -> bool:
    """2.39:1 matte. OFF by default, and not only for taste.

    The matte is burned into the master, so the 9:16 / 1:1 re-export
    (/api/jobs/{id}/export) would then centre-crop a frame that already has
    black bars in it and hand back a vertical video with a black band across
    the middle. Turn this on for deployments that deliver 16:9 only.
    """
    return _flag("MUSEFORGE_LETTERBOX", False)


def build_film_look_filters(width: int = 0, height: int = 0) -> Tuple[List[str], List[str]]:
    """Return (video filter fragments, extra ffmpeg output args).

    ``width``/``height`` are the master's dimensions; the matte is skipped
    unless the frame is wider than it is tall, because "scope" on a vertical
    or square master is meaningless — it would just eat the picture.
    """
    filters: List[str] = []
    args: List[str] = []

    fps = target_fps()
    if fps:
        filters.append(f"fps={fps}")
        # Also state it as an output arg so the container metadata agrees with
        # the filtered stream; players read the header, not the filter graph.
        args += ["-r", str(fps)]

    grain = grain_strength()
    if grain > 0:
        # alls = strength; t = temporal (fresh noise per frame, so it reads as
        # grain rather than as a fixed dirty-sensor pattern); u = uniform.
        filters.append(f"noise=alls={grain:.0f}:allf=t+u")

    if letterbox_enabled() and width > 0 and height > 0 and width > height:
        target_h = int(round(width / 2.39))
        # Only matte when it would actually crop something; a master already
        # at or wider than scope needs nothing.
        if 0 < target_h < height:
            # Even dimensions required by H.264 chroma subsampling.
            target_h -= target_h % 2
            pad_top = (height - target_h) // 2
            filters.append(
                f"crop={width}:{target_h}:0:{pad_top},"
                f"pad={width}:{height}:0:{pad_top}:black"
            )

    return filters, args
