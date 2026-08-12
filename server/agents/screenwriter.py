"""Screenwriter agent — transforms an idea into a structured drama script."""

import json
import logging
import os
import re
from typing import List, Optional

from interfaces import gender as gender_of
from interfaces.character import CharacterProfile, DramaScript, ScriptScene
from interfaces.language import DEFAULT_LANGUAGE, is_default, name_of
from tools.claude_via_muapi import complete_via_muapi, is_muapi_llm_enabled

logger = logging.getLogger(__name__)


class ScriptGenerationFailed(Exception):
    """No LLM provider could write a script for the user's idea.

    Raised instead of quietly returning the deterministic template: the
    template ignores the user's prompt almost entirely (generic location,
    a protagonist with no description, no dialogue), so shipping it renders
    a paid video that has nothing to do with what was asked for. Failing the
    job refunds the credits and tells the user the truth.
    """


class ScreenwriterAgent:
    SYSTEM_PROMPT = """You are an award-winning writer-director of micro-dramas and cinematic short films.
You are not summarizing a plot — you are directing a film. Work like a director:

THE BRIEF IS BINDING. Anything the user states CONCRETELY is a specification, not
inspiration: named characters and their described age, hair, build and clothing; the
named location and the props in it; the stated time of day; the exact lines to be
spoken. Copy those details through verbatim — a described "charcoal crew-neck sweater"
must appear in that character's "wardrobe", a described "walnut desk in a home study"
must be the "setting_location". You invent ONLY what the brief leaves open. If the
brief already reads as a shot list, keep its scenes, their order and their spoken
lines; your job is then to fill in the fields it does not mention, not to rewrite it.
If the brief supplies the spoken lines, put them in "dialogue" word for word — never
replace them with lines of your own and never return an empty dialogue list.

THE BRIEF'S EVENT IS THE CLIMAX. When the brief states something that HAPPENS — "the
city's power dies the moment she opens it", "the letter burns", "he misses the train" —
that event is not background colour, it is the film. Make it the "turn" of the climax
scene and write it into that scene's "action" as something a camera can watch happen.
A drama whose stated event never visibly occurs has failed the brief, however good the
scenes around it are.

DO NOT PRE-EMPT THE EVENT. No scene before the climax may show the event or its
aftermath: if the power dies at the climax, every earlier scene is still lit; if the
container is opened at the climax, every earlier scene has it shut. Order the scenes so
that each one's "action" is only possible given what the earlier scenes have already
done, and so the world visibly CHANGES at the climax.

NAME THE CHANGE. On the ONE scene where the brief's event happens, set "world_change" to
what a camera sees become different about the PLACE itself, in a single concrete clause —
"every light in the city and on the docks goes out, leaving only the container's glow",
"the water floods over the pier edge". Leave "world_change" empty ("") on every other
scene. This field is what tells the image step to break the drama's locked lighting for
that one scene; without it the shot is rendered under the same lamps as scene 1 and the
event the whole film is built on is literally invisible. Write the change as a STATE the
picture ends in, not as a process ("the harbour is now black except for one glow", not
"the lights begin to flicker").

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

WHO THE BRIEF SAYS IT IS. "description" must OPEN with the character's gender and age
("woman in her thirties, weathered face, close-cropped hair"), because it is the only
text the image model is given about who this person is — a description that omits it is
drawn as the model's default, not as your character. When the brief genders anyone, by
pronoun or by noun ("she", "her sister", "a dock worker ... she opens it"), that
character IS that gender and stays it in every scene. The brief's protagonist is the
protagonist: do not demote them to a supporting role, do not split their action between
two new characters, and do not add a second lead the brief never asked for.

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

CLOSED CAST, FIXED COSTUME. Every character a viewer will see must be listed in
"characters" — the render only holds onto faces it was told about, so anyone who appears
in an "action" line without a "characters" entry comes back as a different stranger in
every scene. Keep the cast as small as the story allows, introduce no new featured
character after the first scene, and give each one a SPECIFIC "wardrobe" (garment, cut,
colour) that they wear for the whole drama. Never write a costume change unless the brief
asks for one, and never describe the same person's clothing differently in two scenes.
Dress them from the HEAD DOWN: "wardrobe" must settle what is on their head — name the
hat, helmet or hood if they wear one, and write "bare-headed" if they do not. Leaving it
unsaid is how the same worker ends up in a beanie, then a hard hat, then neither: the
render only holds what the wardrobe named, and invents the rest afresh every scene.

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
    "description": "gender and age FIRST, then face and build - no clothing",
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
      "world_change": "climax scene ONLY: what visibly changes about the place itself - otherwise \"\"",
      "subtext": "what they really mean underneath the lines",
      "staging": "blocking: who is where, hands, the object the scene turns on",
      "tension": 4
    }
  ]
}"""

    #: Appended to the system prompt when the drama is not in English.
    #:
    #: Placed in the SYSTEM prompt, not the user turn, because it has to
    #: outrank the brief: a Turkish user often writes the idea in English
    #: ("two brothers fight over an inheritance") and still wants a Turkish
    #: drama. It also has to outrank this prompt's own English example values
    #: (`"line": "The exact words Kemal says."`), which were quietly biasing
    #: short briefs back to English.
    #:
    #: Field NAMES stay English or the JSON stops parsing.
    LANGUAGE_CLAUSE = """

LANGUAGE. Write the drama in {language}. Every piece of text a viewer will
read or hear — "title", "logline", and every "line" of dialogue — must be in
{language}, natural and idiomatic, never a translation of an English sentence.
This holds even when the user's brief itself is written in another language.
The JSON field NAMES and the enum values ("protagonist", "climax", ...) stay
in English exactly as specified; only the prose changes."""

    #: Appended to the system prompt when the job will actually VOICE the
    #: script (dialogue is enabled and paid for on this run).
    #:
    #: The base prompt tells the model that "silence is a legitimate choice",
    #: which is true of a silent film and wrong of a job the user switched
    #: dialogue on for: an all-silent script produces no voice tracks, no
    #: captions and — with music off — a master with no audio stream at all,
    #: which reads as the feature being broken rather than as a choice.
    DIALOGUE_CLAUSE = """

SPOKEN DRAMA. This script WILL be voiced by actors, so it cannot be a silent film:
EVERY scene needs at least one line in its "dialogue" list, and an empty dialogue
list is not acceptable in any scene. Keep lines short, speakable and few (one to
three per scene) — this is film dialogue over a picture, not a radio play. The
climax's stated event still has to be SEEN, not merely narrated: never replace the
event with a character describing it."""

    #: Token budget for a director-level script. Shared by BOTH provider
    #: paths: the MuAPI route is tried FIRST, so raising it only on the
    #: Anthropic fallback (as an earlier change did) leaves the primary path
    #: truncating its JSON mid-object -- which parses as failure and drops
    #: the whole script to the generic template, silently.
    #:
    #: 8192 still truncated in production: a five-scene script carries
    #: per-scene turn/subtext/staging plus per-character want/need/arc and
    #: verbatim dialogue, and a response cut off mid-object is unparseable
    #: JSON -- which surfaced to the user as "the script model is
    #: unavailable" even though the model had answered fine. The Anthropic
    #: path streams, so a larger budget costs nothing in wall-clock risk;
    #: unused tokens are not billed.
    MAX_SCRIPT_TOKENS = 16000

    def __init__(self, api_key: Optional[str] = None, demo: bool = False):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.muapi_key = os.environ.get("MUAPI_KEY", "")
        self.demo = demo

    def _system_prompt(
        self, language: str = DEFAULT_LANGUAGE, require_dialogue: bool = False
    ) -> str:
        """The system prompt for this drama's language and audio mode.

        English adds nothing to the language clause — the prompt is already
        written in it, and a redundant "write in English" clause only spends
        tokens.
        """
        prompt = self.SYSTEM_PROMPT
        if not is_default(language):
            prompt += self.LANGUAGE_CLAUSE.format(language=name_of(language))
        if require_dialogue:
            prompt += self.DIALOGUE_CLAUSE
        return prompt

    async def write_script(
        self,
        idea: str,
        style: str = "Cinematic",
        num_scenes: int = 3,
        user_requirement: str = "",
        preset_characters: Optional[List[dict]] = None,
        language: str = DEFAULT_LANGUAGE,
        require_dialogue: bool = False,
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

        # 1) MuAPI first, but only when an operator has explicitly named a
        #    model slug: it is a guess, so by default it must not stand in
        #    front of the Anthropic path (see tools/claude_via_muapi.py).
        #    A failure here still falls through to Anthropic.
        if self.muapi_key and is_muapi_llm_enabled():
            try:
                content = await complete_via_muapi(
                    self._system_prompt(language, require_dialogue),
                    prompt,
                    max_tokens=self.MAX_SCRIPT_TOKENS,
                )
                return self._with_brief(
                    DramaScript(**self._parse_json(content)), idea
                )
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
                idea,
                style,
                num_scenes,
                user_requirement,
                preset_characters,
                language,
                require_dialogue,
            )

        # 3) No provider answered. The deterministic template is NOT an
        #    acceptable substitute for a paid render -- it discards the user's
        #    idea (generic location, an undescribed protagonist, no dialogue),
        #    which is exactly how a job ends up producing a video of a
        #    different person in a different room saying nothing. Fail loudly
        #    so the job fails, the credits are refunded, and the operator sees
        #    a configuration error instead of a mystery-bad video.
        raise ScriptGenerationFailed(
            "The script model is unavailable, so your idea could not be turned "
            "into a script. No credits were spent — please try again shortly."
        )

    @classmethod
    def _with_brief(cls, script: DramaScript, idea: str) -> DramaScript:
        """Attach the user's verbatim prompt, then hold the script to it.

        Both provider paths come through here, so the guarantees below apply
        to a script however it was written.
        """
        script.user_brief = (idea or "").strip()
        cls._apply_brief_gender(script)
        return script

    @staticmethod
    def _apply_brief_gender(script: DramaScript) -> None:
        """Write the brief's stated gender into a description that dropped it.

        A prompt instruction is not a guarantee. The brief said "she opens
        it" and the script came back describing a protagonist with no gender
        at all -- from there nothing downstream could recover it, and the
        render cast two men in a woman's story.

        Deliberately conservative, because guessing wrong is worse than not
        guessing: it only fills a description that states NO gender, only for
        the protagonist, and only when the brief itself is unambiguous. A
        character the model already gendered is left exactly as written, even
        if it disagrees with this reading of the brief -- the model saw the
        whole brief; this sees a word list.
        """
        wanted = gender_of.infer(script.user_brief)
        if not wanted:
            return
        noun = gender_of.noun(wanted)
        if not noun:
            return
        for char in script.characters or []:
            if (char.role or "").strip().lower() != "protagonist":
                continue
            if gender_of.infer(char.description):
                return  # already gendered by the writer — leave it alone
            described = (char.description or "").strip()
            char.description = f"{noun}, {described}" if described else noun
            logger.info(
                "Protagonist %r had no gender in its description; applied %r "
                "from the brief.",
                char.name,
                noun,
            )
            return

    async def _write_with_claude(
        self,
        idea: str,
        style: str,
        num_scenes: int,
        user_requirement: str,
        preset_characters: Optional[List[dict]] = None,
        language: str = DEFAULT_LANGUAGE,
        require_dialogue: bool = False,
    ) -> DramaScript:
        import anthropic

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

        # The official SDK, and streaming, both for the same reason: this used
        # to be a raw httpx POST with a flat 60s timeout and no retries. A
        # script this size takes most of a minute to generate, so a slow run
        # hit the deadline and a busy upstream (429/529) failed on the first
        # try -- and both surfaced to the user as "the script model is
        # unavailable". Streaming has no such deadline, and the SDK retries
        # 429/5xx with backoff on its own.
        #
        # Sonnet 5 runs adaptive thinking by default (Sonnet 4.6 did not when
        # `thinking` was omitted), so `content[0]` is a thinking block and the
        # script text is further down the list. The old code read
        # `content[0]["text"]` and died with `KeyError: 'text'` on every
        # single job -- see the type filter below, and never index the block
        # list by position again. Thinking stays on: it measurably improves
        # story structure, and `max_tokens` covers thinking plus text
        # together, which the raised budget above accounts for.
        client = anthropic.AsyncAnthropic(api_key=self.api_key, max_retries=2)
        try:
            async with client.messages.stream(
                model="claude-sonnet-5",
                max_tokens=self.MAX_SCRIPT_TOKENS,
                system=self._system_prompt(language, require_dialogue),
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                message = await stream.get_final_message()
        except anthropic.APIStatusError as exc:
            # The response body is where the API states the actual cause --
            # an expired key, an exhausted quota, a model the key can't reach.
            body = ""
            try:
                body = f" body={exc.response.text[:500]}"
            except Exception:
                pass
            logger.error(
                f"Anthropic screenwriter call failed: {type(exc).__name__}: "
                f"{exc} | status={exc.status_code} type={exc.type}{body}"
            )
            raise ScriptGenerationFailed(self._failure_message(exc)) from exc
        except Exception as exc:
            logger.error(
                f"Anthropic screenwriter call failed: "
                f"{type(exc).__name__}: {exc}"
            )
            # Deliberately NOT the template -- see write_script step 3.
            raise ScriptGenerationFailed(
                "The script model could not be reached, so your idea could "
                "not be turned into a script. No credits were spent — please "
                "try again shortly."
            ) from exc

        # A truncated response is not an outage: the model answered, the
        # budget ran out mid-JSON. Saying "unavailable" here sent operators
        # hunting for a dead API while the real fix was MAX_SCRIPT_TOKENS.
        if message.stop_reason == "max_tokens":
            logger.error(
                "Anthropic screenwriter response hit max_tokens "
                f"({self.MAX_SCRIPT_TOKENS}) and is truncated mid-JSON. "
                f"Raise MAX_SCRIPT_TOKENS or lower the scene count "
                f"(usage: {message.usage.output_tokens} output tokens)."
            )
            raise ScriptGenerationFailed(
                "The script came back longer than the limit and was cut off. "
                "No credits were spent — try again with fewer scenes."
            )
        if message.stop_reason == "refusal":
            logger.error(
                "Anthropic screenwriter declined the request: "
                f"{getattr(message.stop_details, 'category', None)}"
            )
            raise ScriptGenerationFailed(
                "This idea could not be turned into a script. No credits were "
                "spent — please try rephrasing it."
            )

        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            data = self._parse_json(text)
            return self._with_brief(DramaScript(**data), idea)
        except Exception as exc:
            # Include what came back: "No JSON found in response" on its own
            # gives an operator nothing to act on.
            logger.error(
                f"Anthropic screenwriter response could not be parsed: "
                f"{type(exc).__name__}: {exc} | stop_reason="
                f"{message.stop_reason} | first 500 chars: {text[:500]!r}"
            )
            raise ScriptGenerationFailed(
                "The script came back in a form we could not read. No credits "
                "were spent — please try again shortly."
            ) from exc

    @staticmethod
    def _failure_message(exc) -> str:
        """Turn an API status error into something the user can act on.

        Every one of these used to read "the script model is unavailable",
        which is true of an outage and misleading of everything else: a
        rate limit clears in a minute, and a bad key never clears at all
        but tells the user to "try again shortly" forever.
        """
        status = getattr(exc, "status_code", None)
        if status in (401, 403):
            # An operator problem. Say so plainly rather than implying the
            # user should retry into a wall.
            return (
                "The script service is not configured correctly, so nothing "
                "was generated. No credits were spent — please contact support."
            )
        if status == 429:
            return (
                "The script service is rate limited right now. No credits "
                "were spent — please wait a minute and try again."
            )
        return (
            "The script model is unavailable, so your idea could not be "
            "turned into a script. No credits were spent — please try "
            "again shortly."
        )

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
            user_brief=(idea or "").strip(),
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
