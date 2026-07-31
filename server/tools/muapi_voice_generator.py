"""Optional, fail-open character dialogue generation via MuAPI.

Uses ElevenLabs text-to-dialogue v3: one request per scene with all lines
in a single ``inputs`` list (confirmed MuAPI playground schema).
"""

import hashlib
import logging
import os
from typing import Any, Callable, Dict, Iterable, List, Optional

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

    Voice IDs must match MuAPI's ``elevenlabs-text-to-dialogue-v3`` enum exactly
    (playground labels like ``George - Warm``).
    """

    VOICE_ENDPOINT = os.environ.get(
        "MUAPI_VOICE_MODEL", "elevenlabs-text-to-dialogue-v3"
    )
    # Stable subset from MuAPI's confirmed voice_id enum — gender/tone variety.
    SYSTEM_VOICE_IDS = (
        "George - Warm",
        "Sarah - Soft",
        "Brian - Deep, Resonant and Comforting",
        "Charlotte - Clear",
        "Callum - Husky Trickster",
        "Laura - Enthusiast, Quirky Attitude",
    )
    # Gender pools over the same enum, for description-aware casting: a
    # character described as a woman must not be voiced by "George - Warm".
    FEMALE_VOICE_IDS = (
        "Sarah - Soft",
        "Charlotte - Clear",
        "Laura - Enthusiast, Quirky Attitude",
    )
    MALE_VOICE_IDS = (
        "George - Warm",
        "Brian - Deep, Resonant and Comforting",
        "Callum - Husky Trickster",
    )

    # Case-insensitive WHOLE-WORD description keywords -> pool (substring
    # matching is a trap: "the" contains "he", "woman" contains "man").
    # Turkish terms included because scripts are frequently written in Turkish.
    _FEMALE_MARKERS = (
        "woman", "female", "girl", "mother", "mom", "mum", "daughter",
        "sister", "aunt", "grandmother", "wife", "lady", "she", "her",
        "kadın", "kadin", "anne", "kız", "kiz", "abla", "teyze", "hala",
        "babaanne", "anneanne", "gelin",
    )
    _MALE_MARKERS = (
        "man", "male", "boy", "father", "dad", "son", "brother", "uncle",
        "grandfather", "husband", "gentleman", "he", "his",
        "adam", "erkek", "baba", "oğul", "ogul", "oğlan", "oglan",
        "abi", "ağabey", "agabey", "amca", "dayı", "dayi", "dede", "damat",
    )

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)
        self._character_voices: Dict[str, str] = {}

    @classmethod
    def _infer_gender(cls, description: str) -> str:
        """"female" / "male" / "" from a visual description.

        Whole words only, earliest match wins (a description usually leads
        with the defining noun: "52-year-old woman, ...").
        """
        import re

        words = re.findall(r"[^\W\d_]+", (description or "").casefold(), re.UNICODE)
        female = set(cls._FEMALE_MARKERS)
        male = set(cls._MALE_MARKERS)
        for word in words:
            if word in female:
                return "female"
            if word in male:
                return "male"
        return ""

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
            "inputs": [
                {"text": row["line"], "voice_id": row["voice_id"]} for row in lines
            ],
            "stability": 0.5,
            "language": None,
        }
        try:
            audio_url = await self.client.generate(
                self.VOICE_ENDPOINT,
                payload,
                poll_interval=2.0,
                max_polls=120,
                is_cancelled=is_cancelled,
            )
        except Exception as exc:
            logger.warning(
                "Scene dialogue generation failed; continuing silently: %s",
                exc,
            )
            return []

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
