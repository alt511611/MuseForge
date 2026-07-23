"""fal.ai Beatoven music generation — optional alternative to MuAPIMusicGenerator.

Selected via MUSEFORGE_MUSIC_PROVIDER=falai (default remains "muapi").

Schema CONFIRMED against fal.ai's own OpenAPI for endpoint
``beatoven/music-generation``
(https://fal.ai/api/openapi/queue/openapi.json?endpoint_id=beatoven/music-generation
 and playground https://fal.ai/models/beatoven/music-generation):
    input:  prompt (str, required),
            duration (number, 5..150, default 90),
            refinement (int, 10..200, default 100),
            creativity (number, 1..20, default 16),
            negative_prompt (str, optional),
            seed (int, optional)
    output: {"audio": {"url": "...", ...}, "prompt": ..., "metadata": ...}

NOTE: the endpoint id is ``beatoven/music-generation`` (no ``fal-ai/`` prefix) —
confirmed via the OpenAPI ``x-fal-metadata.endpointId`` field. Do not invent
``fal-ai/beatoven/...``; that 404s.

Same public signature as MuAPIMusicGenerator.generate_instrumental(mood, duration).
Errors raise (no silent MuAPI fallback). Callers in idea2video already catch
and continue without music.
"""

from __future__ import annotations

import os
from typing import Optional

from tools.falai_common import fal_generate, make_fal_client

DEMO_MUSIC_URL = ""

MIN_DURATION_SECONDS = 5
MAX_DURATION_SECONDS = 150


def _clamp_duration(seconds) -> int:
    try:
        value = int(round(float(seconds)))
    except (TypeError, ValueError):
        value = 30
    return max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, value))


class FalAIMusicGenerator:
    ENDPOINT = os.environ.get("FALAI_MUSIC_MODEL", "beatoven/music-generation")

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        self.client = make_fal_client(self.api_key, demo=demo)

    async def generate_instrumental(
        self,
        mood: str,
        duration: int = 30,
    ) -> str:
        if self.demo:
            return DEMO_MUSIC_URL

        prompt = (
            f"Instrumental background music, {mood} mood, cinematic, "
            f"no vocals, no lyrics."
        )
        payload = {
            "prompt": prompt,
            "duration": _clamp_duration(duration),
            "negative_prompt": "vocals, lyrics, singing, speech, noise, distortion",
        }
        result = await fal_generate(self.client, self.ENDPOINT, payload)
        audio_url = ((result or {}).get("audio") or {}).get("url")
        if not audio_url:
            raise RuntimeError(
                f"fal.ai beatoven completed but no audio URL: {result}"
            )
        return audio_url
