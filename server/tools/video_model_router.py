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

PICKING A SLUG: CHECK THE BILLING SHAPE, NOT THE HEADLINE PRICE. MuAPI's
catalogue mixes two models of charging, and for the short clips this pipeline
makes they rank in the opposite order to how they read:

    kling-v3.0-standard-image-to-video   $0.72  FLAT, up to 15 seconds
    veo3.1-lite-image-to-video           $0.30  FLAT
    ovi-image-to-video                   $0.20  FLAT
    kling-v3-turbo-standard-image-to-video  $0.112 PER SECOND
    seedance-2.5-image-to-video-480p        $0.17  PER SECOND

"Turbo" and "480p" sound like the budget options and are not: a 3-second
insert costs $0.34 on turbo and $0.51 on seedance-480p, against $0.30 for the
same shot on veo3.1-lite -- which also takes `last_image`, so it can carry an
acted end frame where turbo cannot (see _ENDPOINT_FIELDS). Verified against
muapi.ai/pricing on 2026-08-14; the full table lives in
tests/test_pricing_coherence.MUAPI_RATES, which pins the margin consequences.
"""

import os
from typing import List, Optional

#: Shot profiles. Deliberately few -- a taxonomy nobody can classify
#: reliably is worse than no taxonomy, because it routes shots at random.
ACTION = "action"
DIALOGUE = "dialogue"
ESTABLISHING = "establishing"
#: A two-second cutaway to the face that is listening. Its own profile because
#: it is the one shot whose economics differ from every other: it is short, it
#: is bought in ADDITION to the scene's master rather than instead of it, and
#: it is the only place a $0.30 endpoint is preferable to the $0.72 one.
REACTION = "reaction"
STANDARD = "standard"

_ENV_BY_PROFILE = {
    ACTION: "MUAPI_VIDEO_MODEL_ACTION",
    DIALOGUE: "MUAPI_VIDEO_MODEL_DIALOGUE",
    ESTABLISHING: "MUAPI_VIDEO_MODEL_ESTABLISHING",
    REACTION: "MUAPI_VIDEO_MODEL_REACTION",
}

#: The reaction profile is the one with a default, because it is the one whose
#: whole purpose is to cost less than the plan endpoint. Routing it to Kling
#: would mean paying $0.72 for two seconds of a face -- the same price as the
#: master, for a fraction of the film -- which is not a second angle, it is a
#: second full scene. veo3.1-lite is $0.30 flat and takes `last_image`, so the
#: acted peak still reaches it (turbo, the other cheap-sounding option, takes
#: neither the end frame nor a flat price).
#:
#: Overridable like any other profile; MUAPI_VIDEO_MODEL_REACTION wins.
DEFAULT_REACTION_MODEL = "veo3.1-lite-image-to-video"

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
    """The MuAPI slug for this profile: the operator's, else the default.

    Only REACTION has a default, and only because a reaction shot routed to
    the plan endpoint defeats its own purpose -- see DEFAULT_REACTION_MODEL.
    Every other profile still resolves to nothing unless configured, which is
    what keeps a deployment that sets no routing env identical to how it has
    always behaved.
    """
    env = _ENV_BY_PROFILE.get(profile)
    if not env:
        return None
    configured = (os.environ.get(env, "") or "").strip()
    if configured:
        return configured
    if profile == REACTION:
        return DEFAULT_REACTION_MODEL
    return None


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


#: What to send to an endpoint we have no schema for. MuAPI validates the
#: payload, so an unknown field is not ignored -- it comes back as a 422, which
#: this module's fallback chain then reads as "this endpoint does not exist"
#: and quietly demotes the shot to Standard. The routed model would never
#: actually run, and nothing in the logs would say why. `duration` is in the
#: default because nearly every i2v model in the catalogue takes it; the
#: handful that do not are listed in _NO_DURATION below.
DEFAULT_OPTIONAL_FIELDS = frozenset({"duration"})

#: Optional fields each endpoint is KNOWN to accept, read off the model's
#: schema in the MuAPI playground. Only fields this client actually sends are
#: listed -- an endpoint may well take `seed` or `resolution` too, but we have
#: nothing to put in them.
#:
#: Keep this in step with the playground when adding a model: getting it wrong
#: in the permissive direction (listing a field the model rejects) costs a
#: silent demotion to Standard, which is exactly what this map exists to stop.
_ENDPOINT_FIELDS = {
    # Kling v3.0 is the one family that takes an audio flag and an end frame.
    "kling-v3.0-pro-image-to-video": frozenset(
        {"duration", "generate_audio", "last_image"}
    ),
    "kling-v3.0-standard-image-to-video": frozenset(
        {"duration", "generate_audio", "last_image"}
    ),
    "kling-v3.0-4k-image-to-video": frozenset(
        {"duration", "generate_audio", "last_image"}
    ),
    # Turbo drops both: prompt, image_url and duration only.
    "kling-v3-turbo-pro-image-to-video": frozenset({"duration"}),
    "kling-v3-turbo-standard-image-to-video": frozenset({"duration"}),
    # Veo takes an end frame and an aspect ratio, but no audio flag (its audio
    # is always on). Its `duration` is a single-value enum -- see FIXED_DURATION.
    "veo3.1-image-to-video": frozenset({"duration", "last_image", "aspect_ratio"}),
    "veo3.1-fast-image-to-video": frozenset({"duration", "last_image", "aspect_ratio"}),
    "veo3.1-lite-image-to-video": frozenset({"duration", "last_image", "aspect_ratio"}),
    # Seedance takes an aspect ratio and a seed; no audio flag, no end frame.
    "seedance-2.5-image-to-video": frozenset({"duration", "aspect_ratio"}),
    "seedance-2.5-image-to-video-480p": frozenset({"duration", "aspect_ratio"}),
    "seedance-2-image-to-video": frozenset({"duration", "aspect_ratio"}),
}

#: Endpoints with NO duration field at all -- their clip length is fixed by the
#: model. Sending `duration` to one is a 422; not sending it means the shot
#: comes back at whatever length the model produces, which the second budget
#: (interfaces/second_budget) cannot then honour. Route to these only if you
#: are prepared for that.
_NO_DURATION = frozenset(
    {
        "minimax-hailuo-2.3-pro-i2v",
        "minimax-hailuo-2.3-standard-i2v",
        "minimax-hailuo-2.3-fast",
    }
)


#: Endpoints whose `duration` is a single-value ENUM rather than a range.
#:
#: Read off the model's own API Reference on muapi.ai (veo3.1-lite: "duration
#: int, Options: 8, Default: 8"), and the reason this map exists rather than a
#: comment: `clamp_duration` bounds a value to 3-15, which is right for Kling
#: and wrong here -- a scene budgeted at 6 or 10 seconds would be sent as 6 or
#: 10, rejected as a 422, read by the fallback chain as "this endpoint does not
#: exist" and silently demoted to Standard. A routed Veo would have been
#: configured, expected, billed for in planning, and never once actually run.
#:
#: A shot sent here comes back at the model's fixed length regardless of the
#: second budget (interfaces/second_budget), so the caller has to trim it --
#: which is exactly what a short reaction shot wants anyway.
FIXED_DURATION = {
    "veo3.1-image-to-video": 8,
    "veo3.1-fast-image-to-video": 8,
    "veo3.1-lite-image-to-video": 8,
}

#: Aspect ratios an endpoint actually accepts, where that is narrower than
#: what this product sells. Veo's enum is 16:9 and 9:16 only, so a square job
#: routed there is another silent demotion -- dropping the field lets the
#: model use its own default instead of failing the call.
SUPPORTED_ASPECT_RATIOS = {
    "veo3.1-image-to-video": frozenset({"16:9", "9:16"}),
    "veo3.1-fast-image-to-video": frozenset({"16:9", "9:16"}),
    "veo3.1-lite-image-to-video": frozenset({"16:9", "9:16"}),
}


def fixed_duration(endpoint: str) -> Optional[int]:
    """The only duration this endpoint accepts, or None when it takes a range."""
    return FIXED_DURATION.get((endpoint or "").strip())


def accepts_aspect_ratio(endpoint: str, aspect_ratio: str) -> bool:
    """Whether this endpoint's enum includes ``aspect_ratio``.

    True for every endpoint with no declared restriction, so an unknown model
    keeps the previous behaviour.
    """
    allowed = SUPPORTED_ASPECT_RATIOS.get((endpoint or "").strip())
    if not allowed:
        return True
    return (aspect_ratio or "").strip() in allowed


def optional_fields(endpoint: str) -> frozenset:
    """Which optional fields this endpoint accepts, beyond prompt + image_url."""
    endpoint = (endpoint or "").strip()
    if endpoint in _ENDPOINT_FIELDS:
        return _ENDPOINT_FIELDS[endpoint]
    if endpoint in _NO_DURATION:
        return frozenset()
    return DEFAULT_OPTIONAL_FIELDS


def is_routing_active() -> bool:
    """True when at least one profile is pinned to a non-default model.

    Only used for logging/telemetry: it distinguishes "routing ran and chose
    the usual endpoint" from "routing is not configured at all", which is
    otherwise indistinguishable in the logs.

    Reads the environment directly rather than through configured_model(),
    which now answers for the reaction profile whether or not an operator said
    anything -- routing "being active" is a question about configuration, and
    a built-in default is not configuration.
    """
    return any(
        (os.environ.get(env, "") or "").strip() for env in _ENV_BY_PROFILE.values()
    )
