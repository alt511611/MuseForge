"""Lighting continuity — the script supervisor's job, done deterministically.

The cast is locked to portraits and the set is locked to a plate, but the
LIGHT was still re-invented per shot: the same scene could be lit from the
left in one frame and from the right in the next, at a different hour. The eye
catches that instantly, and it is the single most common tell that a sequence
was not shot on one set in one session.

There is no model call here on purpose. The drama already fixes one
``setting_time_of_day``; a fixed hour implies a fixed sun (or fixed practicals
after dark), so the lighting plan is a pure function of the script. That makes
it free, and — more importantly — identical for every shot in the drama, which
is the entire point. A vision model asked per shot would answer slightly
differently each time, which is the problem, not the fix.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class LightingPlan:
    label: str
    #: Where the key light comes from. Fixed for the whole drama.
    key_direction: str
    #: Hard/soft, and what is doing the lighting.
    quality: str
    #: Warm/cool cast, in words a diffusion model responds to.
    temperature: str

    def as_clause(self) -> str:
        return (
            f"Lighting continuity (identical in every shot of this film): "
            f"key light {self.key_direction}; {self.quality}; {self.temperature}. "
            f"Do not change the light's direction, height or colour between "
            f"shots. "
        )


#: Matched on substrings of setting_time_of_day, longest key first so
#: "late afternoon" wins over "afternoon".
LIGHTING_PLANS: Dict[str, LightingPlan] = {
    "dawn": LightingPlan(
        label="Dawn",
        key_direction="low from camera left, raking across the room",
        quality="soft, hazy, long shadows",
        temperature="cool blue ambient with a thin warm rim",
    ),
    "sunrise": LightingPlan(
        label="Sunrise",
        key_direction="low from camera left, raking across the room",
        quality="soft, hazy, long shadows",
        temperature="cool blue ambient with a thin warm rim",
    ),
    "early morning": LightingPlan(
        label="Early morning",
        key_direction="low from camera left through a window",
        quality="soft directional daylight, visible shafts, long shadows",
        temperature="pale warm gold against cool shadow",
    ),
    "morning": LightingPlan(
        label="Morning",
        key_direction="from camera left through a window",
        quality="clean directional daylight, medium-length shadows",
        temperature="neutral daylight, faintly warm",
    ),
    "midday": LightingPlan(
        label="Midday",
        key_direction="high and near-overhead",
        quality="hard, short shadows directly under the subject",
        temperature="neutral white, high contrast",
    ),
    "noon": LightingPlan(
        label="Noon",
        key_direction="high and near-overhead",
        quality="hard, short shadows directly under the subject",
        temperature="neutral white, high contrast",
    ),
    "late afternoon": LightingPlan(
        label="Late afternoon",
        key_direction="low from camera right",
        quality="warm directional daylight, long soft shadows",
        temperature="golden, warm highlights against cool fill",
    ),
    "afternoon": LightingPlan(
        label="Afternoon",
        key_direction="from camera right, above eye height",
        quality="directional daylight, defined shadows",
        temperature="neutral, slightly warm",
    ),
    "golden hour": LightingPlan(
        label="Golden hour",
        key_direction="very low from camera right, near-backlight",
        quality="soft, glowing, very long shadows and visible haze",
        temperature="deep gold key, cool blue shadow",
    ),
    "sunset": LightingPlan(
        label="Sunset",
        key_direction="very low from camera right, near-backlight",
        quality="soft, glowing, very long shadows and visible haze",
        temperature="deep gold key, cool blue shadow",
    ),
    "dusk": LightingPlan(
        label="Dusk",
        key_direction="ambient from the sky, no single hard source",
        quality="soft and flat, shadows nearly gone",
        temperature="cool blue ambient with warm practicals coming on",
    ),
    "evening": LightingPlan(
        label="Evening",
        key_direction="from warm practical lamps inside the room",
        quality="soft pools of light, darkness between them",
        temperature="warm tungsten key, deep cool shadow",
    ),
    "night": LightingPlan(
        label="Night",
        key_direction="from warm practical lamps inside the room, plus cool "
        "moonlight through the windows",
        quality="low key, strong falloff, faces lit from one side only",
        temperature="warm tungsten key against cool blue moonlight",
    ),
}

#: Used when the script names a time of day nothing here recognises, or names
#: none at all. Deliberately a real plan rather than "no clause": an unstated
#: lighting setup is exactly the drift this module exists to stop.
DEFAULT_PLAN = LightingPlan(
    label="Unspecified",
    key_direction="from camera left, slightly above eye height",
    quality="soft directional key with gentle fill on the shadow side",
    temperature="neutral, faintly warm",
)


def resolve_lighting(setting_time_of_day: str = "") -> LightingPlan:
    """Pick one lighting plan for the whole drama from its locked hour."""
    text = (setting_time_of_day or "").strip().lower()
    if not text:
        return DEFAULT_PLAN
    # Longest key first: "late afternoon" and "early morning" must beat their
    # own substrings ("afternoon", "morning").
    for key in sorted(LIGHTING_PLANS, key=len, reverse=True):
        if key in text:
            return LIGHTING_PLANS[key]
    return DEFAULT_PLAN
