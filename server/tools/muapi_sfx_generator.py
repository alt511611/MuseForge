"""Foley: the sound the picture is making, generated per scene.

A slap that makes no sound is not a slap. Sound effects are what tell an
audience that the thing on screen has weight — and their absence is a large
part of why generated video reads as generated, more than any amount of
grain or grading, because a viewer forgives a strange face far more readily
than a silent door.

This exists as generation rather than as a sample library on purpose. The
obvious build is to ship a folder of licensed wavs (slap.wav, glass.wav,
whoosh.wav) and map them by keyword, which costs a licence, a storage bill,
and a permanent maintenance job answering "which of these forty files is a
'tense room tone'". MuAPI's ``mmaudio-v2/text-to-audio`` answers that question
for **one cent a scene** (verified on muapi.ai/pricing), from a prompt this
pipeline has been writing and discarding since the day it was built:
``StoryboardShot.audio_desc``, filled in by the storyboard agent for every
shot and, until now, read by nothing.

Best-effort throughout, exactly like music: a scene whose foley fails is a
scene that plays with dialogue and score, which is what every scene did
before this module existed.

Schema CONFIRMED against MuAPI's own API reference
(https://muapi.ai/playground/mmaudio-v2-text-to-audio/api):

    POST /api/v1/mmaudio-v2/text-to-audio
        prompt   (str, required)
        duration (int, default 8, range 1-30)
"""

import logging
import os
from typing import Callable, Optional

from tools.muapi_client import MuAPIClient, MuAPIError

logger = logging.getLogger(__name__)

TRUTHY = {"1", "true", "yes", "on"}

#: Note the slash: this endpoint is namespaced, unlike the flat slugs used by
#: the image and video models. Getting it wrong is a 404 per scene.
SFX_ENDPOINT = os.environ.get("MUAPI_SFX_MODEL", "mmaudio-v2/text-to-audio")

#: The provider's own bounds. A request outside them is rejected, and the
#: rejection arrives per scene, so it is clamped here rather than trusted.
MIN_DURATION_SECONDS = 1
MAX_DURATION_SECONDS = 30


def is_foley_enabled() -> bool:
    """Whether scenes get a generated sound bed.

    OFF by default like every other paid step, but the cheapest thing this
    product can buy: $0.01 a scene, about a third of a percent of a scene's
    cost, against the single most audible difference between a drama and a
    slideshow with music over it.
    """
    return os.environ.get("MUSEFORGE_FOLEY", "").strip().lower() in TRUTHY


def clamp_duration(seconds) -> int:
    try:
        value = int(round(float(seconds)))
    except (TypeError, ValueError):
        value = 8
    return max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, value))


def build_prompt(audio_desc: str, scene_emotion: str = "") -> str:
    """Turn the storyboard's sound note into a request for a sound BED.

    Two things are stated that the shot's own note never is. First, no music:
    the score is generated separately and mixed underneath, and a foley track
    that arrives with its own strings fights it. Second, no speech: dialogue
    is recorded by the voice provider and timed to the frame, and a mumbling
    crowd underneath it is the fastest way to make a scene unintelligible.
    """
    desc = (audio_desc or "").strip().rstrip(".")
    if not desc:
        # The storyboard writes this field for every shot, but a legacy shot
        # or a template fallback may not have -- and a room with no sound at
        # all is still a room, so it gets one.
        desc = "quiet room tone, the space itself"
    mood = (scene_emotion or "").strip().rstrip(".")
    mood_clause = f" The mood of the moment is {mood}." if mood else ""
    return (
        f"Cinematic sound design and foley for a film scene: {desc}."
        f"{mood_clause} Diegetic sound only — the sounds the objects, bodies "
        f"and room in the shot actually make. Absolutely NO music, NO score, "
        f"NO singing and NO speech or dialogue."
    )


class MuAPISFXGenerator:
    """One sound bed per scene, from the shot's own audio note."""

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)

    async def generate_scene_sfx(
        self,
        audio_desc: str,
        duration: float = 8.0,
        scene_emotion: str = "",
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        """URL of a sound bed for this scene, or "" in demo mode.

        Raises MuAPIError on failure. Callers must catch and continue: foley
        is the layer a drama can most afford to lose.
        """
        if self.demo:
            return ""
        payload = {
            "prompt": build_prompt(audio_desc, scene_emotion),
            "duration": clamp_duration(duration),
        }
        return await self.client.generate(
            SFX_ENDPOINT,
            payload,
            poll_interval=2.0,
            max_polls=100,
            is_cancelled=is_cancelled,
        )


def make_sfx_generator(api_key: str, demo: bool = False) -> "MuAPISFXGenerator":
    return MuAPISFXGenerator(api_key, demo=demo)


__all__ = [
    "MuAPIError",
    "MuAPISFXGenerator",
    "SFX_ENDPOINT",
    "build_prompt",
    "clamp_duration",
    "is_foley_enabled",
    "make_sfx_generator",
]
