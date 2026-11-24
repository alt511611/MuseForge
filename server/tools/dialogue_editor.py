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
"""

from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_QUOTED = re.compile(r'["“”«»][^"“”«»]{3,}["“”«»]')

SYSTEM = (
    "You are a script editor for 30-second micro-dramas. You get a screenplay as JSON. "
    "Rewrite ONLY the spoken dialogue so it is natural, short, speakable and carries "
    "subtext: people rarely say what they mean, and a line never states the plot or the "
    "emotion outright. Keep each line's character and the number of lines per scene. "
    "Keep every concrete thing a line points at that the picture must show (an object, a "
    "light, a sound) -- say it differently, do not drop it. Reply with ONLY JSON: "
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
    try:
        message = await client.messages.create(
            model=model,
            max_tokens=3000,
            system=SYSTEM,
            messages=[{"role": "user", "content": json.dumps({"title": script.title, "scenes": view})}],
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
            if text and text != old.line and (nl or {}).get("character", old.character) == old.character:
                old.line = text
                changed += 1
    logger.info("Dialogue editor rewrote %d line(s).", changed)
    return script
