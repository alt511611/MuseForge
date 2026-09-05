"""Foley via fal.ai — optional alternative to MuAPISFXGenerator.

Selected via MUSEFORGE_SFX_PROVIDER=falai (default remains "muapi").

WHY THIS EXISTS. Foley was the last stage with no fal.ai backend, which meant
a deployment that had moved video, images, music and lip sync across still had
to hold a MUAPI_KEY for one cent a scene. A key kept alive for a single cheap
call is not a saving, it is a second vendor's outage, a second billing account
and a second set of error shapes in the logs.

The model is the SAME one the MuAPI path already uses -- MMAudio v2 -- so this
is a change of route, not of sound. Schema CONFIRMED against fal.ai's own
OpenAPI for ``fal-ai/mmaudio-v2/text-to-audio``
(https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=fal-ai/mmaudio-v2/text-to-audio):

    input:  prompt (str, required),
            duration (number, 1..30, default 8),
            negative_prompt (str, default ""),
            num_steps (int, 4..50, default 25),
            cfg_strength (number, 0..20, default 4.5),
            seed (int, optional)
    output: {"audio": {"url": "...", ...}}

Note the ``fal-ai/`` prefix, which the MuAPI spelling of the same model does
not have (there it is the bare namespaced ``mmaudio-v2/text-to-audio``). The
two constants are deliberately separate: one is not a default for the other.

The prompt and the duration clamp are IMPORTED from the MuAPI module rather
than restated. They are properties of the model, not of the route to it, and
two copies would eventually disagree about what foley is allowed to contain --
at which point one provider would quietly start generating music under the
score.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from tools.falai_common import fal_generate, make_fal_client

# Provider-neutral, defined once with the default backend. See module docstring.
from tools.muapi_sfx_generator import (  # noqa: F401
    MAX_DURATION_SECONDS,
    MIN_DURATION_SECONDS,
    build_prompt,
    clamp_duration,
    is_foley_enabled,
)

#: fal's own id for MMAudio v2, prefixed. Confirmed against the OpenAPI
#: ``x-fal-metadata.endpointId``; the unprefixed MuAPI spelling 404s here.
SFX_ENDPOINT = os.environ.get("FALAI_SFX_MODEL", "fal-ai/mmaudio-v2/text-to-audio")


class FalAISFXGenerator:
    """One sound bed per scene, from the shot's own audio note."""

    def __init__(self, api_key: str = "", demo: bool = False):
        self.demo = demo
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        self.client = make_fal_client(self.api_key, demo=demo)

    async def generate_scene_sfx(
        self,
        audio_desc: str,
        duration: float = 8.0,
        scene_emotion: str = "",
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        """URL of a sound bed for this scene, or "" in demo mode.

        Raises on failure, exactly like the MuAPI backend: the caller in
        idea2video._generate_foley already catches per scene and delivers the
        drama without that layer.
        """
        if self.demo:
            return ""

        payload = {
            "prompt": build_prompt(audio_desc, scene_emotion),
            "duration": clamp_duration(duration),
            # Stated rather than left to the model's own default: the prompt
            # says what the bed must contain in words, this says it in the
            # place the sampler actually reads.
            "negative_prompt": "music, score, strings, singing, speech, dialogue",
        }
        result = await fal_generate(
            self.client,
            SFX_ENDPOINT,
            payload,
            is_cancelled=is_cancelled,
        )
        audio_url = ((result or {}).get("audio") or {}).get("url")
        if not audio_url:
            raise RuntimeError(f"fal.ai MMAudio completed but no audio URL: {result}")
        return audio_url


__all__ = [
    "FalAISFXGenerator",
    "MAX_DURATION_SECONDS",
    "MIN_DURATION_SECONDS",
    "SFX_ENDPOINT",
    "build_prompt",
    "clamp_duration",
    "is_foley_enabled",
]
