"""Pick which MuAPI video model animates a given shot, with a fallback chain.

Every shot used to go to exactly one endpoint (Pro or Standard, decided by
the paying plan alone), and a shot whose endpoint failed took the whole scene
down with it. Two separate problems with that:

1. A locked-off insert of a teacup and a hand-held chase both got the same
   model, even though they fail in completely different ways -- motion
   coherence matters for one, texture fidelity for the other.
2. One 4xx/5xx from a single endpoint failed a paid job outright.

This module answers both with an ORDERED chain of endpoints per shot. The
chain's first entry is the specialist for that shot's profile (when one is
configured) and its last entry is always the Standard endpoint, which is the
one MuAPI model we know is always present.

Nothing changes by default: with no routing env set, every profile resolves to
the same plan-based endpoint the pipeline has always used, and the chain
degrades to [plan endpoint, standard]. Pointing a profile at a different MuAPI
model is a one-line env change once its slug is confirmed in the playground --
no code deploy:

    MUAPI_VIDEO_MODEL_ACTION=<muapi-slug>         # fast motion, chases, fights
    MUAPI_VIDEO_MODEL_DIALOGUE=<muapi-slug>       # faces talking, lip detail
    MUAPI_VIDEO_MODEL_ESTABLISHING=<muapi-slug>   # empty sets, landscapes, inserts
"""

import os
from typing import List, Optional

#: Shot profiles. Deliberately few -- a taxonomy nobody can classify
#: reliably is worse than no taxonomy, because it routes shots at random.
ACTION = "action"
DIALOGUE = "dialogue"
ESTABLISHING = "establishing"
STANDARD = "standard"

_ENV_BY_PROFILE = {
    ACTION: "MUAPI_VIDEO_MODEL_ACTION",
    DIALOGUE: "MUAPI_VIDEO_MODEL_DIALOGUE",
    ESTABLISHING: "MUAPI_VIDEO_MODEL_ESTABLISHING",
}

#: Words that mean "the picture moves a lot". Matched against the shot's
#: motion/camera description, which is where the storyboard agent puts them.
_ACTION_WORDS = (
    "run", "runs", "running", "chase", "chases", "fight", "fights", "punch",
    "sprint", "leap", "leaps", "jump", "jumps", "crash", "explode", "explosion",
    "fall", "falls", "throw", "throws", "grab", "grabs", "slam", "slams",
    "whip pan", "whip-pan", "handheld", "hand-held", "shake", "shaky",
    "fast", "rapid", "sudden", "violent", "struggle", "flee", "escape",
)

#: Camera moves that are themselves the motion, regardless of the subject.
_ACTION_CAMERA = ("whip pan", "whip-pan", "crash zoom", "handheld", "hand-held", "tracking")

#: A shot with nobody in it. Establishing plates and inserts are cheap to
#: animate and forgiving about faces, so they are the natural place to send a
#: different (or cheaper) model.
_ESTABLISHING_WORDS = (
    "establishing", "wide shot", "extreme wide", "aerial", "landscape",
    "empty", "insert", "close-up on the", "detail of", "skyline", "exterior",
)

#: Tension at or above this reads as an action beat even when the wording is calm.
ACTION_TENSION = 8


def classify_shot(
    motion_desc: str = "",
    visual_desc: str = "",
    camera_movement: str = "",
    shot_type: str = "",
    has_dialogue: bool = False,
    scene_tension: int = 0,
    has_character: bool = True,
) -> str:
    """Label a shot so :func:`model_chain` can route it.

    Order matters. Dialogue wins over everything because a talking face is
    the one thing an audience watches frame by frame, and it is also what a
    later lip-sync pass has to work with -- routing it by motion instead
    would trade the most scrutinised pixels in the film for camera dynamics
    nobody notices.
    """
    text = " ".join(
        part.lower() for part in (motion_desc, visual_desc, camera_movement, shot_type) if part
    )

    if has_dialogue and has_character:
        return DIALOGUE

    camera = (camera_movement or "").lower()
    if int(scene_tension or 0) >= ACTION_TENSION:
        return ACTION
    if any(word in text for word in _ACTION_WORDS):
        return ACTION
    if any(word in camera for word in _ACTION_CAMERA):
        return ACTION

    if not has_character:
        return ESTABLISHING
    if any(word in text for word in _ESTABLISHING_WORDS):
        return ESTABLISHING

    return STANDARD


def configured_model(profile: str) -> Optional[str]:
    """The MuAPI slug an operator pinned to this profile, if any."""
    env = _ENV_BY_PROFILE.get(profile)
    if not env:
        return None
    return (os.environ.get(env, "") or "").strip() or None


def model_chain(profile: str, plan: str = "free") -> List[str]:
    """Ordered endpoints to try for this shot, best first, safest last.

    The plan endpoint always stays in the chain: a specialist model is a
    preference, not a replacement, so a paying customer whose routed model is
    unavailable still gets the Pro endpoint they paid for before anything
    drops to Standard.
    """
    # Imported here, not at module import time, so tests (and operators) can
    # override the endpoint env vars without import-order surprises.
    from tools.muapi_video_generator import STANDARD_ENDPOINT, endpoint_for_plan

    chain: List[str] = []
    for candidate in (configured_model(profile), endpoint_for_plan(plan), STANDARD_ENDPOINT):
        if candidate and candidate not in chain:
            chain.append(candidate)
    return chain


def is_routing_active() -> bool:
    """True when at least one profile is pinned to a non-default model.

    Only used for logging/telemetry: it distinguishes "routing ran and chose
    the usual endpoint" from "routing is not configured at all", which is
    otherwise indistinguishable in the logs.
    """
    return any(configured_model(profile) for profile in _ENV_BY_PROFILE)
