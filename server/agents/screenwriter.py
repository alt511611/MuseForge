"""Screenwriter agent — transforms an idea into a structured drama script."""

import asyncio
import json
import logging
import os
import re
from typing import Any, List, Optional

from interfaces import gender as gender_of
from interfaces.character import (
    CharacterProfile,
    DialogueLine,
    DramaScript,
    ScriptScene,
)
from interfaces.language import DEFAULT_LANGUAGE, is_default, name_of
from interfaces.lighting import GOES_DARK_PATTERNS
from interfaces.micro_drama import SCREENWRITER_CLAUSE, is_micro_drama
from interfaces.series import SCREENWRITER_CLAUSE as SERIES_CLAUSE
from interfaces.second_budget import (
    MAX_SCENE_SECONDS,
    MIN_SCENE_SECONDS,
    SECONDS_PER_CREDIT,
    spoken_words_for,
)
from tools.anthropic_request import classify, log_usage
from tools.claude_via_muapi import complete_via_muapi, is_muapi_llm_enabled

logger = logging.getLogger(__name__)


def _first_json_object(text: str) -> str:
    """The FIRST complete JSON object in `text`, brace-balanced.

    The old reading of this was `re.search(r"{[\s\S]*}", text)`, which is
    greedy: it runs from the first opening brace to the LAST closing one
    anywhere in the response. A model that answers with its script and then
    adds a second object -- a note, an alternative ending, a "here is the same
    thing with shorter scenes" -- had both of them, plus the prose between,
    handed to json.loads as one string, and the whole paid job failed on a
    script that was perfectly good.

    Braces inside strings do not count, and neither does an escaped quote,
    which is why this is a small scanner and not a bigger regex. Returns ""
    when there is no complete object.
    """
    start = text.find("{")
    if start == -1:
        return ""
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return ""


def _repair_json(text: str) -> str:
    """Remove the two things models put in JSON that JSON does not allow.

    Trailing commas before a closing brace or bracket, and `//` or `/* */`
    comments. Nothing else: this is a repair, not a parser, and a repair that
    starts guessing at missing quotes or unbalanced braces would eventually
    "fix" a truncated script into a plausible-looking one and render it.

    Written as a scanner rather than a regex because both edits are only valid
    OUTSIDE string values, and a line of dialogue is perfectly entitled to
    contain ``, }`` or ``//``. A regex cannot tell those apart; this can.
    """
    out: List[str] = []
    in_string = False
    escaped = False
    index = 0
    length = len(text)

    while index < length:
        char = text[index]

        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
            out.append(char)
            index += 1
            continue

        if char == "/" and index + 1 < length:
            nxt = text[index + 1]
            if nxt == "/":
                while index < length and text[index] != "\n":
                    index += 1
                continue
            if nxt == "*":
                end = text.find("*/", index + 2)
                index = length if end == -1 else end + 2
                continue

        if char in "}]":
            # Walk back over whitespace to find the previous meaningful
            # character; if it is a comma, it was trailing.
            back = len(out) - 1
            while back >= 0 and out[back].isspace():
                back -= 1
            if back >= 0 and out[back] == ",":
                del out[back]
        out.append(char)
        index += 1

    return "".join(out)


#: One spoken line per dramatic function, for the demo script only. Short on
#: purpose: they exist so the dialogue stages have something to run on, not to
#: be read as writing.
_TEMPLATE_LINES = {
    "setup": "It's quieter than I remember.",
    "inciting_incident": "That wasn't supposed to be there.",
    "rising_action": "We don't have time to be careful about it.",
    "turning_point": "Then it was never about the money.",
    "climax": "I'm not leaving without it.",
    "resolution": "We'll say it happened the other way.",
}


def _preset_block(preset_characters: Optional[List[dict]]) -> str:
    """The PRESET CHARACTERS section of the prompt, or "" when there is none.

    One function, because there were two copies and they had already drifted:
    one stripped and coerced with `or ""`, the other called `str()` on a
    missing name and put the literal word "None" in the prompt, which the
    writer then used as a character's name.
    """
    if not preset_characters:
        return ""
    lines = []
    for c in preset_characters:
        name = str(c.get("name") or "").strip()
        features = str(c.get("static_features") or "").strip()
        if name and features:
            lines.append(_preset_line(name, features, c.get("wardrobe")))
    if not lines:
        return ""
    return (
        "PRESET CHARACTERS (already exist — use directly, do not redefine):\n"
        + "\n".join(lines)
        + "\n"
    )


def _preset_line(name: str, features: str, wardrobe: Optional[str] = None) -> str:
    """One preset character, as the screenwriter is told about them.

    WITH the wardrobe. A preset character is one the user has already locked
    and is reusing, and this block is the only place the writer hears about
    them -- so listing a face and no clothes is an invitation to invent an
    outfit, which is then what the frame prompts restate all drama long. The
    reference portrait cannot correct it: it binds a face and never a costume
    (see CharacterProfile.wardrobe).
    """
    outfit = str(wardrobe or "").strip()
    if not outfit:
        return f"- {name}: {features}"
    return (
        f"- {name}: {features} | WARDROBE (locked, use verbatim in this "
        f"character's \"wardrobe\" field and do not restyle it): {outfit}"
    )


def _series_block(series_brief: str) -> str:
    """The continuity brief, as the writer of episode N reads it.

    FIRST in the prompt, ahead of the preset cast and the idea. An episode's
    idea is a suggestion for what happens next; what has already happened is
    not, and a model weights the opening of its prompt hardest.
    """
    brief = str(series_brief or "").strip()
    if not brief:
        return ""
    return f"SERIES CONTINUITY (binding — this episode continues it):\n{brief}\n\n"


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

SHOW THE BRIEF'S OWN VERBS. Every action the brief names is an event the film SHOWS, not
a state it may open in the aftermath of. A brief that says she FINDS a letter inside a
returned novel is a brief whose first scene is the finding — the book coming back over
the counter, the envelope in it, her face. Opening on her already reading it spends the
inciting incident off screen and leaves the drama with nothing to have caused it. The
same goes for the objects: a thing the brief makes the story turn on (an address on an
envelope, a key, a name) has to be something the camera looks at, in its own moment, or
the audience is asked to take the pipeline's word for it.

SPEND THE SCENES ON THE BRIEF. With only three to five of them, a scene invented around a
character the brief never mentions is a third of the film spent away from the story it
asked for. Add a character only when the brief's own action cannot happen without them.

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

That rule does not stop at the head, and a delivered drama proved it: a dock worker
described only as "a yellow hooded rain slicker with a reflective blue band across the
chest" kept her hood in all six shots — the part that was named — while the slicker
buttoned in one shot, zipped in the next and hung open in a third, went matte then
glossy, grew flap pockets then patch pockets then none, and put the band on her chest,
then her sleeves, then nowhere. So settle the GARMENT the same way you settled the head,
each in a phrase and not a paragraph: how it fastens, what pockets it has, what the
material looks like, and any badge or marking on it and where. Say what is on their
back too, or nothing will be there in one shot and a backpack in the next.

Describe a marking as a SHAPE, never as words to be read — "a blue reflective band across
the chest", "a square orange patch on the left breast", not "HARBOR OPS stencilled across
the back". The render cannot spell. Asked for stencilled lettering it delivered HAROB
across the back of a jacket in a two-second push-in, and FICST LOU on a name patch that is
on screen in every shot of the drama — and writing is the one thing in a frame a viewer
tries to read, so a misspelled word costs more than the plain patch it replaced.

WRITE THE WARDROBE FOR THE MODEL THAT READS IT. "description" and "wardrobe"
are not read by a person. They are pasted into the prompt for an image model,
once per frame, for every frame of the film -- which is why this brief already
tells you the render cannot spell. Two more things follow from the same fact.

Write what the clothes ARE, never what they are not. An image model has no
NOT: every noun in the prompt is a noun that was asked for, so "no hat" is the
most reliable way to get a hat, and "not a uniform" puts one in the frame.
"bare-headed" is the exception this brief already uses, because it names a
state of the head rather than an absent object -- follow that shape if you
need one.

Keep each field to a phrase per attribute. The frame prompt has a hard
character budget and the wardrobe is restated inside it for every character in
every shot; a paragraph here is paid for on every frame, out of the same
budget that the film's eyeline and continuity rules are the first to lose.

PRESET CHARACTERS in the user message already exist: do NOT redefine or rename them.
Use their exact names and visual descriptions, and weave them into the story. You may
add extra supporting characters only if needed.

Respond ONLY with valid JSON matching this schema:
{
  "title": "string",
  "logline": "string",
  "theme": "the controlling idea in one sentence",
  "visual_motif": "one recurring visual element restaged across scenes",
  "cliffhanger": "micro-drama mode ONLY: the unanswered question the last frame leaves - otherwise an empty string",
  "mood": "string",
  "estimated_duration_seconds": 30,
  "setting_location": "e.g. coastal village wooden pier",
  "setting_time_of_day": "e.g. sunset, night, midday",
  "setting_era": "e.g. present day, 1950s",
  "characters": [{
    "name": "string",
    "description": "gender and age FIRST, then face and build - no clothing",
    "wardrobe": "head down: headwear, garment + cut + colour, fastening, pockets, material, markings as SHAPES not words, anything carried",
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
      "world_change": "climax scene ONLY: what visibly changes about the place itself - otherwise an empty string",
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
    #:
    #: AND SO DO THE FIELDS NO VIEWER EVER READS, which is the harder half.
    #: "only the prose changes" used to be the whole of that instruction, and
    #: a model told to write a Turkish drama read it the way anyone would --
    #: as all of the prose. Delivered job 4631cc44-d30 went to flux-2-pro as
    #: "Character reference sheet of a woman, Sci-Fi style. otuzlu yaşlarının
    #: sonunda bi..." and to the location plate as "yağmurla ıslanmış kargo
    #: limanı, konteyner...". Nobody watching the film sees either sentence.
    #:
    #: It cost that job twice. FLUX conditions on T5, whose vocabulary is
    #: English-centric: this repo measures its own English prose at 3.98
    #: characters per token and that job's Turkish frames at 2.94, so the same
    #: description costs about 40% more of a 512-token window that the film's
    #: continuity rules are the first to be dropped from. Three of its frames
    #: ran the window out and the ladder had nothing optional left to give
    #: (see script2video._trim_to_token_window). The model also simply reads
    #: English better, so the more expensive description was the weaker one.
    LANGUAGE_CLAUSE = """

LANGUAGE. Write the drama in {language}. Every piece of text a viewer will
read or hear — "title", "logline", and every "line" of dialogue — must be in
{language}, natural and idiomatic, never a translation of an English sentence.
This holds even when the user's brief itself is written in another language.

WRITE THESE FIELDS IN ENGLISH, whatever the drama's language:
"setting_location", "setting_time_of_day", "setting_era", "mood", "theme",
"visual_motif", every character's "description" and "wardrobe", and every
scene's "emotion" and "world_change".

No viewer ever reads them. They are pasted straight into the prompts for the
image, video and music models, none of which is a person and all of which are
trained on English — they read {language} worse, and charge about 40% more
tokens for the same words out of a budget the film's own continuity rules are
the first to lose. A {language} "wardrobe" buys a poorer frame at a higher
price. Everything a viewer actually experiences stays in {language}.

The JSON field NAMES and the enum values ("protagonist", "climax", ...) stay
in English exactly as specified."""

    #: Appended to the system prompt when the job will actually VOICE the
    #: script (dialogue is enabled and paid for on this run).
    #:
    #: The base prompt tells the model that "silence is a legitimate choice",
    #: which is true of a silent film and wrong of a job the user switched
    #: dialogue on for: an all-silent script produces no voice tracks, no
    #: captions and — with music off — a master with no audio stream at all,
    #: which reads as the feature being broken rather than as a choice.
    #:
    #: That danger is a silent FILM, though, and this clause used to ban the
    #: silent SCENE to prevent it -- which costs a real dramatic instrument to
    #: buy a technical guarantee. A held look with no line in it is a choice a
    #: director makes; forbidding it outright means every beat is discharged
    #: through speech, which is the flattest way to play a scene.
    #:
    #: So: one scene may be silent, the rest must speak. The audio stream, the
    #: captions and the voice tracks all survive on the scenes that do speak,
    #: and the all-silent script the ban existed for is still banned -- and
    #: still caught downstream, where a script with no lines at all raises a
    #: warning on the finished job rather than shipping as if nothing happened.
    DIALOGUE_CLAUSE = """

SPOKEN DRAMA. This script WILL be voiced by actors, so it cannot be a silent film.
Every scene needs at least one line in its "dialogue" list, with ONE exception:
a single scene may have an empty dialogue list when silence is the dramatic point
of that scene — a look held instead of an answer, a door closed on a sentence
nobody finishes. Use it at most once in the whole drama, only where the silence is
doing the work speech would otherwise do, and say so in that scene's "subtext" so
the choice is legible. Never leave two scenes silent, and never leave a scene
silent because you could not think of a line.

Keep lines short, speakable and few (one to three per scene) — this is film
dialogue over a picture, not a radio play. The climax's stated event still has to
be SEEN, not merely narrated: never replace the event with a character describing
it.

A LINE IS NOT THE EVENT. Giving a character "The power's gone" does not make the
lights go out — it makes someone say so while the lamps stay on, which is what a
viewer sees and does not believe. This is the specific way a voiced script fails
that a silent one cannot, because dialogue offers an easy way to discharge the
brief without filming it. So on the scene where the event happens: "world_change"
names what the camera sees become different, the "action" shows it happening, and
the dialogue is what someone says WHILE it happens — a reaction, an order, a
half-finished sentence. Never a report of it, and never the only place it exists.

WRITE IT TO BE READ, TOO. Every line is spoken AND burned into the picture as a
subtitle, from the same string — so spell each word the way it should look on
screen and let the actor handle the saying of it. No pronunciation respellings, no
syllable hyphens, no phonetic spacing: write "fourteen-oh-two", never
"four-teen-oh-two"; "Route 7", never "Route seh-ven". A viewer who can hear the
line does not need it sounded out, and a viewer reading it sees a typo."""

    #: Appended when the job has BOUGHT lip sync.
    #:
    #: The sync provider is handed ONE combined audio file per scene and one
    #: face to drive with it. It cannot know that a second visible character
    #: takes over halfway through that file, so a two-hander sent to it puts
    #: one person's words in the other's mouth. That is why
    #: idea2video._has_one_visible_speaker refuses such a scene outright,
    #: before any provider is paid -- and the refusal is right.
    #:
    #: Nothing ever told the screenwriter that the shape mattered. Delivered
    #: job 532aa102-86f, three scenes, all three refused:
    #:
    #:     Scene 0 has multiple visible speakers in one combined dialogue
    #:     track; keeping it as voice-over instead of driving the wrong face.
    #:     ... Lip sync was charged for 3 scene(s), delivered on 0;
    #:     refunding 3 undelivered scene surcharge(s).
    #:
    #: The refund is correct and the film still played -- three scenes of
    #: closed mouths over voice-over, on a job that had asked and paid for the
    #: opposite. Job 4631cc44-d30 synced all three of ITS scenes a few hours
    #: earlier, with no code difference between the two runs: its second voice
    #: happened to be a dispatcher on a radio. Whether the feature the customer
    #: bought arrived at all was a property of the script's shape, settled by a
    #: writer who had never been told the shape was load-bearing.
    #:
    #: The escape hatch is one drama uses constantly and that job took by
    #: accident: put the second voice off-screen. It costs nothing -- the
    #: character is still in the scene and still in the story -- and
    #: _heard_but_never_seen reads exactly this staging (a radio, a handset,
    #: an intercom, an (O.S.)) to keep that speaker out of the frame's closed
    #: cast and off the 180-degree axis as well.
    LIPSYNC_CLAUSE = """

LIP SYNC. The mouths in this film will be animated to the voices, and that pass
is given ONE audio file per scene and ONE face to drive with it. So the dialogue
in any one scene belongs to ONE character who is visible in that scene.

A scene may still be an exchange. The second voice arrives from off-screen — over
a radio, a handset, an intercom, a phone, or called from the next room — and the
"action" stages it plainly ("Her radio crackles", "TOMAS (O.S.)"), which is what
keeps that speaker out of the frame and lets the visible character be the one
answering. Where a scene genuinely needs two people speaking face to face, split
it in two: each half its own scene, each with its own single speaker.

This is not a style preference. A scene written with two visible speakers is
dropped from the sync pass entirely and plays with unmoving mouths over
voice-over, on a film whose maker asked and paid for the opposite."""

    #: Appended LAST-but-one, for the same reason the micro-drama clause goes
    #: last: it contradicts the base prompt's "Build 3-5 scenes" and a model
    #: weighs a late override against what came before instead of averaging
    #: the two.
    #:
    #: The scene count was only ever a line in the USER message ("Scenes: 3"),
    #: which the base prompt's own range then argued with — and nothing
    #: downstream checked the answer. A three-scene job came back with five
    #: scenes and rendered a 60-second film, while /api/estimate had quoted
    #: and charged for three. That is the length the user chose, the runtime
    #: they paid for and the per-scene credit maths all disagreeing at once,
    #: so the count is stated as a hard constraint here and enforced after
    #: the fact in _hold_to_scene_count.
    #: What a scene IS, in seconds. The screenwriter was told how many scenes
    #: to write and never how long one lasts, so it wrote paragraphs: a
    #: delivered script's second scene crosses a flooded aisle, crouches at a
    #: lever, watches a light pulse with the character's breathing and takes a
    #: radio call -- four beats for a scene that is filmed as a single ten-
    #: second shot. The storyboard picks ONE of them and the other three never
    #: reach the picture, which the user has already read and approved.
    #:
    #: The numbers come from interfaces/second_budget so the brief the writer
    #: is given and the budget the pipeline enforces cannot drift apart.
    #:
    #: The LINE LENGTH half was missing, and the two halves have to be one
    #: clause because apart they contradict each other in practice. The writer
    #: was told a scene runs ten seconds, and told separately, under DIALOGUE,
    #: to "keep lines short and speakable". It obeyed both: job a8d0766b-421
    #: came back with 8.4 seconds of speech inside a 30-second drama, three
    #: scenes of [9, 9, 12] carrying [2.64, 2.16, 3.6]. Two thirds of the film
    #: was people standing still, and no stage downstream could fix it -- the
    #: budget is fixed before the script exists, and a take cannot be told to
    #: be shorter than the runtime the credit bought.
    RUNTIME_CLAUSE = """

WRITE TO THE RUNNING TIME. Each scene is about {seconds:.0f} seconds of finished
film ({minimum:.0f} at the shortest, {maximum:.0f} at the longest), and it is filmed as ONE
continuous shot from a single generated frame. So a scene is one beat, in one
place, that a viewer can watch happen in {seconds:.0f} seconds: an action begun and
completed, or a look that lands. Do NOT write a sequence of consecutive
actions in one scene -- crossing a yard, then kneeling, then reaching for a
lever, then answering a radio is four scenes' worth of film, and only the
first of them will be shot. Keep the "action" to what the camera can hold in
one take; anything else belongs in another scene or in the story you leave
out.

FILL THE RUNNING TIME WITH THE SCENE. A {seconds:.0f}-second scene holds roughly
{words} spoken words -- that is what {seconds:.0f} seconds of delivery actually is, and
"keep lines short" above means short SENTENCES, not a scene that stops talking
after three. A two-word line in a {seconds:.0f}-second take leaves eight seconds of
someone standing still, and nothing later in the pipeline can shorten the take
to hide it. If a scene genuinely has {words} words' worth to say, write them. If
it does not, make it a SILENT scene and let the action carry the whole {seconds:.0f}
seconds -- an empty dialogue list is a real choice. What does not work is the
middle: a sentence, then silence."""

    SCENE_COUNT_CLAUSE = """

SCENE COUNT IS FIXED. This drama has EXACTLY {count} scene{plural} — not
{minus_one}, not {plus_one}. The number is the length the user chose and paid
for, so it overrides the 3-5 range above and any instinct that the story needs
more room. Build the whole dramatic shape (including its climax) inside those
{count} scene{plural}: if the story feels bigger, compress it — merge beats
into a single scene rather than adding one."""

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
    #: Named once. It was written out at the call and again in the usage log,
    #: which is how a deployment ends up reporting spend against a model it is
    #: not running.
    MODEL = "claude-sonnet-5"
    #: Ceiling on draining one script stream. Generous -- a 24-scene script
    #: with thinking is a long answer -- but finite.
    SCRIPT_STREAM_TIMEOUT_SECONDS = 300.0

    def __init__(self, api_key: Optional[str] = None, demo: bool = False):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.muapi_key = os.environ.get("MUAPI_KEY", "")
        self.demo = demo
        self._anthropic_client: Any = None

    def _anthropic(self):
        """The Anthropic client for this agent, built once.

        A fresh AsyncAnthropic per script means a fresh connection pool per
        script: every job paid for a new TLS handshake, and nothing reused a
        warm connection. Built lazily so importing this module still works
        without the SDK installed, which the demo and template paths rely on.
        """
        if self._anthropic_client is None:
            import anthropic

            self._anthropic_client = anthropic.AsyncAnthropic(
                api_key=self.api_key, max_retries=2
            )
        return self._anthropic_client

    def _system_prompt(
        self,
        language: str = DEFAULT_LANGUAGE,
        require_dialogue: bool = False,
        narrative_mode: str = "",
        num_scenes: int = 0,
        is_episode: bool = False,
        lipsync_enabled: bool = False,
    ) -> str:
        """The system prompt for this drama's language, audio mode and length.

        English adds nothing to the language clause — the prompt is already
        written in it, and a redundant "write in English" clause only spends
        tokens.
        """
        prompt = self.SYSTEM_PROMPT
        if not is_default(language):
            prompt += self.LANGUAGE_CLAUSE.format(language=name_of(language))
        if require_dialogue:
            prompt += self.DIALOGUE_CLAUSE
        # Straight after the dialogue clause, because it constrains the thing
        # that clause has just asked for. Only when the sync was actually
        # bought: it costs the drama its face-to-face two-handers, and that is
        # not a price to charge a job which was never going to sync anyway.
        if lipsync_enabled:
            prompt += self.LIPSYNC_CLAUSE
        # Always, and before the scene count: a scene's LENGTH is a fixed fact
        # about the product (interfaces/second_budget), not something the
        # caller chooses, and it is the constraint the script is most often
        # written against without knowing.
        prompt += self.RUNTIME_CLAUSE.format(
            seconds=SECONDS_PER_CREDIT,
            minimum=MIN_SCENE_SECONDS,
            maximum=MAX_SCENE_SECONDS,
            words=spoken_words_for(SECONDS_PER_CREDIT),
        )
        if num_scenes > 0:
            prompt += self.SCENE_COUNT_CLAUSE.format(
                count=num_scenes,
                plural="" if num_scenes == 1 else "s",
                minus_one=num_scenes - 1,
                plus_one=num_scenes + 1,
            )
        # LAST, deliberately: it contradicts the base prompt's dramatic curve
        # and its demand for a resolution, and a model weighs a late override
        # against what came before instead of blending the two into a shape
        # that is neither (see interfaces/micro_drama).
        if is_micro_drama(narrative_mode):
            prompt += SCREENWRITER_CLAUSE
        # After the micro-drama clause and last of all, for the same reason it
        # is late: an episode of a running series has to contradict the
        # instinct every fresh prompt produces -- introduce these people,
        # establish this place -- and the viewer of episode nine has met them
        # eight times (see interfaces/series).
        if is_episode:
            prompt += SERIES_CLAUSE
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
        narrative_mode: str = "",
        #: What has already happened in this series, if this is an episode of
        #: one (interfaces/series.continuity_brief). Facts, not rules: the
        #: rules ride in the system prompt, where a model reads them as
        #: instruction rather than as material.
        series_brief: str = "",
        #: Whether this job bought lip sync, which constrains who may speak in
        #: a scene -- see LIPSYNC_CLAUSE.
        lipsync_enabled: bool = False,
    ) -> DramaScript:
        # Demo mode must stay fast and free of real network calls --
        # matches MuAPIImageGenerator/MuAPIVideoGenerator's demo behavior.
        if self.demo:
            return self._write_template(
                idea,
                style,
                num_scenes,
                preset_characters,
                narrative_mode,
                require_dialogue=require_dialogue,
            )

        preset_block = _preset_block(preset_characters)

        prompt = (
            f"{_series_block(series_brief)}"
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
                    self._system_prompt(
                        language,
                        require_dialogue,
                        narrative_mode,
                        num_scenes,
                        bool(series_brief),
                        lipsync_enabled=lipsync_enabled,
                    ),
                    prompt,
                    max_tokens=self.MAX_SCRIPT_TOKENS,
                )
                return self._with_brief(
                    DramaScript(**self._parse_json(content)), idea, num_scenes
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
                narrative_mode,
                series_brief,
                lipsync_enabled=lipsync_enabled,
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
    def _with_brief(
        cls, script: DramaScript, idea: str, num_scenes: int = 0
    ) -> DramaScript:
        """Attach the user's verbatim prompt, then hold the script to it.

        Both provider paths come through here, so the guarantees below apply
        to a script however it was written.
        """
        script.user_brief = (idea or "").strip()
        cls._apply_brief_gender(script)
        # BEFORE _apply_brief_event, so the event is restored onto a scene
        # that is still in the film. Run the other way round, a script whose
        # extra scenes are cut could lose the restored world_change with them.
        cls._hold_to_scene_count(script, num_scenes)
        cls._apply_brief_event(script)
        return script

    #: Scenes that carry the drama's shape and must survive a trim. A cut that
    #: takes the climax does not shorten the film, it removes the reason it
    #: exists.
    _LOAD_BEARING_FUNCTIONS = {"climax", "resolution"}

    @classmethod
    def _hold_to_scene_count(cls, script: DramaScript, num_scenes: int) -> None:
        """Cut a script back to the number of scenes the user asked for.

        The count reaches the model as a prompt line and, since
        SCENE_COUNT_CLAUSE, as an explicit constraint — but a prompt
        instruction is not a guarantee, and this one is load-bearing in a way
        the others are not. /api/estimate quotes and charges per scene, the
        runtime budget is per scene, and the plan ceiling is per scene: a
        three-scene job that renders five is billed for three, runs 60 seconds
        instead of ~36, and spends two scenes' worth of generation the user
        never bought. Observed exactly that way on a delivered drama.

        Only ever TRIMS. A script that came back SHORT is left alone and
        logged: padding it means inventing drama, which is the screenwriter's
        job and not a repair's, and a short film is at worst less than the
        user paid for rather than an unbilled overrun.

        Which scenes go: the lowest-tension ones first, skipping the climax,
        the resolution and any scene that declares a ``world_change`` — those
        three are what the rest of the pipeline reads to build the story's
        shape and its one sanctioned lighting break. If protecting them would
        leave more scenes than asked for, the protection yields (the count is
        the promise) and the lowest-tension scene goes regardless.
        """
        scenes = list(script.scenes or [])
        if num_scenes <= 0 or len(scenes) <= num_scenes:
            if 0 < len(scenes) < num_scenes:
                logger.warning(
                    "Screenwriter returned %s scenes for a %s-scene job; "
                    "keeping the short script rather than inventing beats.",
                    len(scenes),
                    num_scenes,
                )
            return

        def _tension(scene) -> int:
            return int(getattr(scene, "tension", 0) or 0)

        def _protected(scene) -> bool:
            function = (getattr(scene, "dramatic_function", "") or "").strip().lower()
            if function in cls._LOAD_BEARING_FUNCTIONS:
                return True
            return bool((getattr(scene, "world_change", "") or "").strip())

        dropped = 0
        while len(scenes) > num_scenes:
            candidates = [s for s in scenes if not _protected(s)]
            # Everything left is load-bearing and there are still too many of
            # them: the count wins, because it is the thing the user chose and
            # was charged for.
            if not candidates:
                candidates = scenes
            victim = min(candidates, key=_tension)
            scenes.remove(victim)
            dropped += 1

        logger.warning(
            "Screenwriter returned %s scenes for a %s-scene job; dropped the "
            "%s lowest-tension non-climax scene(s) so the film matches the "
            "length that was quoted and charged for.",
            len(script.scenes or []),
            num_scenes,
            dropped,
        )
        # Scaled rather than recomputed from a per-scene constant: the writer's
        # own estimate carries its pacing, and only the number of scenes it was
        # spread over has changed. Left as it was, it would keep quoting the
        # length of the script that was just cut.
        original_count = len(script.scenes or []) or 1
        script.estimated_duration_seconds = max(
            1,
            round(
                int(script.estimated_duration_seconds or 0) * len(scenes) / original_count
            ),
        )
        script.scenes = scenes

    #: A flood is WATER arriving. Without that subject the word is ordinary
    #: weather and ordinary metaphor: the same delivered script has Mara
    #: crossing "the flooded aisle" and the container's "light floods out
    #: across the flooded dock" -- three uses, none of them an event, and
    #: between them enough matches to make the real climax unreadable.
    _WATER = r"(?:water|seawater|sea|river|tide|waves?|surge|storm ?surge)"

    #: Unmistakable, world-SCALE changes of state, matched against the brief,
    #: grouped by the CHANGE they describe. Deliberately short and blunt: this
    #: list decides whether a scene gets to break the drama's locked lighting,
    #: so a false positive is expensive and a miss costs only what the product
    #: already does today. Ambiguous verbs are left out on purpose -- "burns"
    #: is as often a candle as a warehouse, and "stops" is usually a person.
    #:
    #: The grouping is what lets "has the film already got the brief's event?"
    #: be a real question rather than "is the field filled?". A script that
    #: declares a world_change of its own passes the second test whatever it
    #: says -- and a writer given a container that hums with light will happily
    #: declare the container's own glow. The brief's blackout is then never
    #: restored, the locked lighting is broken for a spill of blue instead, and
    #: the film's whole reason for existing stays off screen.
    _WORLD_EVENT_FAMILIES = {
        # Imported, not restated. The frame prompt asks the same question of
        # the same words -- "does this event put the lights out?" -- to decide
        # whether the setting line's own lamps may still light the frame, and
        # two copies of this list were never going to stay in step. See
        # interfaces.lighting.extinguishes_light.
        "blackout": GOES_DARK_PATTERNS,
        "flood": (
            rf"\b{_WATER}\b[^.;]{{0,40}}?\bfloods?\b",
            rf"\bfloods?\b[^.;]{{0,40}}?\b{_WATER}\b",
            r"\bsu bas\w+",
        ),
        "explosion": (r"explodes?", r"patlar|patlıyor"),
        "collapse": (r"collapses?", r"çöker|çöküyor"),
    }

    _WORLD_EVENT_CUES = tuple(
        cue for cues in _WORLD_EVENT_FAMILIES.values() for cue in cues
    )

    @classmethod
    def _apply_brief_event(cls, script: DramaScript) -> None:
        """Put the brief's stated event back when the script dropped it.

        `world_change` is the only field that lets a scene break the drama's
        locked lighting, so a script that leaves it empty can never show a
        blackout however well the rest is written. Observed twice: a brief
        whose whole point was "the city's power dies the moment she opens it"
        came back with the lights on both times -- the second time with a
        character SAYING the power was gone, which is the failure the voiced
        script makes easy.

        This does not invent an event. It copies the user's own clause into
        the field that exists to carry it, and only when the film does not
        already have it: a script that declared the SAME change is left alone,
        because the model read the whole brief and this reads a word list.

        "The same change", not "any change at all". That was the third way
        this failed, delivered against a brief reading "...a shipping
        container that hums with light, and the city's power dies the moment
        she opens it": the writer declared the container's own blue spill as
        the world_change -- fair, and visibly rendered -- which was enough to
        stand this down, and the city's power never went out in any frame of
        the film. A filled field is not the same fact as a filmed event.
        """
        all_scenes = list(script.scenes or [])
        # Only scenes that can CARRY a world_change are candidates to receive
        # one. Reading the spoken event, further down, uses every scene: a
        # scene that cannot hold the field can still contain the line that
        # says the event happened.
        scenes = [s for s in all_scenes if hasattr(s, "world_change")]
        if not scenes:
            return
        declared = [
            text for s in scenes if (text := (s.world_change or "").strip())
        ]

        clause = cls._world_event_clause(script.user_brief)
        source = "brief"
        if clause:
            # The brief named the event, so "did the writer fill the field in?"
            # is the wrong question -- the right one is whether the film films
            # THIS event. Delivered against the brief "a shipping container
            # that hums with light, and the city's power dies the moment she
            # opens it": the harbour's lamps, floodlights and lit containers
            # burn through all three scenes, and the only blackout in the film
            # is a caption reading "city's out!". The one thing that DID break
            # the locked lighting was the container's own blue spill -- a
            # world_change the writer was entitled to declare, and one that
            # silenced the recovery for the change the user actually asked for.
            #
            # So the test is by FAMILY: a declared change that describes the
            # same event leaves the script alone, and anything else does not
            # count as having filmed it.
            family = cls._event_family(clause)
            if any(cls._event_family(text) == family for text in declared):
                return
        elif declared:
            # No event in the brief and the writer named one of their own:
            # exactly the case this has always left alone. The model read the
            # whole story; this reads a word list.
            return
        if not clause:
            # The brief did not state it -- but the SCRIPT may have, in the
            # one place a voiced drama makes easiest and the picture never
            # reads: a line of dialogue. Delivered example, three scenes, no
            # world_change anywhere, the climax spoken as "Denny -- Denny, see
            # this? The grid just--" and rendered under every streetlight,
            # container lamp and lit doorway in the yard. The event of the
            # film was audible and invisible.
            #
            # Same word list and the same refusal to guess as the brief path:
            # this reads what the writer already wrote, into the field that
            # exists to carry it.
            clause, source = cls._script_event_clause(all_scenes), "script"
        if not clause:
            return
        target = next(
            (s for s in scenes if (s.dramatic_function or "").strip().lower() == "climax"),
            scenes[-1],
        )
        # ADDED to whatever the climax already declared, never over it. The
        # writer's own change is a real thing that happens in their scene (a
        # hatch swinging open, a container lighting up), and the frame prompt
        # renders the whole state it is given -- so the honest instruction is
        # both, in the order the story has them.
        existing = (target.world_change or "").strip().rstrip(";,. ")
        target.world_change = f"{existing}; {clause}" if existing else clause
        logger.info(
            "The %s's own event was not in any scene's world_change%s; "
            "restored it onto the %s scene: %r",
            source,
            f" (the script declared {declared!r} instead)" if declared else "",
            (target.dramatic_function or "last").strip() or "last",
            clause,
        )

    @classmethod
    def _event_family(cls, text: str) -> str:
        """Which world-scale change ``text`` describes, or "" for none.

        Read from the same cue list the extraction uses, so the two answers
        cannot drift apart. Deliberately NARROW: a phrasing this does not
        recognise reads as "the event is not in the film", which adds the
        brief's own clause to the climax -- repetitive at worst. The opposite
        error, calling an unrelated change a blackout, is what leaves the
        film's event off screen, and that is the failure this exists for.
        """
        for family, cues in cls._WORLD_EVENT_FAMILIES.items():
            if any(re.search(cue, text or "", re.IGNORECASE) for cue in cues):
                return family
        return ""

    @classmethod
    def _script_event_clause(cls, scenes) -> str:
        """The drama's own stated change of world, read from what it says.

        Looks at each scene's action and its spoken lines. Deliberately the
        same shape as _world_event_clause: exactly one matching clause across
        the whole script, or nothing -- two matches mean the drama describes
        more than one change and choosing between them is a judgement a word
        list has no business making.
        """
        found = []
        for scene in scenes:
            texts = [str(getattr(scene, "action", "") or "")]
            for line in getattr(scene, "dialogue", None) or []:
                spoken = (
                    line.get("line") if isinstance(line, dict)
                    else getattr(line, "line", "")
                )
                if spoken:
                    texts.append(str(spoken))
            for text in texts:
                clause = cls._world_event_clause(text)
                if clause and clause not in found:
                    found.append(clause)
        return found[0] if len(found) == 1 else ""

    @classmethod
    def _world_event_clause(cls, brief: str) -> str:
        """The one clause of the brief that states a change to the world.

        Returns "" unless EXACTLY one clause matches: two matches mean the
        brief describes more than one change and picking between them is a
        judgement this cannot make, so it defers rather than guesses.
        """
        text = " ".join((brief or "").split())
        if not text:
            return ""
        clauses = [c.strip(" ,;—-") for c in re.split(r"[.;—]|,\s*and\b|\band\b", text)]
        hits = [
            clause
            for clause in clauses
            if clause
            and any(re.search(cue, clause, re.IGNORECASE) for cue in cls._WORLD_EVENT_CUES)
        ]
        return hits[0] if len(hits) == 1 else ""

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

        "Unambiguous" is read by gender_of.infer_brief, not by infer: a brief
        introduces a CAST, and the first gendered word in one belongs to
        whoever the sentence reaches first. On "...realises the man across the
        table is copying her own tell" that is the antagonist, and filling the
        protagonist's description from it would have made a woman a man.
        """
        wanted = gender_of.infer_brief(script.user_brief)
        if not wanted:
            return
        noun = gender_of.noun(wanted)
        if not noun:
            return
        for char in script.characters or []:
            if (char.role or "").strip().lower() != "protagonist":
                continue
            if gender_of.infer(char.description):
                # `continue`, not `return`: a two-hander with two protagonists
                # (which this product writes) stopped the whole pass at the
                # first one the writer had already gendered, and the second
                # stayed genderless -- the exact case this exists to repair.
                continue  # already gendered by the writer — leave it alone
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
        narrative_mode: str = "",
        series_brief: str = "",
        lipsync_enabled: bool = False,
    ) -> DramaScript:
        import anthropic

        preset_block = _preset_block(preset_characters)
        prompt = (
            f"{_series_block(series_brief)}"
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
        client = self._anthropic()
        try:
            async with client.messages.stream(
                model=self.MODEL,
                max_tokens=self.MAX_SCRIPT_TOKENS,
                system=self._system_prompt(
                    language,
                    require_dialogue,
                    narrative_mode,
                    num_scenes,
                    bool(series_brief),
                    lipsync_enabled=lipsync_enabled,
                ),
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                # A deadline, because a stream that stalls has no other one:
                # the SDK's request timeout covers establishing the response,
                # not draining it, so a connection that goes quiet mid-script
                # held the job open until the pipeline's own hard timeout.
                message = await asyncio.wait_for(
                    stream.get_final_message(),
                    timeout=self.SCRIPT_STREAM_TIMEOUT_SECONDS,
                )
        except anthropic.APIStatusError as exc:
            # _failure_message already sorts what the USER is told by status.
            # This sorts what the OPERATOR is told, which was one line for
            # every status: the body is where the API states the actual cause
            # -- an expired key, an exhausted quota, a model the key cannot
            # reach -- and `retryable` is the part a log reader acts on.
            failure = classify(exc)
            logger.error(
                "Anthropic screenwriter call failed (%s, %s): %s",
                failure.kind,
                "worth retrying" if failure.retryable else "will not fix itself",
                failure.detail,
            )
            raise ScriptGenerationFailed(self._failure_message(exc)) from exc
        except anthropic.APIConnectionError as exc:
            # Covers APITimeoutError. Separated from the bare handler below
            # because "could not be reached" is TRUE here and was being said
            # about every unexpected exception in this block as well -- an
            # outage message printed over a bug in our own code.
            logger.error(
                "Anthropic screenwriter call never reached the API "
                "(%s): %s", type(exc).__name__, exc
            )
            # Deliberately NOT the template -- see write_script step 3.
            raise ScriptGenerationFailed(
                "The script model could not be reached, so your idea could "
                "not be turned into a script. No credits were spent — please "
                "try again shortly."
            ) from exc
        except Exception as exc:
            logger.exception(
                "Anthropic screenwriter call raised an unexpected %s -- this "
                "is not an API failure", type(exc).__name__
            )
            raise ScriptGenerationFailed(
                "Something went wrong turning your idea into a script. No "
                "credits were spent — please try again shortly."
            ) from exc

        log_usage("screenwriter", self.MODEL, getattr(message, "usage", None))

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
            return self._with_brief(DramaScript(**data), idea, num_scenes)
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
        """Read the model's script, forgiving the ways models write JSON.

        Strictness here is not rigour, it is waste. A delivered failure:

            JSONDecodeError: Expecting property name enclosed in double quotes:
            line 31 column 5 | stop_reason=end_turn

        ``end_turn`` means the model finished its answer. The script was
        complete and correct -- a title, a theme, a cast, five scenes -- and
        the whole job was failed, and the user told to try again, over ONE
        stray comma about two thirds of the way down.

        So a strict parse is tried first and, only when it fails, the response
        is repaired for the small set of things language models actually do
        (trailing commas, `//` notes to themselves) and parsed again. The
        repair is logged: models getting worse at this is something an
        operator should be able to see, not something that silently costs
        retries.
        """
        body = _first_json_object(text)
        if not body:
            # Two different failures, said differently: nothing that looks like
            # JSON at all, versus an object that starts and never closes --
            # which is what a response cut off at max_tokens looks like, and is
            # worth naming rather than reporting as "no JSON".
            if "{" in text:
                raise ValueError(
                    "JSON object in response is unterminated (the answer looks "
                    "truncated)"
                )
            raise ValueError("No JSON found in response")
        try:
            return json.loads(body)
        except json.JSONDecodeError as strict_error:
            repaired = _repair_json(body)
            if repaired == body:
                raise
            try:
                data = json.loads(repaired)
            except json.JSONDecodeError as repair_error:
                # Both messages, because they point at different things: the
                # first says what the model actually got wrong, the second says
                # what the repair left behind. Reporting only the second turns
                # every bad script into the same unhelpful line.
                logger.error(
                    "Script JSON did not parse and the repair did not help. "
                    "Original: %s. After repair: %s",
                    strict_error.msg, repair_error.msg,
                )
                raise repair_error from strict_error
            logger.warning(
                "Script JSON needed repair before it would parse (%s). The "
                "model's answer was usable; only its punctuation was not.",
                strict_error.msg,
            )
            return data

    def _write_template(
        self,
        idea: str,
        style: str,
        num_scenes: int,
        preset_characters: Optional[List[dict]] = None,
        narrative_mode: str = "",
        require_dialogue: bool = False,
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
        # The micro-drama shape opens ON the shock and refuses to resolve --
        # the opposite curve, not a shortened version of the same one (see
        # interfaces/micro_drama). The template has to know it too: a key-less
        # run that quietly produces a three-act film is a run that ignored the
        # mode the caller asked for.
        micro_shapes = {
            2: ["inciting_incident", "climax"],
            3: ["inciting_incident", "setup", "climax"],
            4: ["inciting_incident", "setup", "rising_action", "climax"],
            5: [
                "inciting_incident",
                "setup",
                "rising_action",
                "turning_point",
                "climax",
            ],
        }
        micro = is_micro_drama(narrative_mode)
        table = micro_shapes if micro else shapes
        shape = table[max(2, min(num_scenes, 5))]
        # ...and the curve that goes with it: a shock, a fall, then the climb.
        micro_tensions = {
            "inciting_incident": 9,
            "setup": 5,
            "rising_action": 7,
            "turning_point": 8,
            "climax": 10,
        }
        # The demo's own speaker: whoever the cast has, or the name pulled out
        # of the idea. A demo run asked for dialogue and got a silent script,
        # so every stage downstream that only exists when somebody speaks --
        # the voice cast, the subtitle pass, the mouths -- was untestable
        # without spending real provider money.
        speaker = characters[0].name if characters else protagonist
        scenes = []
        for fn in shape:
            beat = dict(beats.get(fn) or beats["rising_action"])
            if micro:
                beat["tension"] = micro_tensions.get(fn, beat.get("tension", 5))
            # Into the copy rather than as a second keyword: `**beat` would
            # collide with a literal `dialogue=` the moment a beat carries one.
            beat["dialogue"] = (
                [DialogueLine(character=speaker, line=_TEMPLATE_LINES[fn])]
                if require_dialogue and fn in _TEMPLATE_LINES
                else []
            )
            scenes.append(ScriptScene(dramatic_function=fn, **beat))

        return DramaScript(
            generated_by="template",
            user_brief=(idea or "").strip(),
            title=title,
            logline=idea,
            theme="A choice made too late still counts as a choice.",
            visual_motif="light through a window, falling differently in each scene",
            mood=style.lower(),
            # The same seconds-per-credit the rest of the product quotes and
            # bills in (interfaces/second_budget); 8 was a second, older answer
            # to the same question.
            estimated_duration_seconds=len(scenes) * SECONDS_PER_CREDIT,
            setting_location="generic cinematic location",
            setting_time_of_day="midday",
            setting_era="present day",
            characters=characters,
            scenes=scenes,
            # Micro-drama ends on the question, and the field that carries it
            # is what the next episode is commissioned from -- a demo run that
            # left it empty could not exercise a series at all.
            cliffhanger="What happens after the choice?" if micro else "",
        )

    def _extract_protagonist(self, idea: str) -> str:
        for word in idea.split():
            cleaned = re.sub(r"[^a-zA-Z]", "", word)
            if cleaned and cleaned[0].isupper() and len(cleaned) > 2:
                return cleaned
        return "Alex"
