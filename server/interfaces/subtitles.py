"""Subtitle typesetting: the rules broadcast has and generated video does not.

Delivered captions from this pipeline, measured:

    52  Mira Kess: Sal, you seeing this? That one's glowing.
    58  Sal Okafor: Probably a bad seal light. Log it and move on.
    72  Mira Kess: It's already been called in a hundred times. Nobody's coming.

Every one of those is a single unwrapped line, up to 1.7x the maximum a
broadcast subtitle is allowed to be, with a speaker name on it that no
professional subtitle would carry. It is not that they are hard to read; it is
that they are *recognisably* the output of a machine, which is the same tell
as a flat face or an unducked score.

The conventions below are the ones the EBU and the streaming platforms
converged on, and they exist for measured reasons rather than taste:

* **42 characters a line, two lines.** Past that the eye stops reading the
  line and starts scanning it, and the caption competes with the picture it
  is supposed to serve.
* **17 characters a second.** A cue the viewer cannot finish is a cue that
  taught them nothing and covered the shot anyway.
* **Break where the sentence breaks.** A line split before its verb makes the
  reader hold half a clause across a line change; splitting after the comma
  costs nothing and reads as prose.
* **Name the speaker only when the picture cannot.** Broadcast identifies a
  speaker when they are off screen or ambiguous, never as a matter of course.
  On a two-shot it is twelve characters of a forty-two character budget spent
  telling the viewer what they are looking at.

Pure text in, pure text out: no timing, no ffmpeg, no pipeline. What this
module decides can be read in a test.
"""

from __future__ import annotations

import os
import re
from typing import List

#: Characters per line, and lines per cue. Two lines is the ceiling everywhere
#: -- a third covers enough of a vertical frame to hide the shot.
MAX_LINE_CHARS = 42
MAX_LINES = 2

#: Reading speed, in characters a second, for the adult subtitle standard.
#: Used to decide when a line has to become two CUES rather than two lines.
MAX_CHARS_PER_SECOND = 17.0

#: A cue shorter than this reads as a flicker even when its words are short.
#:
#: There is no matching ceiling, and there does not need to be one: a cue is
#: split at MAX_LINE_CHARS * MAX_LINES characters (split_into_cues), so at
#: MAX_CHARS_PER_SECOND the longest legal cue reads in about five seconds.
MIN_CUE_SECONDS = 0.85

#: Sentence-final punctuation, in the languages this product ships in.
_SENTENCE_END = tuple(".!?…:;")

#: Clause boundaries, ranked below sentence ends but above everything else.
_CLAUSE_END = tuple(",—–")

#: Words a line should break BEFORE rather than after: they open the clause
#: that follows them, so stranding one at the end of a line leaves the reader
#: holding an unfinished thought across the break. Turkish included because
#: the drama is written in the language the user asked for.
_BREAK_BEFORE = {
    # English
    "and", "but", "or", "so", "because", "if", "when", "while", "that",
    "which", "who", "than", "as", "for", "with", "to", "of", "in", "on",
    # Turkish
    "ve", "ama", "ya", "veya", "çünkü", "ki", "eğer", "ama", "fakat",
    "diye", "gibi", "için", "ile",
}

TRUTHY = {"1", "true", "yes", "on"}


def speaker_labels_enabled() -> bool:
    """Whether to prefix every cue with the speaker's name.

    OFF, and this is the one convention here that looks like a removal rather
    than an improvement, so it is worth being explicit: a subtitle names its
    speaker when the picture cannot -- an off-screen voice, a crowd, a
    narrator. A two-hander staged around whoever is talking does not need it,
    and on a 42-character line "Sal Okafor: " is more than a quarter of the
    budget spent describing what the viewer is already looking at.

    Kept switchable because a deployment producing accessibility subtitles
    (rather than burned-in captions for a feed) has the opposite requirement:
    SDH names every speaker by design.
    """
    return os.environ.get("MUSEFORGE_SPEAKER_LABELS", "").strip().lower() in TRUTHY


def format_speaker(character: str) -> str:
    """The speaker prefix for SDH-style captions, empty when labels are off."""
    name = (character or "").strip()
    if not name or not speaker_labels_enabled():
        return ""
    return f"{name}: "


def reading_seconds(text: str) -> float:
    """How long this text needs on screen to be read at all."""
    stripped = re.sub(r"\s+", " ", (text or "").strip())
    if not stripped:
        return 0.0
    return max(MIN_CUE_SECONDS, len(stripped) / MAX_CHARS_PER_SECOND)


def _break_score(words: List[str], at: int) -> int:
    """How good a line break after ``words[:at]`` is. Higher is better."""
    if at <= 0 or at >= len(words):
        return -1
    previous = words[at - 1]
    following = words[at]
    if previous.endswith(_SENTENCE_END):
        return 3
    if previous.endswith(_CLAUSE_END):
        return 2
    if following.strip("\"'([").casefold() in _BREAK_BEFORE:
        return 1
    return 0


def wrap_cue(text: str, max_chars: int = MAX_LINE_CHARS) -> str:
    """Lay one cue out over at most two lines, breaking where prose breaks.

    Among the breaks that FIT, the best-scoring one wins, and ties go to the
    most balanced pair of lines -- a caption whose first line runs to the
    margin and whose second holds two words reads as a mistake even when both
    lines are legal.
    """
    words = re.sub(r"\s+", " ", (text or "").strip()).split(" ")
    if not words:
        return ""
    if len(" ".join(words)) <= max_chars:
        return " ".join(words)

    best = None
    for at in range(1, len(words)):
        top = " ".join(words[:at])
        bottom = " ".join(words[at:])
        if len(top) > max_chars or len(bottom) > max_chars:
            continue
        # Prefer a real break; then the most even split; then, all else equal,
        # the shorter line on top, which is the house style everywhere.
        key = (_break_score(words, at), -abs(len(top) - len(bottom)), -len(top))
        if best is None or key > best[0]:
            best = (key, f"{top}\n{bottom}")
    if best:
        return best[1]

    # Too long for two lines even at their limit. The caller is expected to
    # have split it into separate cues already (see split_into_cues); this is
    # the backstop, and it breaks as late as it can rather than dropping words.
    top: List[str] = []
    while words and len(" ".join(top + [words[0]])) <= max_chars:
        top.append(words.pop(0))
    if not top:  # a single word longer than a whole line
        top.append(words.pop(0))
    return f"{' '.join(top)}\n{' '.join(words)}" if words else " ".join(top)


def split_into_cues(
    text: str,
    max_chars: int = MAX_LINE_CHARS,
    max_lines: int = MAX_LINES,
) -> List[str]:
    """One line of dialogue as one or more cues, each of legal size.

    A long line becomes several cues rather than one crowded one, split at
    sentence ends where it has them -- which is what a subtitler does, and why
    a two-sentence line of dialogue turns into two captions rather than four
    lines of text.
    """
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return []
    budget = max_chars * max_lines
    if len(cleaned) <= budget:
        return [cleaned]

    # Sentence boundaries first: they are the only splits that need no
    # judgement at all.
    sentences = [s for s in re.split(r"(?<=[.!?…])\s+", cleaned) if s]
    cues: List[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > budget:
            cues.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        cues.append(current)

    # A single sentence can still be over budget; split it on words.
    final: List[str] = []
    for cue in cues:
        while len(cue) > budget:
            words = cue.split(" ")
            head: List[str] = []
            while words and len(" ".join(head + [words[0]])) <= budget:
                head.append(words.pop(0))
            if not head:
                head.append(words.pop(0))
            final.append(" ".join(head))
            cue = " ".join(words)
        if cue:
            final.append(cue)
    return final
