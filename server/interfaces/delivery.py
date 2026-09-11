"""What size a finished drama is actually delivered at.

Two separate questions live here, and they were previously answered by one
constant.

**WHICH STANDARD SIZE.** A delivered master is not just "some pixels of the
right shape". It is a file another piece of software has to accept: an editor
timeline, a platform's ingest, a client's spec sheet. Those all speak in named
resolutions, and a size that is not one of them reads as a broken export even
when it is mathematically closer to the truth.

Job-audit evidence, verbatim: a 16:9 master shipped at **1276x718**. Not
1280x720, not 1920x1080, and -- at 1.777158 -- not exactly 16:9 either. It came
out of an honest rule (never upscale: fit the largest correctly-shaped
rectangle inside what the provider really rendered) applied without a second
one (land on a size that exists). Fourteen pixels of width were saved and the
file stopped being a 720p file.

So the fit is snapped UP to the nearest rung of DELIVERY_LADDER when it is
within SNAP_TO_LADDER_TOLERANCE of it. Up, never down: snapping a 608x1080
vertical fit down to 480x854 would throw away a quarter of the picture the
render actually produced, which is the opposite of the problem being fixed.

**WHICH TIER.** The other half is a product decision. No video model in this
pipeline returns 4K -- Kling, Veo and Seedance all deliver 1080p-class frames
-- and competitors advertising "4K" are upscaling at the end of their chain,
because that is the only thing anyone can do today. This module makes that a
declared tier rather than a lie: a 4K delivery is a real 3840x2160 file,
produced by one lanczos upscale in the finishing encode that was happening
anyway, and every delivery reports ``upscaled`` and the size the pixels were
really generated at. The product may sell 4K. The record may not pretend the
render was 4K.

The default tier is 1080p and it NEVER upscales, which is exactly the
behaviour every existing job had. Upscaling is something a customer asks for.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

#: Delivery tiers, smallest first. The names are the ones a customer reads on
#: a plan page, which is why "4k" is spelled the marketing way and the rest are
#: spelled the broadcast way -- nobody has ever asked for "2160p".
DELIVERY_TIERS: Tuple[str, ...] = ("480p", "720p", "1080p", "1440p", "4k")

#: What a job gets when nothing asks for anything. 1080p is what the models
#: generate, so this is the one tier that is never an upscale.
DEFAULT_TIER = "1080p"

#: Standard delivery sizes per ratio, one per tier, in DELIVERY_TIERS order.
#:
#: Every rung is even on both axes (yuv420p halves each axis, so x264 refuses
#: odd dimensions) and within 0.1% of its ratio. 854x480 is the one that looks
#: wrong and is not: 480 * 16/9 is 853.33, and 854 is the size the rest of the
#: world calls 480p.
DELIVERY_LADDER: Dict[str, Tuple[Tuple[int, int], ...]] = {
    "16:9": ((854, 480), (1280, 720), (1920, 1080), (2560, 1440), (3840, 2160)),
    "9:16": ((480, 854), (720, 1280), (1080, 1920), (1440, 2560), (2160, 3840)),
    "1:1": ((480, 480), (720, 720), (1080, 1080), (1440, 1440), (2160, 2160)),
}

#: How far short of a ladder rung a fit may fall and still be delivered AT that
#: rung.
#:
#: Providers hand back house sizes: 1904x1072 on a 16:9 order (multiples of
#: 16), 1280x718 where 1280x720 was meant. Both are inside 1%. The margin is
#: 5% because the next rung down the ladder is always at least 33% away, so
#: nothing can ever be ambiguous about which rung it is reaching for, and a
#: genuinely smaller render -- a 768-wide frame is 40% short of 720p -- is
#: never inflated and sold as something it is not.
SNAP_TO_LADDER_TOLERANCE = 0.05

TRUTHY = {"1", "true", "yes", "on"}

#: Tiers that require a plan to unlock. A 4K master costs a full extra encode
#: at four times the pixel count; it is a paid deliverable, not a checkbox.
PAID_TIERS = frozenset({"1440p", "4k"})

#: Plans allowed to order a PAID_TIER.
TIER_PLANS = frozenset({"pro"})


def normalize_tier(value: Optional[str]) -> str:
    """A tier name as this module spells it, or "" for anything unknown.

    Unknown values normalise to "" rather than to the default, so the caller
    can tell "they asked for nothing" apart from "they asked for something we
    do not have" -- only the second is worth a log line.
    """
    name = str(value or "").strip().lower()
    if name in DELIVERY_TIERS:
        return name
    # The spellings people actually type.
    alias = {
        "2160p": "4k",
        "uhd": "4k",
        "4K": "4k",
        "1080": "1080p",
        "hd": "1080p",
        "fhd": "1080p",
        "720": "720p",
        "2k": "1440p",
        "qhd": "1440p",
    }.get(name, "")
    return alias


def resolve_tier(requested: Optional[str] = "", plan: str = "") -> str:
    """Which tier this job delivers at.

    An explicit request wins, then MUSEFORGE_DELIVERY_TIER, then the default.
    A paid tier asked for by a plan that does not carry it falls back to the
    default rather than erroring: the drama still ships, at the size the plan
    bought, which is the same way music and dialogue already degrade.
    """
    tier = normalize_tier(requested) or normalize_tier(
        os.environ.get("MUSEFORGE_DELIVERY_TIER")
    ) or DEFAULT_TIER
    if tier in PAID_TIERS and plan and plan.strip().lower() not in TIER_PLANS:
        return DEFAULT_TIER
    return tier


def ladder_for(aspect_ratio: str) -> Tuple[Tuple[int, int], ...]:
    """The rungs available for a ratio, smallest first. () when we do not
    deliver that ratio at all."""
    return DELIVERY_LADDER.get((aspect_ratio or "").strip(), ())


def tier_size(aspect_ratio: str, tier: str = "") -> Optional[Tuple[int, int]]:
    """The canonical size of one tier in one ratio, or None for a ratio we do
    not deliver."""
    rungs = ladder_for(aspect_ratio)
    if not rungs:
        return None
    name = normalize_tier(tier) or DEFAULT_TIER
    return rungs[DELIVERY_TIERS.index(name)]


def _nearest_even(value: float) -> int:
    """Round a pixel dimension to the NEAREST even number.

    The derived side of a crop is fractional almost every time (9:16 out of a
    1080-tall master wants 607.5px). Flooring it always biases the shape the
    same way and doubles the ratio error it costs: 606x1080 is 0.25% off 9:16
    where 608x1080 is 0.09% off.
    """
    return max(2, int(round(value / 2)) * 2)


def _even_down(value: float) -> int:
    """Round DOWN to even -- for the binding side of a fit, where rounding up
    would ask for pixels the source does not have."""
    return max(2, int(value) // 2 * 2)


def snap_to_ladder(
    width: int,
    height: int,
    aspect_ratio: str,
    ceiling: Optional[Tuple[int, int]] = None,
) -> Tuple[int, int]:
    """Round a fitted size up to a standard delivery size when it is close.

    Returns the input untouched when no rung is within
    SNAP_TO_LADDER_TOLERANCE, when the only candidate is above ``ceiling``, or
    for a ratio with no ladder. The smallest qualifying rung wins: a fit that
    is somehow within tolerance of two rungs is reaching for the nearer one.
    """
    rungs = ladder_for(aspect_ratio)
    if not rungs or width <= 0 or height <= 0:
        return width, height
    limit = 1.0 + SNAP_TO_LADDER_TOLERANCE
    for rung_w, rung_h in rungs:
        if ceiling and (rung_w > ceiling[0] or rung_h > ceiling[1]):
            continue
        if rung_w < width or rung_h < height:
            # Below the fit: snapping here would DISCARD generated pixels.
            continue
        if rung_w <= width * limit and rung_h <= height * limit:
            return rung_w, rung_h
    return width, height


@dataclass(frozen=True)
class Delivery:
    """The size a master ships at, and how honestly it got there."""

    width: int
    height: int
    aspect_ratio: str
    tier: str
    #: True when the delivered frame is larger than what was generated, i.e.
    #: the pixels were invented by a scaler. Recorded on the job result so a
    #: "4K" file can always be traced back to the size it was really rendered
    #: at.
    upscaled: bool = False
    #: What the provider actually handed back, before any of this.
    source_width: int = 0
    source_height: int = 0

    @property
    def size(self) -> Tuple[int, int]:
        return self.width, self.height

    def as_dict(self) -> Dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
            "tier": self.tier,
            "upscaled": self.upscaled,
            "rendered_width": self.source_width,
            "rendered_height": self.source_height,
        }


def plan_delivery(
    source_width: int,
    source_height: int,
    aspect_ratio: str,
    tier: str = "",
    force: bool = False,
) -> Optional[Delivery]:
    """The full delivery decision for one master.

    ``force`` (the exact-resolution switch, or any tier a customer asked for
    above what was rendered) delivers the tier's canonical size whatever the
    source measures. Otherwise the largest correctly-shaped rectangle that fits
    inside the source is used, capped at the tier and snapped up to a standard
    rung when it is within a hair of one.

    Returns None for a ratio we do not deliver, which leaves the video
    untouched -- the same answer this pipeline has always given.
    """
    name = normalize_tier(tier) or DEFAULT_TIER
    ceiling = tier_size(aspect_ratio, name)
    if not ceiling:
        return None
    ceiling_w, ceiling_h = ceiling

    def _delivery(width: int, height: int) -> Delivery:
        return Delivery(
            width=width,
            height=height,
            aspect_ratio=(aspect_ratio or "").strip(),
            tier=name,
            # Either axis growing MATERIALLY means a scaler invented pixels.
            # The ladder snap is deliberately not counted: rounding 1276x718
            # up to 1280x720 adds 0.3% of width that nobody can see and is not
            # what "upscaled" is warning anyone about. A tier above the render
            # adds 33% or more, and that is.
            upscaled=bool(
                source_width > 0
                and source_height > 0
                and (
                    width > source_width * (1.0 + SNAP_TO_LADDER_TOLERANCE)
                    or height > source_height * (1.0 + SNAP_TO_LADDER_TOLERANCE)
                )
            ),
            source_width=int(max(0, source_width)),
            source_height=int(max(0, source_height)),
        )

    if source_width <= 0 or source_height <= 0 or force:
        return _delivery(ceiling_w, ceiling_h)

    # A tier ABOVE what was rendered is a promise, not a ceiling: nobody
    # ordering a 4K master wants a 1080p file that merely respects 4K as an
    # upper bound. The upscale is real, it is recorded, and it is the only
    # thing anyone in this market can do -- no video model here renders 4K.
    #
    # The DEFAULT tier is exempt, and that exemption is the whole no-upscaling
    # rule: a 768x1344 render on an ordinary job ships at 756x1344 and is not
    # inflated to 1080x1920 and sold as vertical HD. Upscaling is something a
    # customer orders, never something a job discovers.
    if name != DEFAULT_TIER and ceiling_w > source_width and ceiling_h > source_height:
        if DELIVERY_TIERS.index(name) > _tier_index_of(
            source_width, source_height, aspect_ratio
        ):
            return _delivery(ceiling_w, ceiling_h)

    ratio = ceiling_w / ceiling_h
    if source_width / source_height > ratio:
        # Source is wider than the target: height is the binding constraint.
        height = float(source_height)
        width = height * ratio
        fitted = (_nearest_even(width), _even_down(height))
    else:
        width = float(source_width)
        height = width / ratio
        fitted = (_even_down(width), _nearest_even(height))
    if fitted[0] > ceiling_w or fitted[1] > ceiling_h:
        fitted = (ceiling_w, ceiling_h)

    width, height = snap_to_ladder(fitted[0], fitted[1], aspect_ratio, ceiling)
    return _delivery(width, height)


def _tier_index_of(width: int, height: int, aspect_ratio: str) -> int:
    """Which tier the SOURCE already is, as an index into DELIVERY_TIERS.

    Used to tell "they ordered a bigger file than we rendered" (an upscale
    they asked for) apart from "they ordered 1080p and the render is 1080p-ish"
    (the ladder snap, which is not a tier change). A source below every rung
    reads as -1, so any named tier counts as above it.
    """
    rungs = ladder_for(aspect_ratio)
    limit = 1.0 + SNAP_TO_LADDER_TOLERANCE
    index = -1
    for i, (rung_w, rung_h) in enumerate(rungs):
        if rung_w <= width * limit and rung_h <= height * limit:
            index = i
    return index


def scale_suffix(upscaled: bool) -> str:
    """The scaler clause appended to an ffmpeg ``scale=`` filter, if any.

    lanczos on the way UP: ffmpeg's default (bicubic) softens an upscale
    exactly where an upscale has the least detail to spare, and a 4K tier is
    four times the pixels of the render it came from.

    Nothing at all on the way down, deliberately. A downscale is what this
    pipeline has always done and ffmpeg's default is both fast and perfectly
    good at it -- naming a scaler there would change the bytes of every
    existing delivery to say the same thing it already said.
    """
    return ":flags=lanczos" if upscaled else ""


def is_exact_resolution_enabled() -> bool:
    """Force delivery at exactly the tier's canonical size, upscaling when the
    provider returned something smaller.

    OFF by default: upscaling invents no detail, it only spends bitrate to
    claim a resolution the pixels do not have. Turn on when a distributor
    demands literal 1080x1920 files. Ordering a tier above the render does the
    same thing for one job; this does it for every job.
    """
    return os.environ.get("MUSEFORGE_EXACT_RESOLUTION", "").strip().lower() in TRUTHY


def describe(delivery: Optional[Delivery]) -> str:
    """One line for the log: what shipped, and whether it was real."""
    if not delivery:
        return "untouched"
    provenance = (
        f" (upscaled from {delivery.source_width}x{delivery.source_height})"
        if delivery.upscaled
        else ""
    )
    return f"{delivery.width}x{delivery.height} {delivery.tier}{provenance}"
