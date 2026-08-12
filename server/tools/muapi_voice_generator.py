"""Optional, fail-open character dialogue generation via MuAPI.

Uses ElevenLabs text-to-dialogue v3: one request per scene with all lines
in a single ``dialogue`` list.

Schema CONFIRMED against MuAPI's own OpenAPI spec
(https://api.muapi.ai/openapi.json -> ElevenlabsTextToDialogueV3Request):

    {"dialogue": [{"text": str, "voice_id": str}, ...],
     "stability": float, "language_code": str}

Two details that are easy to get wrong and fail EVERY request when wrong:
  * the list field is ``dialogue`` -- ``inputs`` is not a declared field, so
    the endpoint rejected the whole body with a 422 before generating a note;
  * ``voice_id`` is a real ElevenLabs voice ID hash (the sibling
    ``elevenlabs-tts-turbo-2-5`` schema defaults it to ``21m00Tcm4TlvDq8ikWAM``),
    NOT a playground display label like "George - Warm".
"""

import hashlib
import logging
import os
from typing import Any, Callable, Dict, Iterable, List, Optional

from interfaces import gender as gender_of
from interfaces.language import DEFAULT_LANGUAGE, is_default, normalize
from tools.muapi_client import MuAPIClient

logger = logging.getLogger(__name__)

TRUTHY = {"1", "true", "yes", "on"}


def is_dialogue_enabled() -> bool:
    """Dialogue is opt-in because every spoken line makes a paid API call."""
    return os.environ.get("MUSEFORGE_DIALOGUE_ENABLED", "0").strip().lower() in TRUTHY


def _estimate_line_duration_seconds(line: str) -> float:
    """Rough spoken duration (~2.5 words/sec) when the API returns no timings."""
    words = max(1, len((line or "").split()))
    return max(1.2, min(8.0, words / 2.5))


class MuAPIVoiceGenerator:
    """Lock each character to one ElevenLabs dialogue voice for the whole drama.

    Voice IDs are ElevenLabs library voice IDs. The display names are kept in
    ``VOICE_NAMES`` for logs and debugging only -- sending a name where an ID
    belongs is what silenced every drama.
    """

    VOICE_ENDPOINT = os.environ.get(
        "MUAPI_VOICE_MODEL", "elevenlabs-text-to-dialogue-v3"
    )

    # ElevenLabs library voices, multilingual v2 -- gender/tone variety.
    _GEORGE = "JBFqnCBsd6RMkjVDRZzb"   # warm, male
    _BRIAN = "nPczCjzI2devNBz1zQrb"    # deep, resonant, male
    _CALLUM = "N2lVS1w4EtoT3dr4eOWO"   # husky, male
    _SARAH = "EXAVITQu4vr4xnSDxMaL"    # soft, female
    _CHARLOTTE = "XB0fDUnXU5powFXDhCwa"  # clear, female
    _LAURA = "FGY2WhTYpPnrIDTdsKH5"    # bright, female

    #: ID -> display name. Diagnostics only; never sent to the API.
    VOICE_NAMES = {
        _GEORGE: "George",
        _BRIAN: "Brian",
        _CALLUM: "Callum",
        _SARAH: "Sarah",
        _CHARLOTTE: "Charlotte",
        _LAURA: "Laura",
    }

    SYSTEM_VOICE_IDS = (_GEORGE, _SARAH, _BRIAN, _CHARLOTTE, _CALLUM, _LAURA)
    # Gender pools over the same voices, for description-aware casting: a
    # character described as a woman must not be voiced by George.
    FEMALE_VOICE_IDS = (_SARAH, _CHARLOTTE, _LAURA)
    MALE_VOICE_IDS = (_GEORGE, _BRIAN, _CALLUM)

    # The marker table lives in interfaces/gender.py: the screenwriter writes
    # the gender INTO the description, and this step reads it back out. Two
    # copies of the word list would let a character be written as a woman and
    # cast as a man.
    _FEMALE_MARKERS = gender_of.FEMALE_MARKERS
    _MALE_MARKERS = gender_of.MALE_MARKERS

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)
        self._character_voices: Dict[str, str] = {}

    @classmethod
    def _infer_gender(cls, description: str) -> str:
        """"female" / "male" / "" from a visual description."""
        return gender_of.infer(description)

    def cast_characters(self, characters: Iterable[Any]) -> Dict[str, str]:
        """Assign every named character a voice UP FRONT, matched to the
        gender implied by their visual description.

        Called once per drama before any dialogue is generated. Without this
        the per-line hash fallback picks from the full enum, which can voice
        a mother with "George - Warm" — instantly amateurish. Characters
        whose description implies no gender keep the hash-based fallback
        (still stable and collision-avoiding).
        """
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
                continue  # hash fallback assigns on first line, as before
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
        return dict(self._character_voices)

    def voice_id_for_character(self, character: str) -> str:
        """Return a stable voice ID, assigning it on the character's first line."""
        key = (character or "Narrator").strip().casefold()
        if key in self._character_voices:
            return self._character_voices[key]

        digest = hashlib.sha256(key.encode("utf-8")).digest()
        start = int.from_bytes(digest[:4], "big") % len(self.SYSTEM_VOICE_IDS)
        used = set(self._character_voices.values())
        voice_id = self.SYSTEM_VOICE_IDS[start]
        for offset in range(len(self.SYSTEM_VOICE_IDS)):
            candidate = self.SYSTEM_VOICE_IDS[(start + offset) % len(self.SYSTEM_VOICE_IDS)]
            if candidate not in used:
                voice_id = candidate
                break

        self._character_voices[key] = voice_id
        return voice_id

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
            voice_id = self.voice_id_for_character(character)
            lines.append(
                {
                    "character": character,
                    "line": text,
                    "voice_id": voice_id,
                }
            )
        return lines

    async def generate_scene_dialogue(
        self,
        dialogue: Iterable[Any],
        is_cancelled: Optional[Callable[[], bool]] = None,
        language: str = DEFAULT_LANGUAGE,
    ) -> List[Dict[str, Any]]:
        """Generate all non-empty scene lines in ONE ElevenLabs dialogue request.

        Returns per-line track metadata for captions. The combined audio URL
        (when the API returns a single file) is attached only to the first
        track so the mixer plays it once; later tracks are caption-only.
        """
        lines = self._parse_lines(dialogue)
        if not lines or self.demo:
            return []

        payload = {
            "dialogue": [
                {"text": row["line"], "voice_id": row["voice_id"]} for row in lines
            ],
            "stability": 0.5,
        }
        # The field is `language_code`, not `language` -- the old key was not a
        # field this endpoint declares, so it carried no hint at all and every
        # drama fell through to auto-detection. Auto-detect is fine on a
        # paragraph and unreliable on the two-word lines a micro-drama is made
        # of ("Söz."), where it can switch language mid-scene.
        #
        # Sent only for non-English: omitted means auto-detect, which is the
        # right behaviour for English and keeps the payload identical to what
        # the endpoint saw before for every existing job.
        #
        # No per-language voice table is needed to go with it: ElevenLabs v3
        # voices are multilingual, so the same cast speaks any supported
        # language once the code is passed.
        if not is_default(language):
            payload["language_code"] = normalize(language)
        try:
            audio_url = await self.client.generate(
                self.VOICE_ENDPOINT,
                payload,
                poll_interval=2.0,
                max_polls=120,
                is_cancelled=is_cancelled,
            )
        except Exception as exc:
            # Deliberately NOT swallowed here. Returning [] made a broken
            # request schema indistinguishable from a scene with no lines:
            # every drama shipped silent while the only trace was a warning
            # with no scene number. The caller (idea2video) still fails open
            # per scene -- it just gets to say WHICH scene and WHY.
            logger.error(
                "Scene dialogue generation failed (%s voice(s), %s line(s)): %s",
                len({row["voice_id"] for row in lines}),
                len(lines),
                exc,
            )
            raise

        if not audio_url:
            return []

        # Single combined audio file for the whole scene (confirmed typical
        # MuAPI outputs[0] shape). Per-line duration_seconds are fail-safe
        # estimates for SRT when the API does not return cue timings.
        tracks: List[Dict[str, Any]] = []
        for i, row in enumerate(lines):
            track: Dict[str, Any] = {
                "character": row["character"],
                "line": row["line"],
                "voice_id": row["voice_id"],
                "duration_seconds": _estimate_line_duration_seconds(row["line"]),
            }
            if i == 0:
                track["audio_url"] = audio_url
            tracks.append(track)
        return tracks
