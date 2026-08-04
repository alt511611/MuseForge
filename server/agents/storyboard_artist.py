"""Storyboard artist agent — designs shots from script with director style guidance."""

import json
import logging
import os
import re
from typing import List, Optional

from interfaces.camera import get_director_style
from interfaces.character import CharacterInScene
from interfaces.shot import StoryboardShot
from tools.claude_via_muapi import complete_via_muapi, is_muapi_llm_enabled

logger = logging.getLogger(__name__)


class StoryboardArtist:
    SYSTEM_PROMPT = """You are a master storyboard artist for cinematic productions.
Design exactly 1 shot for the given scene script. Apply the director's style guidance.

THE USER'S BRIEF OUTRANKS EVERYTHING BELOW. When the brief is given it is the
production's specification: honour its named props, wardrobe, location, framing,
lens and camera rules exactly, and never design a shot that contradicts it. If the
brief says the camera is locked off, "camera_movement" is "static locked-off tripod,
no camera movement" — not a push-in. If the brief names what is in frame (a desk, a
notepad, a watch), name those things in "visual_desc" so they actually get rendered.
Only where the brief is silent do the guidelines below decide.

CHOOSE THE RIGHT MOMENT. You only get ONE shot for this scene, so it must capture the
scene's DRAMATIC PEAK — the single beat that carries the scene's emotional turn (the
look that lands, the touch, the break, the decision). Do NOT storyboard set-up,
arrival, walking, waiting, or scene-setting business when an emotional beat exists in
the scene; a viewer seeing only your shot must understand what emotionally happened.
If the scene has dialogue, stage the moment around the most important line.
When the director's notes name THE TURN, that is the moment — film it, not the
business around it. Honour the given staging (positions, hands, the object the scene
turns on) instead of inventing different blocking.

MATCH SHOT SCALE TO THE BEAT. Let the scene's dramatic function and tension pick the
framing: setup and resolution can breathe in wide or medium; rising_action and
turning_point tighten to medium; climax and any tension of 8+ belong in a close-up
where the face fills the frame. High tension also earns more screen time.

PLAY THE SUBTEXT, NOT THE LINE. When the notes give subtext that contradicts the
dialogue, the expression must play the subtext — a character insisting they are fine
while their face says otherwise is the shot worth making.

RESPECT THE 180° LINE. Screen direction is LOCKED for the whole drama: in any
two-character conversation the FIRST character listed always occupies frame-left
looking screen-RIGHT, and the SECOND always occupies frame-right looking
screen-LEFT — in every scene, including singles and over-the-shoulder shots (a
character alone in frame still looks toward where the other one is). Never cross
the line or mirror the composition between scenes; reversed eyelines make a
conversation read as two people facing away from each other.

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

    #: One shot's JSON is small, but the director's notes make the RESPONSE
    #: longer than the old default allowed. Same lesson as the screenwriter:
    #: both provider paths must share the budget.
    MAX_SHOT_TOKENS = 2048

    def __init__(self, api_key: Optional[str] = None, demo: bool = False):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.muapi_key = os.environ.get("MUAPI_KEY", "")
        self.demo = demo

    # Non-finale scenes are capped well below the model's max so a run of
    # "important" scenes can't each independently land on 13-15s -- that
    # both defeats the intended variety and multiplies total Kling render
    # time and cost, which scale with generated seconds.
    NON_FINALE_MAX_DURATION = 9.0
    FINALE_MAX_DURATION = 15.0

    # When the script carries a dramatic tension, the cap follows the BEAT
    # rather than being one flat ceiling every scene drifts up to. A quiet
    # setup gets ~5s and a climax ~10s, which is both better filmmaking (a
    # varied rhythm instead of uniform blocks) and cheaper: a run of scenes
    # can no longer each sit at the flat maximum.
    TENSION_MIN_DURATION = 5.0
    TENSION_MAX_DURATION = 10.0
    # A finale needs room to land even when its tension is low (a quiet
    # resolution is still the ending), so it gets extra headroom.
    FINALE_EXTRA_DURATION = 3.0
    FINALE_MIN_DURATION = 8.0

    @classmethod
    def duration_cap(cls, is_finale: bool, tension: int = 0) -> float:
        """Maximum shot length for a scene, in seconds.

        Without a tension value (legacy scripts) this is exactly the previous
        flat behavior. With one, the cap scales linearly across the tension
        range so screen time is spent where the drama is.
        """
        if not tension:
            return cls.FINALE_MAX_DURATION if is_finale else cls.NON_FINALE_MAX_DURATION
        tension = max(1, min(10, int(tension)))
        span = cls.TENSION_MAX_DURATION - cls.TENSION_MIN_DURATION
        cap = cls.TENSION_MIN_DURATION + ((tension - 1) / 9.0) * span
        if is_finale:
            cap = max(cap + cls.FINALE_EXTRA_DURATION, cls.FINALE_MIN_DURATION)
            return min(cap, cls.FINALE_MAX_DURATION)
        return min(cap, cls.NON_FINALE_MAX_DURATION)

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
        scene_direction: str = "",
        scene_tension: int = 0,
        scene_duration: float = 0.0,
        character_direction: str = "",
        theme: str = "",
        visual_motif: str = "",
        user_brief: str = "",
    ) -> List[StoryboardShot]:
        preset = get_director_style(director_style)

        # Demo mode must stay fast and free of real network calls --
        # matches MuAPIImageGenerator/MuAPIVideoGenerator's demo behavior.
        if self.demo:
            return self._clamp_durations(
                self._design_template(script, characters, preset, scene_emotion),
                is_finale,
                scene_tension,
                scene_duration,
            )

        char_desc = ", ".join(f"{c.name}: {c.static_features}" for c in characters if c.is_visible)
        setting_line = self._format_setting_line(
            setting_location, setting_time_of_day, setting_era
        )
        prompt = (
            f"{self._format_user_brief_block(user_brief)}"
            f"Scene script: {script}\n"
            f"{self._format_emotion_line(scene_emotion)}"
            f"{self._format_direction_block(scene_direction)}"
            f"{self._format_dialogue_line(scene_dialogue)}"
            f"Characters: {char_desc}\n"
            f"{self._format_character_direction_block(character_direction)}"
            f"{setting_line}"
            f"{self._format_through_line(theme, visual_motif)}"
            f"Director guidance: {preset.storyboard_guidance}\nDefault lens: {preset.default_lens}\n"
            f"User requirements: {user_requirement or 'none'}"
        )

        # 1) MuAPI first, but opt-in only -- its LLM slug is a guess, so it
        #    does not stand in front of the Anthropic path unless
        #    MUAPI_LLM_MODEL is set (see tools/claude_via_muapi.py).
        if self.muapi_key and is_muapi_llm_enabled():
            try:
                content = await complete_via_muapi(
                    self.SYSTEM_PROMPT, prompt, max_tokens=self.MAX_SHOT_TOKENS
                )
                data = json.loads(re.search(r"\[[\s\S]*\]", content).group())
                shots = [StoryboardShot(**s) for s in data]
                self._ensure_expression(shots, scene_emotion)
                if shots:
                    # Hard cap: never produce more than 1 shot per scene
                    # (cost control) — this path was previously missing
                    # the same cap already applied to the direct-Anthropic
                    # fallback below, silently defeating the cost fix
                    # since MuAPI is the PRIMARY path, tried first.
                    return self._clamp_durations(shots[:1], is_finale, scene_tension, scene_duration)
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
                scene_direction=scene_direction,
                character_direction=character_direction,
                theme=theme,
                visual_motif=visual_motif,
                user_brief=user_brief,
            )
            self._ensure_expression(shots, scene_emotion)
            if shots:
                # Hard cap: never produce more than 1 shot per scene (cost control).
                return self._clamp_durations(shots[:1], is_finale, scene_tension, scene_duration)

        # 3) Last resort: deterministic template, never crashes generation.
        return self._clamp_durations(
            self._design_template(script, characters, preset, scene_emotion),
            is_finale,
            scene_tension,
            scene_duration,
        )

    @classmethod
    def _clamp_durations(
        cls,
        shots: List[StoryboardShot],
        is_finale: bool,
        tension: int = 0,
        budget: float = 0.0,
    ) -> List[StoryboardShot]:
        """Set each shot's length.

        With a `budget` (the drama's fixed second allowance, already split by
        tension in interfaces/second_budget) the scene is SET to it rather
        than merely capped: the provider bills per second, so leaving the
        model free to come in under budget makes the job's cost -- and its
        margin -- unpredictable at the moment credits are charged. The budget
        is the whole point; honouring it exactly is what makes the promise
        "N credits buys M seconds" true.

        Without a budget (legacy callers, single-scene tests) this keeps the
        previous cap-only behaviour.
        """
        if budget and budget > 0:
            for shot in shots:
                shot.duration_seconds = float(budget)
            return shots
        cap = cls.duration_cap(is_finale, tension)
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

    #: How much of the user's prompt is carried into the shot-design call.
    #: The API caps an idea at 2000 characters, so this passes it whole; the
    #: bound exists only so a future cap increase cannot blow the token budget.
    MAX_BRIEF_CHARS = 2000

    @classmethod
    def _format_user_brief_block(cls, user_brief: str = "") -> str:
        """The user's own words, at the TOP of the prompt and marked binding.

        The scene action line is a lossy re-telling: it survives the
        screenwriter's rewrite, the brief's concrete specifics (props on the
        desk, the exact sweater, "locked-off tripod, zero camera movement")
        do not. Restating them here is what stops the shot being designed
        against a description the user never wrote.
        """
        brief = (user_brief or "").strip()
        if not brief:
            return ""
        if len(brief) > cls.MAX_BRIEF_CHARS:
            brief = brief[: cls.MAX_BRIEF_CHARS].rstrip() + " […]"
        return (
            "USER'S ORIGINAL BRIEF — BINDING, outranks every other instruction "
            "below. Honour its wardrobe, props, location, framing and camera "
            "rules exactly; never design a shot that contradicts it:\n"
            f"{brief}\n\n"
        )

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
    def _format_direction_block(scene_direction: str = "") -> str:
        """The scene's dramatic function, turn, subtext, staging and tension.

        The turn is the single most important input to shot selection: it
        names the moment that must be filmed.
        """
        direction = (scene_direction or "").strip()
        if not direction:
            return ""
        return f"DIRECTOR'S NOTES FOR THIS SCENE:\n{direction}\n"

    @staticmethod
    def _format_character_direction_block(character_direction: str = "") -> str:
        direction = (character_direction or "").strip()
        if not direction:
            return ""
        return (
            "Character performance (what each is playing underneath):\n"
            f"{direction}\n"
        )

    @staticmethod
    def _format_through_line(theme: str = "", visual_motif: str = "") -> str:
        """Drama-wide theme and recurring visual motif.

        Restaging the motif is what makes a set of independently generated
        shots read as one film instead of a slideshow.
        """
        parts = []
        if (theme or "").strip():
            parts.append(f"Theme (the idea every shot should serve): {theme.strip()}")
        if (visual_motif or "").strip():
            parts.append(
                f"Recurring visual motif — restage it in this shot where it "
                f"fits naturally: {visual_motif.strip()}"
            )
        return "\n".join(parts) + "\n" if parts else ""

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
        scene_direction: str = "",
        character_direction: str = "",
        theme: str = "",
        visual_motif: str = "",
        user_brief: str = "",
    ) -> List[StoryboardShot]:
        try:
            import httpx

            char_desc = ", ".join(f"{c.name}: {c.static_features}" for c in characters if c.is_visible)
            setting_line = self._format_setting_line(
                setting_location, setting_time_of_day, setting_era
            )
            prompt = (
                f"{self._format_user_brief_block(user_brief)}"
                f"Scene script: {script}\n"
                f"{self._format_emotion_line(scene_emotion)}"
                f"{self._format_direction_block(scene_direction)}"
                f"{self._format_dialogue_line(scene_dialogue)}"
                f"Characters: {char_desc}\n"
                f"{self._format_character_direction_block(character_direction)}"
                f"{setting_line}"
                f"{self._format_through_line(theme, visual_motif)}"
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
                        "model": "claude-sonnet-5",
                        "max_tokens": 2048,
                        "system": self.SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                content = resp.json()["content"][0]["text"]
                data = json.loads(re.search(r"\[[\s\S]*\]", content).group())
                return [StoryboardShot(**s) for s in data]
        except Exception as exc:
            detail = ""
            resp = getattr(exc, "response", None)
            if resp is not None:
                try:
                    detail = f" | status={resp.status_code} body={resp.text[:500]}"
                except Exception:
                    pass
            logger.error(
                f"Anthropic storyboard call failed, falling back to template: "
                f"{type(exc).__name__}: {exc}{detail}"
            )
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
