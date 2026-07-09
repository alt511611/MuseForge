"""Screenwriter agent — transforms an idea into a structured drama script."""

import json
import os
import re
from typing import List, Optional

from interfaces.character import CharacterProfile, DramaScript


class ScreenwriterAgent:
    SYSTEM_PROMPT = """You are an award-winning screenwriter specializing in micro-dramas and cinematic short films.
Given a user's idea, write a compelling script broken into 3-5 short scenes (each 1-2 sentences of action).
Extract named characters with visual descriptions for AI image generation.
Respond ONLY with valid JSON matching this schema:
{
  "title": "string",
  "logline": "string",
  "mood": "string",
  "estimated_duration_seconds": 30,
  "characters": [{"name": "string", "description": "visual appearance for AI", "role": "protagonist|antagonist|supporting"}],
  "scenes": ["scene 1 action...", "scene 2 action..."]
}"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    async def write_script(
        self,
        idea: str,
        style: str = "Cinematic",
        num_scenes: int = 3,
        user_requirement: str = "",
    ) -> DramaScript:
        if self.api_key:
            return await self._write_with_claude(idea, style, num_scenes, user_requirement)
        return self._write_template(idea, style, num_scenes)

    async def _write_with_claude(
        self,
        idea: str,
        style: str,
        num_scenes: int,
        user_requirement: str,
    ) -> DramaScript:
        try:
            import httpx

            prompt = (
                f"Idea: {idea}\nStyle: {style}\nScenes: {num_scenes}\n"
                f"Additional requirements: {user_requirement or 'none'}"
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
                data = self._parse_json(content)
                return DramaScript(**data)
        except Exception:
            return self._write_template(idea, style, num_scenes)

    def _parse_json(self, text: str) -> dict:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise ValueError("No JSON found in response")

    def _write_template(self, idea: str, style: str, num_scenes: int) -> DramaScript:
        title = idea[:60].strip().rstrip(".") or "Untitled Drama"
        protagonist = self._extract_protagonist(idea)

        scene_templates = [
            f"{protagonist} enters the scene. The {style.lower()} atmosphere sets the tone.",
            f"Tension builds as {protagonist} faces an unexpected challenge.",
            f"A pivotal moment — {protagonist} makes a decisive choice.",
            f"The aftermath: consequences ripple through the environment.",
            f"Final frame: {protagonist} walks away, transformed.",
        ]
        scenes = scene_templates[: max(2, min(num_scenes, 5))]

        return DramaScript(
            title=title,
            logline=idea,
            mood=style.lower(),
            estimated_duration_seconds=len(scenes) * 8,
            characters=[
                CharacterProfile(
                    name=protagonist,
                    description=f"Main character from the story, {style.lower()} visual style",
                    role="protagonist",
                )
            ],
            scenes=scenes,
        )

    def _extract_protagonist(self, idea: str) -> str:
        for word in idea.split():
            cleaned = re.sub(r"[^a-zA-Z]", "", word)
            if cleaned and cleaned[0].isupper() and len(cleaned) > 2:
                return cleaned
        return "Alex"
