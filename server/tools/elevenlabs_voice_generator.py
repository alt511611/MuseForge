"""Character dialogue straight from ElevenLabs, no reseller in between.

Why this exists. The same feature runs through MuAPI's
``elevenlabs-text-to-dialogue-v3``, and that endpoint refuses the voices its
own playground publishes. Delivered logs, one drama, every spelling tried::

    Invalid voice parameter: XB0fDUnXU5powFXDhCwa   (its id)
    Invalid voice parameter: Charlotte - Clear      (its published label)
    Invalid voice parameter: Charlotte              (its name)

``XB0fDUnXU5powFXDhCwa`` is on the list that endpoint's own model page offers.
No cast we pick can satisfy a validator that rejects its own catalogue, so the
reseller is the thing to remove.

Three things get better by going direct, and only the first is about money:

  * VOICES ARE ENUMERABLE. ``GET /v1/voices`` answers what this account may
    use. Every voice failure in this product's history came from guessing at a
    list nobody published; that guessing ends here (see ``list_voices``).
  * TIMINGS ARE REAL. ``/v1/text-to-dialogue/with-timestamps`` returns a
    ``voice_segments`` entry per input with ``start_time_seconds`` and
    ``end_time_seconds``. The SRT builder already prefers explicit
    ``start_seconds``/``end_seconds`` over its own word-count guesses, so
    captions stop being estimated the moment this path is on -- which is the
    entire class of bug behind cues running past their scene.
  * IT IS CHEAPER HERE. MuAPI bills $0.10 per generation whatever the length;
    ElevenLabs bills ~1 credit per character, and a micro-drama's scene is a
    couple of hundred characters. Roughly six times less for this shape of
    work. (The opposite is true of video, where a flat per-clip price beats
    per-second billing -- do not generalise this.)

Kept deliberately interface-compatible with MuAPIVoiceGenerator: same
``cast_characters`` / ``generate_scene_dialogue``, same track dicts, so the
pipeline neither knows nor cares which one it is holding.
"""

import base64
import binascii
import hashlib
import logging
import os
import tempfile
from typing import Any, Callable, Dict, Iterable, List, Optional

import httpx

from interfaces import gender as gender_of
from interfaces.language import DEFAULT_LANGUAGE, is_default, normalize

logger = logging.getLogger(__name__)

ELEVENLABS_BASE = os.environ.get(
    "ELEVENLABS_BASE", "https://api.elevenlabs.io/v1"
)

#: Model that has to support text-to-dialogue. Overridable because the id is
#: the one part of this that the provider revises without warning; ask
#: ``GET /v1/models`` when a 4xx names it.
DIALOGUE_MODEL = os.environ.get("ELEVENLABS_DIALOGUE_MODEL", "eleven_v3")


class ElevenLabsError(Exception):
    """Raised when ElevenLabs refuses a dialogue request."""


def _voices(env_name: str, default: tuple) -> tuple:
    raw = os.environ.get(env_name, "")
    values = tuple(v.strip() for v in raw.split(",") if v.strip())
    return values or default


def _estimate_line_duration_seconds(line: str) -> float:
    """Fallback only. This path normally gets measured timings instead."""
    words = max(1, len((line or "").split()))
    return max(1.2, min(8.0, words / 2.5))


class ElevenLabsVoiceGenerator:
    """Lock each character to one voice for the whole drama, then speak it."""

    #: ElevenLabs library voices. Unlike the reseller's, these are the
    #: provider's own long-standing public ids -- and ``list_voices`` can
    #: check them against the account rather than trusting this tuple.
    _GEORGE = "JBFqnCBsd6RMkjVDRZzb"
    _BRIAN = "nPczCjzI2devNBz1zQrb"
    _CALLUM = "N2lVS1w4EtoT3dr4eOWO"
    _SARAH = "EXAVITQu4vr4xnSDxMaL"
    _CHARLOTTE = "XB0fDUnXU5powFXDhCwa"
    _LAURA = "FGY2WhTYpPnrIDTdsKH5"

    SYSTEM_VOICE_IDS = _voices(
        "ELEVENLABS_VOICE_IDS",
        (_GEORGE, _SARAH, _BRIAN, _CHARLOTTE, _CALLUM, _LAURA),
    )
    FEMALE_VOICE_IDS = _voices(
        "ELEVENLABS_FEMALE_VOICE_IDS", (_SARAH, _CHARLOTTE, _LAURA)
    )
    MALE_VOICE_IDS = _voices(
        "ELEVENLABS_MALE_VOICE_IDS", (_GEORGE, _BRIAN, _CALLUM)
    )

    def __init__(
        self,
        api_key: str = "",
        demo: bool = False,
        working_dir: str = "",
        timeout: float = 180.0,
    ):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self.demo = demo
        # The API hands back audio BYTES, not a URL. The mixer opens whatever
        # is in `audio_url` with moviepy, which takes a local path perfectly
        # well, so the scene is written into the job's own directory and the
        # path travels in that field -- no upload, no second round trip.
        self.working_dir = working_dir or tempfile.gettempdir()
        self.timeout = timeout
        self._character_voices: Dict[str, str] = {}

    # --- casting (identical rules to the MuAPI path) ---------------------

    @classmethod
    def _infer_gender(cls, description: str) -> str:
        return gender_of.infer(description)

    def _assign(self, key: str, pool) -> str:
        used = set(self._character_voices.values())
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        start = int.from_bytes(digest[:4], "big") % len(pool)
        voice_id = pool[start]
        for offset in range(len(pool)):
            candidate = pool[(start + offset) % len(pool)]
            if candidate not in used:
                voice_id = candidate
                break
        self._character_voices[key] = voice_id
        return voice_id

    def cast_characters(self, characters: Iterable[Any]) -> Dict[str, str]:
        """Assign every named character a gender-matched voice up front."""
        for char in characters or []:
            name = str(getattr(char, "name", "") or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key in self._character_voices:
                continue
            description = str(
                getattr(char, "static_features", "")
                or getattr(char, "description", "")
                or ""
            )
            gender = self._infer_gender(f"{name} {description}")
            pool = (
                self.FEMALE_VOICE_IDS
                if gender == "female"
                else self.MALE_VOICE_IDS if gender == "male" else None
            )
            if pool is None:
                continue  # hash fallback assigns on the character's first line
            self._assign(key, pool)
        return dict(self._character_voices)

    def voice_id_for_character(self, character: str) -> str:
        key = (character or "Narrator").strip().casefold()
        if key in self._character_voices:
            return self._character_voices[key]
        return self._assign(key, self.SYSTEM_VOICE_IDS)

    def _parse_lines(self, dialogue: Iterable[Any]) -> List[Dict[str, str]]:
        lines: List[Dict[str, str]] = []
        for item in dialogue or []:
            if isinstance(item, dict):
                character = str(item.get("character", "Narrator"))
                line = str(item.get("line", ""))
            else:
                character = str(getattr(item, "character", "Narrator"))
                line = str(getattr(item, "line", ""))
            text = line.strip()
            if not text:
                continue
            lines.append(
                {
                    "character": character,
                    "line": text,
                    "voice_id": self.voice_id_for_character(character),
                }
            )
        return lines

    # --- the provider ----------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {"xi-api-key": self.api_key, "Content-Type": "application/json"}

    async def list_voices(self) -> List[Dict[str, str]]:
        """What this ACCOUNT may actually use, asked rather than assumed.

        The whole voice saga came from a provider that published no list. This
        one does, so a wrong id is a question with an answer instead of a
        drama that ships silent.
        """
        if not self.api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{ELEVENLABS_BASE}/voices", headers=self._headers()
            )
            response.raise_for_status()
            data = response.json()
        return [
            {"voice_id": v.get("voice_id", ""), "name": v.get("name", "")}
            for v in (data.get("voices") or [])
            if v.get("voice_id")
        ]

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

    def _write_scene_audio(self, audio_base64: str) -> str:
        raw = base64.b64decode(audio_base64, validate=True)
        os.makedirs(self.working_dir, exist_ok=True)
        handle, path = tempfile.mkstemp(
            prefix="dialogue_", suffix=".mp3", dir=self.working_dir
        )
        with os.fdopen(handle, "wb") as out:
            out.write(raw)
        return path

    async def generate_scene_dialogue(
        self,
        dialogue: Iterable[Any],
        is_cancelled: Optional[Callable[[], bool]] = None,
        language: str = DEFAULT_LANGUAGE,
    ) -> List[Dict[str, Any]]:
        """Speak a whole scene in one request, and keep the timings it returns.

        The combined audio path rides on the FIRST track only, so the mixer
        lays it down once; the rest are caption rows, exactly as on the MuAPI
        path. What is new is ``start_seconds``/``end_seconds`` per line, which
        the SRT builder honours as given -- so this path's captions are
        measured rather than guessed from the word count.
        """
        lines = self._parse_lines(dialogue)
        if not lines or self.demo:
            return []
        if not self.api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured")

        payload: Dict[str, Any] = {
            # `inputs`, not the reseller's `dialogue`: the wrapper renamed the
            # field, and sending the wrong one is a 422 before a note is sung.
            "inputs": [
                {"text": row["line"], "voice_id": row["voice_id"]} for row in lines
            ],
            "model_id": DIALOGUE_MODEL,
        }
        # Sent only for non-English, same reasoning as the MuAPI path: omitted
        # means auto-detect, which is right for English and unreliable on the
        # two-word lines a micro-drama is made of.
        if not is_default(language):
            payload["language_code"] = normalize(language)

        if is_cancelled and is_cancelled():
            raise ElevenLabsError("Job cancelled before dialogue generation")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{ELEVENLABS_BASE}/text-to-dialogue/with-timestamps",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise ElevenLabsError(self._describe(exc)) from exc
        except httpx.HTTPError as exc:
            raise ElevenLabsError(str(exc)) from exc

        audio_base64 = data.get("audio_base64") or ""
        if not audio_base64:
            raise ElevenLabsError(f"No audio in response (keys: {sorted(data)})")
        try:
            audio_path = self._write_scene_audio(audio_base64)
        except (binascii.Error, ValueError) as exc:
            raise ElevenLabsError(f"Audio was not valid base64: {exc}") from exc

        # voice_segments carries dialogue_input_index, so a line is matched to
        # its own timing rather than to its position in a list the provider
        # never promised to preserve.
        timings: Dict[int, Dict[str, float]] = {}
        for segment in data.get("voice_segments") or []:
            index = segment.get("dialogue_input_index")
            if not isinstance(index, int):
                continue
            start = segment.get("start_time_seconds")
            end = segment.get("end_time_seconds")
            if start is None or end is None:
                continue
            timings[index] = {"start": float(start), "end": float(end)}

        if not timings:
            logger.warning(
                "ElevenLabs returned no voice_segments; captions fall back to "
                "estimated timings for this scene."
            )

        tracks: List[Dict[str, Any]] = []
        for i, row in enumerate(lines):
            track: Dict[str, Any] = {
                "character": row["character"],
                "line": row["line"],
                "voice_id": row["voice_id"],
            }
            timing = timings.get(i)
            if timing and timing["end"] > timing["start"]:
                track["start_seconds"] = timing["start"]
                track["end_seconds"] = timing["end"]
                track["duration_seconds"] = timing["end"] - timing["start"]
            else:
                track["duration_seconds"] = _estimate_line_duration_seconds(
                    row["line"]
                )
            if i == 0:
                track["audio_url"] = audio_path
            tracks.append(track)
        return tracks
