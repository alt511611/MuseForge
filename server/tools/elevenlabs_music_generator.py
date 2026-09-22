"""Instrumental background music straight from ElevenLabs, no reseller in between.

Why this exists. fal.ai hosts a copy of ElevenLabs Music too
(``fal-ai/elevenlabs/music``), but its own docs mark that endpoint as
deprecating December 17, 2026, and the migration targets it names --
``fal-ai/elevenlabs/music/v2`` and ``v2.5`` -- are marked Private on fal.ai
(gated access, not guaranteed available on any given account). Going direct
avoids both: this account's own ``model_id`` choice
(``music_v1``/``music_v2``/``music_v2_5``) is answerable to ElevenLabs' own
API lifecycle, not a reseller's hosting decision, and it reuses the same
ELEVENLABS_API_KEY already configured for dialogue
(tools/elevenlabs_voice_generator.py) -- no new vendor account needed.

Schema CONFIRMED against ElevenLabs' own docs
(https://elevenlabs.io/docs/api-reference/music/compose):
    POST https://api.elevenlabs.io/v1/music
    header: xi-api-key
    input:  prompt (str, optional, <=4100 chars),
            music_length_ms (int, 3000..600000),
            model_id (str, default "music_v1"),
            force_instrumental (bool),
            output_format (str)
    output: the raw audio file IN THE RESPONSE BODY -- unlike the dialogue
            endpoint (/text-to-dialogue/with-timestamps), which returns JSON
            with base64 audio, this one hands back bytes directly. Simpler:
            no base64 decode, just response.content.

Same public signature as MuAPIMusicGenerator/FalAIMusicGenerator.
generate_instrumental(mood, duration, style_hint). Errors raise (no silent
MuAPI fallback). Callers in idea2video already catch and continue without
music.
"""

from __future__ import annotations

import logging
import os
import tempfile

import httpx

from tools.elevenlabs_voice_generator import ElevenLabsError

logger = logging.getLogger(__name__)

#: Same var the voice module already reads, so one override covers both.
ELEVENLABS_BASE = os.environ.get("ELEVENLABS_BASE", "https://api.elevenlabs.io/v1")

#: Overridable because ElevenLabs is the one revising this without warning --
#: same reasoning as DIALOGUE_MODEL in the voice module.
MUSIC_MODEL = os.environ.get("ELEVENLABS_MUSIC_MODEL", "music_v1")

DEMO_MUSIC_URL = ""

#: ElevenLabs' own music_length_ms bounds (3000ms..600000ms), in seconds.
MIN_DURATION_SECONDS = 3
MAX_DURATION_SECONDS = 600


def _clamp_duration(seconds) -> int:
    try:
        value = int(round(float(seconds)))
    except (TypeError, ValueError):
        value = 30
    return max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, value))


class ElevenLabsMusicGenerator:
    def __init__(
        self,
        api_key: str = "",
        demo: bool = False,
        working_dir: str = "",
        timeout: float = 180.0,
    ):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self.demo = demo
        # The API hands back audio BYTES, not a URL -- same situation as
        # dialogue (elevenlabs_voice_generator.py), same fix: write it into
        # the job's own directory and let the path travel as the "url".
        self.working_dir = working_dir or tempfile.gettempdir()
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"xi-api-key": self.api_key, "Content-Type": "application/json"}

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
        payload = {
            "prompt": prompt,
            "music_length_ms": _clamp_duration(duration) * 1000,
            "model_id": MUSIC_MODEL,
            "force_instrumental": True,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{ELEVENLABS_BASE}/music", headers=self._headers(), json=payload
                )
                response.raise_for_status()
                raw = response.content
        except httpx.HTTPStatusError as exc:
            raise ElevenLabsError(self._describe(exc)) from exc
        except httpx.HTTPError as exc:
            raise ElevenLabsError(str(exc)) from exc

        if not raw:
            raise ElevenLabsError("No audio in response")
        return self._write_music(raw)

    def _write_music(self, raw: bytes) -> str:
        os.makedirs(self.working_dir, exist_ok=True)
        handle, path = tempfile.mkstemp(
            prefix="music_", suffix=".mp3", dir=self.working_dir
        )
        with os.fdopen(handle, "wb") as out:
            out.write(raw)
        return path

    @staticmethod
    def _describe(exc: Exception) -> str:
        """The provider's own sentence, not httpx's link to MDN."""
        response = getattr(exc, "response", None)
        if response is None:
            return str(exc)
        body = ""
        try:
            payload = response.json()
            detail = payload.get("detail", payload)
            if isinstance(detail, dict):
                body = str(detail.get("message") or detail)
            else:
                body = str(detail)
        except Exception:
            body = (getattr(response, "text", "") or "")[:500]
        return f"HTTP {response.status_code}: {body[:500]}"
