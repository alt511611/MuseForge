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

from tools.falai_common import fal_generate, make_fal_client

DEMO_MUSIC_URL = ""

MIN_DURATION_SECONDS = 5
# ElevenLabs allows 600 s, Beatoven 150; a micro-drama is under a minute either way.
MAX_DURATION_SECONDS = 150


def _clamp_duration(seconds) -> int:
    try:
        value = int(round(float(seconds)))
    except (TypeError, ValueError):
        value = 30
    return max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, value))


#: ElevenLabs Music v2.5 through fal: one fal bill, and the model that scores
#: with the best production quality of what fal lists for music. Beatoven stays
#: one environment variable away (FALAI_MUSIC_MODEL=beatoven/music-generation).
DEFAULT_ENDPOINT = "elevenlabs/music/v2.5"


def _endpoint() -> str:
    return os.environ.get("FALAI_MUSIC_MODEL", "").strip() or DEFAULT_ENDPOINT


def _payload(endpoint: str, prompt: str, duration: int) -> dict:
    """The request body in the shape THIS endpoint takes.

    The two families share nothing but ``prompt``: Beatoven wants seconds and a
    negative prompt, ElevenLabs wants milliseconds and a flag that guarantees no
    vocals (its prompt field has no negative form -- and a prompt that says "no
    vocals" is a hint, not a guarantee).
    """
    if "elevenlabs/music" in endpoint:
        return {
            "prompt": prompt,
            "music_length_ms": duration * 1000,
            "force_instrumental": True,
            "output_format": "mp3_44100_128",
        }
    return {
        "prompt": prompt,
        "duration": duration,
        "negative_prompt": "vocals, lyrics, singing, speech, noise, distortion",
    }


class FalAIMusicGenerator:
    @property
    def ENDPOINT(self) -> str:
        return _endpoint()

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        self.client = make_fal_client(self.api_key, demo=demo)

    async def generate_instrumental(
        self,
        mood: str,
        duration: int = 30,
        style_hint: str = "",
    ) -> str:
        if self.demo:
            return DEMO_MUSIC_URL

        hint = f"{style_hint.strip()} " if (style_hint or "").strip() else ""
        prompt = (
            f"Instrumental background music, {mood} mood, cinematic, "
            f"{hint}no vocals, no lyrics."
        )
        endpoint = self.ENDPOINT
        payload = _payload(endpoint, prompt, _clamp_duration(duration))
        result = await fal_generate(self.client, endpoint, payload)
        audio_url = ((result or {}).get("audio") or {}).get("url")
        if not audio_url:
            raise RuntimeError(
                f"fal.ai music ({endpoint}) completed but no audio URL: {result}"
            )
        return audio_url
