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

CHOOSE THE RIGHT MOMENT. You only get ONE shot for this scene, so it must capture the
scene's DRAMATIC PEAK — the single beat that carries the scene's emotional turn (the
look that lands, the touch, the break, the decision). Do NOT storyboard set-up,
arrival, walking, waiting, or scene-setting business when an emotional beat exists in
the scene; a viewer seeing only your shot must understand what emotionally happened.
If the scene has dialogue, stage the moment around the most important line.

SHOW THE EMOTION ON THE FACE. The scene's emotional beat is given to you. "expression_desc"
must state the concrete, visible facial expression AND body language for the character(s)
in frame (e.g. "eyes brimming with tears, trembling chin, shoulders finally dropping as
she exhales"). Never write "neutral", "calm", "expressionless", or a blank value unless
the scene is genuinely emotionless. Repeat the key expression inside visual_desc too.

KEEP FACES READABLE. Faces must be clearly visible and lit well enough to read the
expression — soft key light on the face. Do NOT design pure silhouettes, backlit
shapes, faces turned away from camera, or faces hidden by shadow; those destroy the
emotional read. Prefer medium or close-up framing for emotional beats so the face fills
enough of the frame to be legible.

If a locked Setting is provided, EVERY shot MUST stay in that place and time of day —
do not invent a different location or lighting for this scene.
For duration_seconds do NOT blindly assign 5 to every shot — pick between 3 and 15
based on the scene's importance: 4-6 for short transition/action shots, 8-12 for
emotional/establishing moments, 13-15 for very important finales.
Respond ONLY with valid JSON array containing a single shot object:
[{"idx": 0, "visual_desc": "...", "motion_desc": "...", "expression_desc": "...",
  "audio_desc": "...", "shot_type": "wide|medium|close-up", "camera_movement": "...",
  "lens": "50mm", "duration_seconds": 8}]
(duration_seconds is an example — vary 3-15 by scene; do not always use 5.)"""

    def __init__(self, api_key: Optional[str] = None, demo: bool = False):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.muapi_key = os.environ.get("MUAPI_KEY", "")
        self.demo = demo

    # Non-finale scenes are capped well below the model's max so a run of
    # "important" scenes can't each independently land on 13-15s -- that
    # both defeats the intended variety and multiplies total Kling render
    # time, since every scene is generated sequentially.
    NON_FINALE_MAX_DURATION = 9.0
    FINALE_MAX_DURATION = 15.0

    async def design_storyboard(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: str = "",
        director_style: str = "cinematic_balanced",
        setting_location: str = "",
        setting_time_of_day: str = "",
        setting_era: str = "",
        is_finale: bool = False,
        scene_emotion: str = "",
        scene_dialogue: str = "",
    ) -> List[StoryboardShot]:
        preset = get_director_style(director_style)

        # Demo mode must stay fast and free of real network calls --
        # matches MuAPIImageGenerator/MuAPIVideoGenerator's demo behavior.
        if self.demo:
            return self._clamp_durations(
                self._design_template(script, characters, preset, scene_emotion),
                is_finale,
            )

        char_desc = ", ".join(f"{c.name}: {c.static_features}" for c in characters if c.is_visible)
        setting_line = self._format_setting_line(
            setting_location, setting_time_of_day, setting_era
        )
        prompt = (
            f"Scene script: {script}\n"
            f"{self._format_emotion_line(scene_emotion)}"
            f"{self._format_dialogue_line(scene_dialogue)}"
            f"Characters: {char_desc}\n"
            f"{setting_line}"
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
                self._ensure_expression(shots, scene_emotion)
                if shots:
                    # Hard cap: never produce more than 1 shot per scene
                    # (cost control) — this path was previously missing
                    # the same cap already applied to the direct-Anthropic
                    # fallback below, silently defeating the cost fix
                    # since MuAPI is the PRIMARY path, tried first.
                    return self._clamp_durations(shots[:1], is_finale)
            except Exception as exc:
                raw_snippet = locals().get("content", "<no content received>")
                logger.warning(
                    f"MuAPI LLM call failed, falling back: {exc} | "
                    f"Raw response (first 500 chars): {str(raw_snippet)[:500]!r}"
                )

        # 2) Fall back to a direct Anthropic call if a key is configured.
        if self.api_key:
            shots = await self._design_with_claude(
                script,
                characters,
                user_requirement,
                preset.storyboard_guidance,
                preset.default_lens,
                setting_location=setting_location,
                setting_time_of_day=setting_time_of_day,
                setting_era=setting_era,
                scene_emotion=scene_emotion,
                scene_dialogue=scene_dialogue,
            )
            self._ensure_expression(shots, scene_emotion)
            if shots:
                # Hard cap: never produce more than 1 shot per scene (cost control).
                return self._clamp_durations(shots[:1], is_finale)

        # 3) Last resort: deterministic template, never crashes generation.
        return self._clamp_durations(
            self._design_template(script, characters, preset, scene_emotion), is_finale
        )

    @classmethod
    def _clamp_durations(
        cls, shots: List[StoryboardShot], is_finale: bool
    ) -> List[StoryboardShot]:
        cap = cls.FINALE_MAX_DURATION if is_finale else cls.NON_FINALE_MAX_DURATION
        for shot in shots:
            shot.duration_seconds = min(float(shot.duration_seconds or 0), cap)
        return shots

    # Expressions that mean "no emotion on the face" -- exactly what the
    # user-reported flat/neutral scenes looked like. When a shot comes back
    # with one of these (or with nothing at all), we substitute the scene's
    # own emotional beat so the frame prompt still carries an expression.
    _EMPTY_EXPRESSIONS = {
        "",
        "neutral",
        "none",
        "n/a",
        "calm",
        "expressionless",
        "neutral expression",
        "no expression",
    }

    @classmethod
    def _ensure_expression(
        cls, shots: List[StoryboardShot], scene_emotion: str
    ) -> List[StoryboardShot]:
        """Guarantee every shot carries a usable expression beat.

        The LLM is instructed to fill expression_desc, but it is the single
        thing that makes a scene read as emotional, so it is not left to
        chance: a missing/neutral value falls back to the scene's emotion tag.
        """
        emotion = (scene_emotion or "").strip()
        if not emotion:
            return shots
        for shot in shots:
            # getattr/setattr rather than attribute access: shots may be
            # plain objects from callers/tests that predate expression_desc.
            current = (getattr(shot, "expression_desc", "") or "").strip()
            if current.lower().rstrip(".") in cls._EMPTY_EXPRESSIONS:
                try:
                    shot.expression_desc = emotion
                except AttributeError:
                    # Immutable/slotted shot object -- the frame prompt just
                    # falls back to its face-visibility clause.
                    pass
        return shots

    @staticmethod
    def _format_emotion_line(scene_emotion: str = "") -> str:
        emotion = (scene_emotion or "").strip()
        if not emotion:
            return ""
        return (
            f"Scene emotional beat (MUST be visible on the character's face "
            f"and body in this shot): {emotion}\n"
        )

    @staticmethod
    def _format_dialogue_line(scene_dialogue: str = "") -> str:
        dialogue = (scene_dialogue or "").strip()
        if not dialogue:
            return ""
        return (
            f"Scene dialogue (what is actually said in this moment — stage the "
            f"shot around the most important line):\n{dialogue}\n"
        )

    @staticmethod
    def _format_setting_line(
        setting_location: str = "",
        setting_time_of_day: str = "",
        setting_era: str = "",
    ) -> str:
        parts = [
            p.strip()
            for p in (setting_location, setting_time_of_day, setting_era)
            if (p or "").strip()
        ]
        if not parts:
            return ""
        return (
            "Setting (LOCKED for entire drama — do not change): "
            + ", ".join(parts)
            + "\n"
        )

    async def _design_with_claude(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: str,
        guidance: str,
        default_lens: str,
        setting_location: str = "",
        setting_time_of_day: str = "",
        setting_era: str = "",
        scene_emotion: str = "",
        scene_dialogue: str = "",
    ) -> List[StoryboardShot]:
        try:
            import httpx

            char_desc = ", ".join(f"{c.name}: {c.static_features}" for c in characters if c.is_visible)
            setting_line = self._format_setting_line(
                setting_location, setting_time_of_day, setting_era
            )
            prompt = (
                f"Scene script: {script}\n"
                f"{self._format_emotion_line(scene_emotion)}"
                f"{self._format_dialogue_line(scene_dialogue)}"
                f"Characters: {char_desc}\n"
                f"{setting_line}"
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
        scene_emotion: str = "",
    ) -> List[StoryboardShot]:
        char_name = next((c.name for c in characters if c.is_visible), "Character")
        emotion = (scene_emotion or "").strip()
        emotion_clause = f", {emotion}" if emotion else ""
        return [
            StoryboardShot(
                idx=0,
                visual_desc=f"{char_name} — {script[:120]}{emotion_clause}",
                motion_desc=f"{preset.pacing} camera movement, {preset.storyboard_guidance[:80]}",
                expression_desc=emotion,
                audio_desc="ambient atmospheric sound",
                shot_type="medium shot",
                camera_movement="slow push-in" if preset.pacing == "slow" else "tracking shot",
                lens=preset.default_lens,
                duration_seconds=5.0,
            )
        ]
