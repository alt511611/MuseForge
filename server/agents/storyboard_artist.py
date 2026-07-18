"""Storyboard artist agent — designs shots from script with director style guidance."""

import json
import logging
import os
import re
from typing import List, Optional

from interfaces.camera import get_director_style
from interfaces.character import CharacterInScene
from interfaces.shot import StoryboardShot
from tools.claude_via_muapi import complete_via_muapi

logger = logging.getLogger(__name__)


class StoryboardArtist:
    SYSTEM_PROMPT = """You are a master storyboard artist for cinematic productions.
Design exactly 1 shot for the given scene script. Apply the director's style guidance.
Respond ONLY with valid JSON array containing a single shot object:
[{"idx": 0, "visual_desc": "...", "motion_desc": "...", "audio_desc": "...",
  "shot_type": "wide|medium|close-up", "camera_movement": "...", "lens": "50mm", "duration_seconds": 5}]"""

    def __init__(self, api_key: Optional[str] = None, demo: bool = False):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.muapi_key = os.environ.get("MUAPI_KEY", "")
        self.demo = demo

    async def design_storyboard(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: str = "",
        director_style: str = "cinematic_balanced",
    ) -> List[StoryboardShot]:
        preset = get_director_style(director_style)

        # Demo mode must stay fast and free of real network calls --
        # matches MuAPIImageGenerator/MuAPIVideoGenerator's demo behavior.
        if self.demo:
            return self._design_template(script, characters, preset)

        char_desc = ", ".join(f"{c.name}: {c.static_features}" for c in characters if c.is_visible)
        prompt = (
            f"Scene script: {script}\nCharacters: {char_desc}\n"
            f"Director guidance: {preset.storyboard_guidance}\nDefault lens: {preset.default_lens}\n"
            f"User requirements: {user_requirement or 'none'}"
        )

        # 1) Prefer MuAPI (see tools/claude_via_muapi.py docstring for the
        #    caveat on why this isn't 100% guaranteed to work yet).
        if self.muapi_key:
            try:
                content = await complete_via_muapi(self.SYSTEM_PROMPT, prompt)
                data = json.loads(re.search(r"\[[\s\S]*\]", content).group())
                shots = [StoryboardShot(**s) for s in data]
                if shots:
                    # Hard cap: never produce more than 1 shot per scene
                    # (cost control) — this path was previously missing
                    # the same cap already applied to the direct-Anthropic
                    # fallback below, silently defeating the cost fix
                    # since MuAPI is the PRIMARY path, tried first.
                    return shots[:1]
            except Exception as exc:
                raw_snippet = locals().get("content", "<no content received>")
                logger.warning(
                    f"MuAPI LLM call failed, falling back: {exc} | "
                    f"Raw response (first 500 chars): {str(raw_snippet)[:500]!r}"
                )

        # 2) Fall back to a direct Anthropic call if a key is configured.
        if self.api_key:
            shots = await self._design_with_claude(
                script, characters, user_requirement, preset.storyboard_guidance, preset.default_lens
            )
            if shots:
                # Hard cap: never produce more than 1 shot per scene (cost control).
                return shots[:1]

        # 3) Last resort: deterministic template, never crashes generation.
        return self._design_template(script, characters, preset)

    async def _design_with_claude(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: str,
        guidance: str,
        default_lens: str,
    ) -> List[StoryboardShot]:
        try:
            import httpx

            char_desc = ", ".join(f"{c.name}: {c.static_features}" for c in characters if c.is_visible)
            prompt = (
                f"Scene script: {script}\nCharacters: {char_desc}\n"
                f"Director guidance: {guidance}\nDefault lens: {default_lens}\n"
                f"User requirements: {user_requirement or 'none'}"
            )
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 2048,
                        "system": self.SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                content = resp.json()["content"][0]["text"]
                data = json.loads(re.search(r"\[[\s\S]*\]", content).group())
                return [StoryboardShot(**s) for s in data]
        except Exception:
            return []

    def _design_template(
        self,
        script: str,
        characters: List[CharacterInScene],
        preset,
    ) -> List[StoryboardShot]:
        char_name = next((c.name for c in characters if c.is_visible), "Character")
        return [
            StoryboardShot(
                idx=0,
                visual_desc=f"{char_name} — {script[:120]}",
                motion_desc=f"{preset.pacing} camera movement, {preset.storyboard_guidance[:80]}",
                audio_desc="ambient atmospheric sound",
                shot_type="medium shot",
                camera_movement="slow push-in" if preset.pacing == "slow" else "tracking shot",
                lens=preset.default_lens,
                duration_seconds=5.0,
            )
        ]
