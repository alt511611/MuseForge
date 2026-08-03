"""Screenwriter agent — transforms an idea into a structured drama script."""

import json
import logging
import os
import re
from typing import List, Optional

from interfaces.character import CharacterProfile, DramaScript, ScriptScene
from tools.claude_via_muapi import complete_via_muapi

logger = logging.getLogger(__name__)


class ScreenwriterAgent:
    SYSTEM_PROMPT = """You are an award-winning writer-director of micro-dramas and cinematic short films.
You are not summarizing a plot — you are directing a film. Work like a director:

STRUCTURE. Build 3-5 scenes into ONE dramatic shape, not a list of events. Assign each
scene a "dramatic_function" from: setup, inciting_incident, rising_action, turning_point,
climax, resolution. A drama needs a climax; do not write five scenes of rising_action.
Give each scene a "tension" from 1-10 that rises across the story and peaks at the climax.

EVERY SCENE MUST TURN. Set "turn" to the thing that actually CHANGES in the scene — a
decision made, a truth admitted, a hope broken, a distance closed. If you cannot name the
turn, the scene has no reason to exist: rewrite it. This single field decides which moment
gets filmed, so make it concrete and physical, not abstract ("she finally takes her
mother's hand", not "they grow closer").

WRITE SUBTEXT. People in drama rarely say what they mean. Set "subtext" to what is
really going on underneath the spoken lines. When the subtext contradicts the dialogue,
say so — that contradiction is what the actor plays.

STAGE IT PHYSICALLY. Set "staging" to concrete blocking: who is where, what their hands
are doing, and the ONE object the scene turns on. Never leave characters abstractly
"talking"; give the camera something to see.

DIRECT THE PERFORMANCE. For each character give "want" (the external goal they pursue on
screen), "need" (the internal truth they avoid), and "arc" (how they change from first
scene to last). Keep "description" to face, build and age ONLY, and put clothing in
"wardrobe" — these are used separately downstream.

FIND THE THROUGH-LINE. Give the drama a "theme" (its controlling idea in one sentence)
and a "visual_motif": one recurring visual element — an object, a gesture, a quality of
light — that you deliberately restage across scenes so the film reads as a whole.

EMOTION. Set "emotion" to a short (2-4 word) tag for each scene's emotional beat, driven
by what actually happens in that scene (e.g. "tearful reconciliation", "cold resentment",
"tense confrontation", "quiet resignation"). A later storyboard step uses it to pick the
character's facial expression, so it must never be neutral or flat unless the scene is
genuinely emotionless.

DIALOGUE. Write the exact spoken words as character/line pairs. Keep lines short and
speakable. Use an empty dialogue list for silent scenes — silence is a legitimate choice.

SETTING. Define ONE locked setting for the ENTIRE drama (not per scene): location, time
of day, era. Every scene takes place there — do not invent a different place or time per
scene.

PRESET CHARACTERS in the user message already exist: do NOT redefine or rename them.
Use their exact names and visual descriptions, and weave them into the story. You may
add extra supporting characters only if needed.

Respond ONLY with valid JSON matching this schema:
{
  "title": "string",
  "logline": "string",
  "theme": "the controlling idea in one sentence",
  "visual_motif": "one recurring visual element restaged across scenes",
  "mood": "string",
  "estimated_duration_seconds": 30,
  "setting_location": "e.g. coastal village wooden pier",
  "setting_time_of_day": "e.g. sunset, night, midday",
  "setting_era": "e.g. present day, 1950s",
  "characters": [{
    "name": "string",
    "description": "face, build and age ONLY - no clothing",
    "wardrobe": "what they wear",
    "role": "protagonist|antagonist|supporting",
    "want": "external goal", "need": "internal truth", "arc": "how they change"
  }],
  "scenes": [
    {
      "action": "scene 1 action...",
      "dialogue": [{"character": "Kemal", "line": "The exact words Kemal says."}],
      "emotion": "e.g. tearful reconciliation",
      "dramatic_function": "setup|inciting_incident|rising_action|turning_point|climax|resolution",
      "turn": "the concrete thing that changes in this scene",
      "subtext": "what they really mean underneath the lines",
      "staging": "blocking: who is where, hands, the object the scene turns on",
      "tension": 4
    }
  ]
}"""

    #: Token budget for a director-level script. Shared by BOTH provider
    #: paths: the MuAPI route is tried FIRST, so raising it only on the
    #: Anthropic fallback (as an earlier change did) leaves the primary path
    #: truncating its JSON mid-object -- which parses as failure and drops
    #: the whole script to the generic template, silently.
    MAX_SCRIPT_TOKENS = 8192

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
        preset_characters: Optional[List[dict]] = None,
    ) -> DramaScript:
        # Demo mode must stay fast and free of real network calls --
        # matches MuAPIImageGenerator/MuAPIVideoGenerator's demo behavior.
        if self.demo:
            return self._write_template(idea, style, num_scenes, preset_characters)

        preset_block = ""
        if preset_characters:
            lines = []
            for c in preset_characters:
                name = str(c.get("name") or "").strip()
                features = str(c.get("static_features") or "").strip()
                if name and features:
                    lines.append(f"- {name}: {features}")
            if lines:
                preset_block = (
                    "PRESET CHARACTERS (already exist — use directly, do not redefine):\n"
                    + "\n".join(lines)
                    + "\n"
                )

        prompt = (
            f"{preset_block}"
            f"Idea: {idea}\nStyle: {style}\nScenes: {num_scenes}\n"
            f"Additional requirements: {user_requirement or 'none'}"
        )

        # 1) Prefer MuAPI (single existing key, no separate Anthropic
        #    account needed) -- but its exact LLM endpoint/schema isn't
        #    100% confirmed, so any failure here falls through silently.
        if self.muapi_key:
            try:
                content = await complete_via_muapi(
                    self.SYSTEM_PROMPT, prompt, max_tokens=self.MAX_SCRIPT_TOKENS
                )
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
            return await self._write_with_claude(
                idea, style, num_scenes, user_requirement, preset_characters
            )

        # 3) Last resort: deterministic template, never crashes generation.
        return self._write_template(idea, style, num_scenes, preset_characters)

    async def _write_with_claude(
        self,
        idea: str,
        style: str,
        num_scenes: int,
        user_requirement: str,
        preset_characters: Optional[List[dict]] = None,
    ) -> DramaScript:
        try:
            import httpx

            preset_block = ""
            if preset_characters:
                lines = [
                    f"- {c.get('name')}: {c.get('static_features')}"
                    for c in preset_characters
                    if c.get("name") and c.get("static_features")
                ]
                if lines:
                    preset_block = (
                        "PRESET CHARACTERS (already exist — use directly, do not redefine):\n"
                        + "\n".join(lines)
                        + "\n"
                    )
            prompt = (
                f"{preset_block}"
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
                        "model": "claude-sonnet-5",
                        # A director-level script carries per-scene turn,
                        # subtext, staging and per-character want/need/arc, so
                        # 5 scenes no longer fit the old 2048 budget -- a
                        # truncated response is unparseable JSON and silently
                        # drops the whole script to the template fallback.
                        "max_tokens": self.MAX_SCRIPT_TOKENS,
                        "system": self.SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                content = resp.json()["content"][0]["text"]
                data = self._parse_json(content)
                return DramaScript(**data)
        except Exception as exc:
            # This used to swallow the exception entirely, so a failing
            # Anthropic key/model/quota looked identical to "no key
            # configured" in the logs -- both just produced a generic
            # template with no explanation. Surface the response body when
            # there is one; that is where the API states the actual cause.
            detail = ""
            resp = getattr(exc, "response", None)
            if resp is not None:
                try:
                    detail = f" | status={resp.status_code} body={resp.text[:500]}"
                except Exception:
                    pass
            logger.error(
                f"Anthropic screenwriter call failed, falling back to template: "
                f"{type(exc).__name__}: {exc}{detail}"
            )
            return self._write_template(idea, style, num_scenes, preset_characters)

    def _parse_json(self, text: str) -> dict:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            return json.loads(match.group())
        raise ValueError("No JSON found in response")

    def _write_template(
        self,
        idea: str,
        style: str,
        num_scenes: int,
        preset_characters: Optional[List[dict]] = None,
    ) -> DramaScript:
        title = idea[:60].strip().rstrip(".") or "Untitled Drama"
        protagonist = self._extract_protagonist(idea)

        characters = []
        if preset_characters:
            for i, c in enumerate(preset_characters):
                name = str(c.get("name") or "").strip()
                features = str(c.get("static_features") or "").strip()
                if not name:
                    continue
                characters.append(
                    CharacterProfile(
                        name=name,
                        description=features or f"{name}, {style.lower()} visual style",
                        role="protagonist" if i == 0 else "supporting",
                    )
                )
            if characters:
                protagonist = characters[0].name

        if not characters:
            characters = [
                CharacterProfile(
                    name=protagonist,
                    description=f"Main character from the story, {style.lower()} visual style",
                    role="protagonist",
                )
            ]

        # The offline fallback still has to be a DRAMA, not five flat captions:
        # it carries the same structure the LLM path is asked for (a function,
        # a turn, a tension value), so a key-less run degrades in polish rather
        # than losing the shape of the story.
        #
        # Each beat is keyed by its dramatic function and carries its OWN
        # action line, so a beat can never end up describing one thing while
        # its function and turn describe another.
        beats = {
            "setup": {
                "action": f"{protagonist} enters. The {style.lower()} atmosphere sets the tone.",
                "emotion": "guarded anticipation",
                "turn": f"{protagonist} decides to stay instead of turning back",
                "subtext": "wanting to be here and not wanting to admit it",
                "staging": f"{protagonist} stops in the doorway, one hand still on the frame",
                "tension": 3,
            },
            "inciting_incident": {
                "action": f"An unexpected challenge finds {protagonist}.",
                "emotion": "rising alarm",
                "turn": f"{protagonist} realises this cannot be avoided",
                "subtext": "pretending to be steadier than they are",
                "staging": f"{protagonist} sets an object down too carefully",
                "tension": 6,
            },
            "rising_action": {
                "action": f"The cost of going on becomes clear to {protagonist}.",
                "emotion": "mounting dread",
                "turn": f"{protagonist} sees what this will take and does not turn back",
                "subtext": "counting the price and staying anyway",
                "staging": f"{protagonist} stands very still while the room settles",
                "tension": 8,
            },
            "climax": {
                "action": f"A pivotal moment — {protagonist} makes a decisive choice.",
                "emotion": "steeled resolve",
                "turn": f"{protagonist} commits, out loud, and cannot take it back",
                "subtext": "the fear underneath the decision has not gone away",
                "staging": f"{protagonist} steps forward into the light, hands open",
                "tension": 10,
            },
            "resolution": {
                "action": f"Final frame: {protagonist} is changed by what was said.",
                "emotion": "quiet release",
                "turn": f"{protagonist} finally lets the held breath go",
                "subtext": "grief and relief arriving at the same time",
                "staging": f"{protagonist} turns from the window, shoulders dropping",
                "tension": 4,
            },
        }
        # Every shape opens somewhere, peaks at the climax and lands on the
        # resolution -- so no scene count can produce a drama that never peaks
        # or that stops mid-escalation.
        shapes = {
            2: ["climax", "resolution"],
            3: ["setup", "climax", "resolution"],
            4: ["setup", "inciting_incident", "climax", "resolution"],
            5: ["setup", "inciting_incident", "rising_action", "climax", "resolution"],
        }
        shape = shapes[max(2, min(num_scenes, 5))]
        scenes = [
            ScriptScene(dialogue=[], dramatic_function=fn, **beats[fn]) for fn in shape
        ]

        return DramaScript(
            generated_by="template",
            title=title,
            logline=idea,
            theme="A choice made too late still counts as a choice.",
            visual_motif="light through a window, falling differently in each scene",
            mood=style.lower(),
            estimated_duration_seconds=len(scenes) * 8,
            setting_location="generic cinematic location",
            setting_time_of_day="midday",
            setting_era="present day",
            characters=characters,
            scenes=scenes,
        )

    def _extract_protagonist(self, idea: str) -> str:
        for word in idea.split():
            cleaned = re.sub(r"[^a-zA-Z]", "", word)
            if cleaned and cleaned[0].isupper() and len(cleaned) > 2:
                return cleaned
        return "Alex"
