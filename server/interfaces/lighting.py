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
from typing import Dict, Optional


@dataclass(frozen=True)
class LightingPlan:
    label: str
    #: Where the key light comes from INDOORS. Fixed for the whole drama.
    key_direction: str
    #: Hard/soft, and what is doing the lighting.
    quality: str
    #: Warm/cool cast, in words a diffusion model responds to.
    temperature: str
    #: Where it comes from when the drama is NOT in a room -- or when nothing
    #: in the script says it is. None where the answer does not change,
    #: which is every daylight hour: the key is the sun either way, and it
    #: does not enter through a window that the sentence has to name.
    open_key_direction: Optional[str] = None

    def as_clause(self, interior: Optional[bool] = None) -> str:
        """The clause for this hour, in a room or out of one.

        ``interior`` is True for a room, False for a street, and None when the
        script did not say. None reads as "not a room" on purpose: the plan
        only ever has to be RIGHT about where the key comes from, and a
        sentence that names no window is right in both places, while one that
        names a window is wrong in half of them.
        """
        direction = self.key_direction
        if interior is not True and self.open_key_direction:
            direction = self.open_key_direction
        # Tight on purpose: this is one of the first clauses the frame prompt
        # drops when it runs out of budget, and it is the one whose loss is
        # most visible -- a shot lit differently reads as a different film.
        # Delivered job 21e3d767-bce lost it from every frame and changes its
        # key light four times in thirty seconds. Both instructions survive
        # (identical in every shot; do not move it); the prose does not.
        return (
            f"Lighting continuity, identical in every shot: "
            f"key light {direction}; {self.quality}; {self.temperature}. "
            f"Do not change its direction, height or colour. "
        )


#: Matched on substrings of setting_time_of_day, longest key first so
#: "late afternoon" wins over "afternoon".
LIGHTING_PLANS: Dict[str, LightingPlan] = {
    "dawn": LightingPlan(
        label="Dawn",
        key_direction="low from camera left, raking across the room",
        open_key_direction="low from camera left, raking across the location",
        quality="soft, hazy, long shadows",
        temperature="cool blue ambient with a thin warm rim",
    ),
    "sunrise": LightingPlan(
        label="Sunrise",
        key_direction="low from camera left, raking across the room",
        open_key_direction="low from camera left, raking across the location",
        quality="soft, hazy, long shadows",
        temperature="cool blue ambient with a thin warm rim",
    ),
    "early morning": LightingPlan(
        label="Early morning",
        key_direction="low from camera left through a window",
        open_key_direction="low from camera left, the sun itself",
        quality="soft directional daylight, visible shafts, long shadows",
        temperature="pale warm gold against cool shadow",
    ),
    "morning": LightingPlan(
        label="Morning",
        key_direction="from camera left through a window",
        open_key_direction="from camera left, the sun itself",
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
        open_key_direction="from the location's own practical lights -- "
        "lamps, windows, signs, vehicles",
        quality="soft pools of light, darkness between them",
        temperature="warm tungsten key, deep cool shadow",
    ),
    "night": LightingPlan(
        label="Night",
        key_direction="from warm practical lamps inside the room, plus cool "
        "moonlight through the windows",
        open_key_direction="from the location's own lamps -- street, dock, "
        "vehicle -- with the night sky as cool fill",
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


#: Nouns that put a scene outdoors, and nouns that put it in a room. Neither
#: list tries to be a gazetteer -- they only have to separate the settings a
#: micro-drama actually names, and anything they do not recognise falls
#: through to "not stated", which asserts no window either way.
_OUTDOOR_WORDS = (
    "harbour", "harbor", "dock", "quay", "pier", "wharf", "marina",
    "street", "road", "avenue", "alley", "lane", "highway", "motorway",
    "yard", "courtyard", "car park", "parking lot", "forecourt",
    "rooftop", "roof", "terrace", "balcony", "garden", "park", "square",
    "field", "meadow", "hill", "mountain", "cliff", "valley", "desert",
    "forest", "woods", "jungle", "beach", "shore", "coast", "riverbank",
    "river", "canal", "towpath", "lakeside", "seafront", "promenade",
    "bridge", "runway", "airfield", "platform", "graveyard", "cemetery",
    "trench", "battlefield", "campsite", "clearing", "outdoors", "outside",
)
_INDOOR_WORDS = (
    "room", "kitchen", "bedroom", "bathroom", "living", "office", "study",
    "apartment", "flat", "corridor", "hallway", "stairwell", "lobby",
    "basement", "cellar", "attic", "loft", "garage", "shed", "cabin",
    "bar", "pub", "cafe", "café", "restaurant", "diner", "kitchenette",
    "hospital", "ward", "clinic", "surgery", "laboratory", "lab",
    "warehouse", "workshop", "factory floor", "classroom", "lecture",
    "courtroom", "cell", "chapel", "church", "temple", "library",
    "studio", "control room", "cockpit", "carriage", "cabin interior",
    "shop", "store", "hotel", "indoors", "inside",
)


def is_interior(setting_location: str = "") -> Optional[bool]:
    """True in a room, False out of one, None when the script did not say.

    Screenwriting answers this in the first three characters of a slug line,
    so INT./EXT. wins outright where it is present. Where it is not, the
    location's own nouns decide, and a location naming both ("the yard behind
    the workshop") is left as None rather than guessed at -- an unstated
    answer costs a slightly vaguer sentence, and a wrong one puts a window in
    a harbour.
    """
    text = (setting_location or "").strip().lower()
    if not text:
        return None
    head = text.lstrip("( ")
    if head.startswith("ext.") or head.startswith("ext ") or head.startswith("exterior"):
        return False
    if head.startswith("int.") or head.startswith("int ") or head.startswith("interior"):
        return True
    outdoor = any(word in text for word in _OUTDOOR_WORDS)
    indoor = any(word in text for word in _INDOOR_WORDS)
    if outdoor == indoor:
        return None
    return indoor


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
