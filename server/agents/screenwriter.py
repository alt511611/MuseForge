"""Screenwriter agent — transforms an idea into a structured drama script."""

import json
import logging
import os
import re
from typing import List, Optional

from interfaces.character import CharacterProfile, DramaScript
from tools.claude_via_muapi import complete_via_muapi

logger = logging.getLogger(__name__)


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

    def __init__(self, api_key: Optional[str] = None, demo: bool = False):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.muapi_key = os.environ.get("MUAPI_KEY", "")
        self.demo = demo

    async def write_script(
        self,
        idea: str,
        style: str = "Cinematic",
        num_scenes: int = 3,
        user_requirement: str = "",
    ) -> DramaScript:
        # Demo mode must stay fast and free of real network calls --
        # matches MuAPIImageGenerator/MuAPIVideoGenerator's demo behavior.
        if self.demo:
            return self._write_template(idea, style, num_scenes)

        prompt = (
            f"Idea: {idea}\nStyle: {style}\nScenes: {num_scenes}\n"
            f"Additional requirements: {user_requirement or 'none'}"
        )

        # 1) Prefer MuAPI (single existing key, no separate Anthropic
        #    account needed) -- but its exact LLM endpoint/schema isn't
        #    100% confirmed, so any failure here falls through silently.
        if self.muapi_key:
            try:
                content = await complete_via_muapi(self.SYSTEM_PROMPT, prompt)
                return DramaScript(**self._parse_json(content))
            except Exception as exc:
                # Include a snippet of the RAW MuAPI response so failures
                # are diagnosable from logs alone -- the earlier version of
                # this log line only showed the exception message ("No
                # JSON found in response"), not what MuAPI actually
                # returned, making it impossible to tell whether the
                # response was empty, wrapped in markdown fences, JSON in
                # a different field, an error message, etc.
                raw_snippet = locals().get("content", "<no content received>")
                logger.warning(
                    f"MuAPI LLM call failed, falling back: {exc} | "
                    f"Raw response (first 500 chars): {str(raw_snippet)[:500]!r}"
                )

        # 2) Fall back to a direct Anthropic call if a key is configured.
        if self.api_key:
            return await self._write_with_claude(idea, style, num_scenes, user_requirement)

        # 3) Last resort: deterministic template, never crashes generation.
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
