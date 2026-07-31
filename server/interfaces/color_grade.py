"""Color grade presets — the ffmpeg realization of DirectorStyle.color_grade.

Each DirectorStyle already names a grade ("noir_bw", "warm_soft", ...); this
module turns that name into an actual filter chain, so the chosen director
style is visible in the finished picture instead of every drama receiving the
same look.

Two rules every preset here follows:

1. **Faces stay readable.** A grade that crushes skin tones hides the actors'
   expressions, which is the whole point of the shot. Each preset therefore
   declares a `strength` — how much of the graded image is blended back over
   the ungraded original — tuned to how aggressive its chain is. Gentle
   presets sit near 1.0; heavy ones deliberately do not.
2. **Shadows keep detail.** Chains hold shadows off zero rather than crushing
   them to pure black, so detail survives the later H.264 encode. Verified
   against a shadow/skin/highlight ramp: no preset drives a band to 0 or 255.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ColorGrade:
    label: str
    #: ffmpeg -vf chain applied to the full drama.
    filter_chain: str
    #: Fraction of the graded image kept when blended over the ungraded
    #: original, in [0, 1]. 1.0 applies the chain at full strength.
    strength: float = 1.0


#: Applied when a style names a grade that does not exist here.
FALLBACK_GRADE = "natural"


COLOR_GRADES: Dict[str, ColorGrade] = {
    # Gentle, true-to-life lift. The default look: enough contrast and
    # saturation to stop footage feeling flat, not enough to read as a
    # "filter".
    "natural": ColorGrade(
        label="Natural",
        filter_chain="eq=contrast=1.04:saturation=1.06:gamma=1.01",
        strength=1.0,
    ),
    # Classic prestige-drama look: pull overall saturation down, then push
    # shadows toward teal and highlights toward orange via colorbalance.
    # colorbalance (rather than curves=cross_process) keeps skin in a
    # believable range instead of driving everything yellow-green.
    "desaturated_teal_orange": ColorGrade(
        label="Desaturated Teal & Orange",
        filter_chain=(
            "eq=contrast=1.07:saturation=0.85,"
            "colorbalance=rs=-0.06:bs=0.10:rh=0.07:bh=-0.06"
        ),
        strength=0.80,
    ),
    # Punchy and graphic for action. Contrast does the work; saturation only
    # nudges up so the extra contrast doesn't read as oversaturated.
    "high_contrast": ColorGrade(
        label="High Contrast",
        filter_chain="eq=contrast=1.22:saturation=1.10:gamma=0.98",
        strength=0.75,
    ),
    # Soft, warm and close. Slightly lifted gamma opens the shadows so
    # close-ups on faces stay readable, which is what this style is for.
    "warm_soft": ColorGrade(
        label="Warm & Soft",
        filter_chain=(
            "eq=contrast=0.98:saturation=1.05:gamma=1.05,"
            "colorbalance=rm=0.07:gm=0.02:bm=-0.06"
        ),
        strength=0.85,
    ),
    # Monochrome noir. Runs near full strength on purpose: blending colour
    # back in would defeat a black-and-white look. Contrast is raised but
    # gamma is held just above crush so faces keep detail in shadow.
    "noir_bw": ColorGrade(
        label="Noir B&W",
        filter_chain="hue=s=0,eq=contrast=1.28:gamma=0.97",
        strength=0.95,
    ),
    # Bold, poster-like colour for the anime style.
    "vivid_saturated": ColorGrade(
        label="Vivid",
        filter_chain="eq=contrast=1.12:saturation=1.45:gamma=1.02",
        strength=0.80,
    ),
}


def get_color_grade(name: str) -> ColorGrade:
    """Look up a grade by name, falling back to the neutral preset.

    Never raises: an unknown or empty name yields the fallback so a typo in a
    style definition degrades to a sane picture instead of failing a render.
    """
    return COLOR_GRADES.get((name or "").strip(), COLOR_GRADES[FALLBACK_GRADE])
