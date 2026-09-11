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
* **A cue does not outlive its shot.** Subtitling practice holds cues inside
  the shot they belong to, because a caption that survives a cut is read as
  belonging to whoever the new shot is pointing at. Delivered 30-second drama
  10e143bb: "I wrote you a letter once." came up at 22.54s over the woman who
  says it, the picture cut to the man listening at 25.50s, and her line stayed
  on his face for another 1.83 seconds.

Almost all of it is pure text in, pure text out -- no ffmpeg, no pipeline --
and the one function that is not (fit_cues_to_shots) still takes numbers and
returns numbers. What this module decides can be read in a test.
"""

from __future__ import annotations

import os
import re
from typing import List, Sequence, Tuple

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

#: Tokens whose trailing full stop is part of the WORD, not the end of a
#: sentence. Without this list a caption breaks in the middle of a name.
#:
#: Delivered job 4c7bbe85-e5c, the line "Play your cards, Mr. Voss.": the
#: karaoke path splits one sentence at a time and divides each evenly, so
#: five words should have come out 3 + 2. "Mr." ended in a full stop, so it
#: was read as the end of a sentence -- and the second "sentence" was the
#: single word "Voss.", which went to screen alone for a third of a second.
#: MIN_WORDS_PER_CUE exists to stop exactly that, and could not help: from
#: inside the chunker this was not an orphan, it was a complete sentence that
#: happened to be one word long, which is the one case the floor is relaxed
#: for ("Run.").
#:
#: Titles are the common case in a drama, because a title is how one character
#: addresses another. Turkish included alongside English for the same reason
#: _BREAK_BEFORE is: it is the language most of these films are written in.
_ABBREVIATIONS = {
    # English titles and the handful of abbreviations dialogue actually uses.
    "mr", "mrs", "ms", "dr", "prof", "st", "sgt", "lt", "capt", "col",
    "gen", "rev", "hon", "jr", "sr", "mt", "no", "vs", "etc", "inc", "ltd",
    # Turkish
    "dr", "prof", "doç", "av", "sn", "bay", "bn", "yrd", "öğr", "gör",
    "vb", "bkz", "örn",
}


def ends_sentence(token: str) -> bool:
    """Whether ``token`` closes a sentence, rather than merely ending in a dot.

    Shared by both caption paths -- the broadcast SRT wrapper below and the
    karaoke ASS chunker -- because a boundary the two disagree about is a
    caption that breaks differently depending on which style is switched on.

    Two things are not sentence ends despite the punctuation: a known
    abbreviation ("Mr.", "Dr."), and a single initial ("J. Voss"), which no
    list can enumerate.

    The failure this refuses is asymmetric, which is why the doubt resolves
    toward "not a sentence": a missed boundary merges two cues that could have
    been separate, and the reader loses nothing. A false boundary strands a
    word on screen by itself.
    """
    text = (token or "").rstrip()
    if not text:
        return False
    if text[-1] not in _SENTENCE_END:
        return False
    if text[-1] != ".":
        # "!", "?", "…", ":" and ";" are never part of a word.
        return True
    body = text[:-1].strip("\"'([)]").casefold()
    if not body:
        return False
    if body in _ABBREVIATIONS:
        return False
    # A single initial: "J.", "A." -- and "J.R." style runs, whose segments
    # are all one letter.
    if all(len(part) == 1 for part in body.split(".") if part):
        return False
    return True

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
    if ends_sentence(previous):
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


def fit_cues_to_shots(
    durations: Sequence[float],
    windows: Sequence[Tuple[float, float]],
    gap: float = 0.0,
    fill: bool = False,
) -> List[Tuple[float, float]]:
    """Each line's cue placed inside the SHOT that line is spoken in.

    ``durations[i]`` is how long line i needs, ``windows[i]`` is the (start,
    end) of the shot it is said in, and the answer is one (start, end) per
    line in the same clock as the windows. Lines that share a shot are laid
    out inside it in order, with ``gap`` between them, scaled down together
    when they do not fit -- the same trade the scene-wide layout makes, made
    against a shot instead. ``fill`` stretches them to the shot as well as
    shrinking them to it, which is right for exactly one case and it is the
    case this exists for: a scene voiced by its own take is speaking for its
    whole length, so a line's shot is how long that line is being said.

    WHY A SHOT AND NOT THE SCENE. Until a scene could cut inside itself
    (interfaces/scene_take) the two were the same window, so laying a scene's
    cues across a scene was laying them across its only shot. A one-take scene
    is several framings of one clip, and a cue whose length is an ESTIMATE --
    which is what a scene voiced by its own take has, there being one
    recording and no per-line measurement in it -- lands across those framings
    at random. Delivered drama 10e143bb: "I wrote you a letter once." came up
    at 22.54s over the woman saying it, the picture cut to the man listening
    at 25.50s, and her line stayed on his face for 1.83 seconds more. A reader
    attributes a caption to whoever is on screen under it; the film therefore
    reads as him saying he wrote her a letter, which is the opposite of the
    scene.

    The take already knows the answer -- scene_take._spread_dialogue decides
    which beat says which line before the take is generated -- so nothing here
    is guessed. This only spends what that decision already worked out.
    """
    placed: List[Tuple[float, float]] = [(0.0, 0.0)] * len(durations)
    by_shot: dict = {}
    for index, window in enumerate(windows):
        if index < len(durations):
            by_shot.setdefault((float(window[0]), float(window[1])), []).append(index)

    for (start, end), members in by_shot.items():
        span = max(0.0, end - start)
        needed = sum(max(0.0, float(durations[i])) for i in members)
        needed += gap * max(0, len(members) - 1)
        if needed <= 0:
            continue
        scale = span / needed if (fill or needed > span) else 1.0
        cursor = start
        for index in members:
            finish = min(end, cursor + max(0.0, float(durations[index])) * scale)
            placed[index] = (cursor, finish)
            cursor = finish + gap * scale
    return placed
