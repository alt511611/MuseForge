"""A second pair of eyes on the spoken lines of a freshly written script.

The screenwriter writes a story and fills a twenty-field schema in one call --
the "task coupling" Lei et al. (arXiv:2510.23163) blame for out-of-character,
on-the-nose dialogue. Measured here before this was written: six briefs of very
different kinds, each script written once by the production agent, then its
dialogue (and ONLY its dialogue) rewritten by a separate editor call; a judge of
another model family (Gemini 2.5 Pro) read both blind, in both orders. The
edited script won the overall verdict on 6 of 6 briefs, and won dialogue on 6 of
6. A two-stage "treatment first, then schema" variant, tried on the same briefs,
won only 4 of 6 and lost on fidelity to the brief, so it was not adopted.

Limits of that evidence: six briefs, one LLM judge, no human viewers. So the
edit is bounded -- it can change only the words of a line, never who speaks,
never how many lines a scene has, never the action -- and every failure returns
the original script untouched. ``MUSEFORGE_DIALOGUE_EDITOR=0`` turns it off.
It is skipped when the customer wrote the spoken lines themselves: those are
binding.

WHAT THE EDIT CHECKS, and where each check comes from. The first version asked
for natural, speakable lines with subtext. The editorial passes the 2026
script tools sell as separate features add three that fit inside the same call
and the same bounds:

* VOICE. A "character voice check" (ScriptFlo, Greenlight, Claude's own
  "character consistency tracking") asks whether each person sounds like
  themselves. The editor was never told who anyone was -- it saw names and
  lines -- so it could only make every line natural in the same voice. It now
  gets the cast's descriptions, and is told a line must not be swappable.
* ON THE NOSE. Detecting "dialogue that sounds too direct" (Inkshift) and
  "exposition in the dialogue" (listed as the commonest micro-drama mistake by
  Scenepaper) -- a character telling another what both already know.
* LENGTH. Vertical-drama formatting guides (Scenemixer) cap a single line at
  about twenty words: it is a subtitle on a phone, often read with the sound
  off. Enforced, not just asked for: an edited line over MAX_LINE_WORDS that
  is longer than the line it replaced is refused, and the draft line stays.

None of these was measured the way the first version was (six briefs, a blind
judge). They are bounded the same way -- words only, the draft survives any
failure -- so the worst an unhelpful check can do is leave a line as it was.
"""

from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_QUOTED = re.compile(r'["“”«»][^"“”«»]{3,}["“”«»]')

#: One spoken line, at most, in words. See the module docstring (LENGTH).
MAX_LINE_WORDS = 20

SYSTEM = (
    "You are a script editor for 30-second micro-dramas. You get a screenplay as JSON. "
    "Rewrite ONLY the spoken dialogue so it is natural, short, speakable and carries "
    "subtext: people rarely say what they mean, and a line never states the plot or the "
    "emotion outright. Keep each line's character and the number of lines per scene. "
    "Keep every concrete thing a line points at that the picture must show (an object, a "
    "light, a sound) -- say it differently, do not drop it. "
    "Make each character sound like THEMSELVES, from who the cast list says they are: "
    "their own vocabulary, rhythm and evasions, so no line could be handed to someone "
    "else unchanged. Cut exposition: a line that tells the other person what they both "
    "already know is said some other way or reduced to what they would actually say. "
    f"No line over {MAX_LINE_WORDS} words: it is also a subtitle on a phone. "
    "Reply with ONLY JSON: "
    '{"scenes": [{"dialogue": [{"character": "...", "line": "..."}]}]}'
)


def enabled() -> bool:
    return (os.environ.get("MUSEFORGE_DIALOGUE_EDITOR", "1") or "1").strip() != "0"


def customer_wrote_the_lines(*texts: str) -> bool:
    """A quoted run of words in the brief is a line the customer wants spoken."""
    return any(_QUOTED.search(t or "") for t in texts)


def _json_object(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError("the editor returned no JSON")
    return json.loads(match.group(0))


async def edit_dialogue(script, client, model: str):
    """The script with its dialogue edited, or the same script if anything is off."""
    scenes = [s for s in script.scenes if not isinstance(s, str)]
    if not scenes or not any(s.dialogue for s in scenes):
        return script
    view = [
        {"action": s.action, "turn": s.turn, "subtext": s.subtext,
         "dialogue": [d.model_dump() for d in s.dialogue]}
        for s in scenes
    ]
    # Who each speaker IS, so the voice check has something to check against.
    cast = [
        {"name": c.name, "description": c.description, "role": getattr(c, "role", "")}
        for c in (getattr(script, "characters", None) or [])
        if getattr(c, "name", "")
    ]
    try:
        message = await client.messages.create(
            model=model,
            max_tokens=3000,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps(
                {"title": script.title, "cast": cast, "scenes": view}
            )}],
            thinking={"type": "disabled"},
        )
        text = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
        revised = _json_object(text)["scenes"]
    except Exception as exc:  # an edit is a bonus; never cost the customer their script
        logger.warning("Dialogue editor skipped (%s): keeping the first draft.", exc)
        return script

    changed = 0
    for scene, new in zip(scenes, revised):
        lines = (new or {}).get("dialogue") or []
        if len(lines) != len(scene.dialogue):
            continue
        for old, nl in zip(scene.dialogue, lines):
            text = str((nl or {}).get("line") or "").strip()
            if not text or text == old.line:
                continue
            if (nl or {}).get("character", old.character) != old.character:
                continue
            words = len(text.split())
            if words > MAX_LINE_WORDS and words > len(old.line.split()):
                # Longer than the cap AND longer than the draft: the edit made
                # the subtitle worse, so the draft line stays.
                continue
            old.line = text
            changed += 1
    logger.info("Dialogue editor rewrote %d line(s).", changed)
    return script
