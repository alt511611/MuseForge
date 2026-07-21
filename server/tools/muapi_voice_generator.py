"""Optional, fail-open character dialogue generation via MuAPI."""

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


class MuAPIVoiceGenerator:
    """Lock each character to one MiniMax system voice for the whole drama.

    MuAPI also exposes ``minimax-voice-clone``, but it requires a consented
    reference-audio sample. MuseForge currently has no voice-upload input, so
    assigning stable system voices is the safe character-identity mechanism.
    """

    VOICE_ENDPOINT = os.environ.get("MUAPI_VOICE_MODEL", "minimax-speech-2.6-hd")
    SYSTEM_VOICE_IDS = (
        "Friendly_Person",
        "Wise_Woman",
        "Deep_Voice_Man",
        "Calm_Woman",
        "Casual_Guy",
        "Lively_Girl",
        "Patient_Man",
        "Young_Knight",
        "Determined_Man",
        "Lovely_Girl",
        "Elegant_Man",
        "Inspirational_girl",
    )

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)
        self._character_voices: Dict[str, str] = {}

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

    async def generate_dialogue(
        self,
        character: str,
        line: str,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Optional[str]:
        """Generate one spoken line; return ``None`` on every provider failure."""
        text = (line or "").strip()
        if not text or self.demo:
            return None

        voice_id = self.voice_id_for_character(character)
        payload = {
            "prompt": text,
            "voice_id": voice_id,
            "speed": 1,
            "volume": 1,
            "pitch": 0,
            "emotion": "neutral",
            "english_normalization": False,
            "sample_rate": 32000,
            "bitrate": 128000,
            "channel": 1,
            "format": "mp3",
            "language_boost": "auto",
        }
        try:
            return await self.client.generate(
                self.VOICE_ENDPOINT,
                payload,
                poll_interval=2.0,
                max_polls=120,
                is_cancelled=is_cancelled,
            )
        except Exception as exc:
            logger.warning(
                "Dialogue generation failed for character %s; continuing silently: %s",
                character,
                exc,
            )
            return None

    async def generate_scene_dialogue(
        self,
        dialogue: Iterable[Any],
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> List[Dict[str, str]]:
        """Generate non-empty scene lines in order with locked voice metadata."""
        tracks: List[Dict[str, str]] = []
        for item in dialogue or []:
            if isinstance(item, dict):
                character = str(item.get("character", "Narrator"))
                line = str(item.get("line", ""))
            else:
                character = str(getattr(item, "character", "Narrator"))
                line = str(getattr(item, "line", ""))
            if not line.strip():
                continue

            voice_id = self.voice_id_for_character(character)
            audio_url = await self.generate_dialogue(character, line, is_cancelled=is_cancelled)
            if audio_url:
                tracks.append(
                    {
                        "character": character,
                        "line": line,
                        "voice_id": voice_id,
                        "audio_url": audio_url,
                    }
                )
        return tracks
