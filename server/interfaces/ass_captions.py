"""Kinetic captions: the word lights up as it is spoken.

Vertical drama is watched muted. Not "sometimes" -- as the default, on a feed,
with the sound off until something earns it, which means the captions are not
an accessibility layer here, they are the dialogue. A block of white text
sitting still for four seconds is the same information delivered in a way
nobody watches.

The convention that works is two or three words at a time, timed to the voice,
with the word currently being said picked out. libass does exactly this with
karaoke timing (``\\k``), which is why the output here is ASS rather than the
SRT the pipeline burns by default: SRT has no way to say "this word, now".

Everything here is TIMED, never estimated. The word times come from the voice
provider's own character alignment (tools/elevenlabs_voice_generator's
``_word_timings``), so a highlight lands on the word being spoken or the line
gets no highlight at all. A karaoke caption whose emphasis is on the wrong
word is worse than a plain one: it reads as a broken player rather than as a
style choice.

Nothing in this module touches ffmpeg or the filesystem -- it returns a
document, so it can be tested as text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

#: Words on screen at once. Three is about what the eye takes in a single
#: fixation at phone reading distance; four starts to be read rather than
#: seen, which defeats the point.
WORDS_PER_CUE = 3

#: Caption height as a fraction of the frame's SHORTER side. Larger than the
#: broadcast-style default the SRT path uses (4.5%): this style is meant to be
#: read at arm's length on a phone, and it carries fewer words per line.
HEIGHT_FRACTION = 0.062

#: ...and the emphasised word grows on top of that.
EMPHASIS_SCALE = 118

#: Distance from the bottom of the frame, as a fraction of height. Higher than
#: the SRT path's 11%: kinetic captions are the focus, and a feed's own UI
#: (progress bar, handle, caption text) crowds the bottom of a vertical video.
BOTTOM_MARGIN_FRACTION = 0.17

SIDE_MARGIN_FRACTION = 0.07

#: &HAABBGGRR -- ASS colours are BGR with an inverted alpha, which is the
#: single most common way to get this file wrong.
WHITE = "&H00FFFFFF"
#: What a word looks like BEFORE it is spoken: the same white, dimmed. Not a
#: different hue -- a colour change per word turns a caption into a rainbow.
DIM = "&H50FFFFFF"
#: The emphasis colour, for the words the scene actually turns on.
ACCENT = "&H0025E1FF"
OUTLINE = "&HC0000000"

#: A word this short is a preposition, not a plot point; emphasising it makes
#: the effect look automatic, which it is, and should not look.
MIN_EMPHASIS_CHARS = 4

#: How many leading characters two words must share to count as the same word.
#: Turkish is agglutinative -- "boşanıyoruz", "boşanma" and "boşandık" are the
#: same news -- so an exact match would emphasise almost nothing in the
#: language this product is mostly used in.
STEM_CHARS = 5


@dataclass
class CaptionWord:
    text: str
    start: float
    end: float


@dataclass
class CaptionCue:
    """One burst of words, with the timings that animate them."""

    start: float
    end: float
    words: List[CaptionWord] = field(default_factory=list)
    #: Plain text, used when a cue has no per-word timing to animate.
    text: str = ""


def _stem(word: str) -> str:
    cleaned = "".join(ch for ch in word.casefold() if ch.isalnum())
    return cleaned[:STEM_CHARS]


def emphasis_stems(*sources: str) -> set:
    """Word stems worth shouting, taken from the scene's own turn.

    The screenwriter already names what changes in a scene ("she finally says
    the child is not his"), and that sentence is where its shocking words are.
    Deriving emphasis from it costs nothing and stays in whatever language the
    drama is written in -- a hardcoded list of trigger words ("divorce",
    "pregnant") would work for English and for no other language this product
    sells.
    """
    stems = set()
    for source in sources:
        for word in (source or "").split():
            stem = _stem(word)
            if len(stem) >= min(MIN_EMPHASIS_CHARS, STEM_CHARS):
                stems.add(stem)
    return stems


def chunk_into_cues(
    words: Sequence[Dict],
    words_per_cue: int = WORDS_PER_CUE,
) -> List[CaptionCue]:
    """Group timed words into bursts, breaking at sentence ends."""
    cues: List[CaptionCue] = []
    current: List[CaptionWord] = []

    def _flush():
        if current:
            cues.append(
                CaptionCue(
                    start=current[0].start,
                    end=current[-1].end,
                    words=list(current),
                )
            )
            current.clear()

    for raw in words or []:
        current.append(
            CaptionWord(
                text=str(raw.get("text") or ""),
                start=float(raw.get("start") or 0.0),
                end=float(raw.get("end") or 0.0),
            )
        )
        ends_sentence = current[-1].text.rstrip()[-1:] in {".", "!", "?", "…", ":"}
        if len(current) >= words_per_cue or ends_sentence:
            _flush()
    _flush()
    return cues


def _timestamp(seconds: float) -> str:
    """H:MM:SS.cc, ASS's format.

    Rounded to centiseconds FIRST and split afterwards. Splitting first and
    rounding the remainder is how 59.999 becomes "0:00:60.00" -- a timestamp
    libass reads as a minute and a zero, which silently shifts every cue after
    it by a minute.
    """
    total_centis = int(round(max(0.0, float(seconds)) * 100))
    centis = total_centis % 100
    total_seconds = total_centis // 100
    hours, remainder = divmod(total_seconds, 3600)
    minutes, whole = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{whole:02d}.{centis:02d}"


def _escape(text: str) -> str:
    """ASS treats braces as override blocks and newlines as literal \\N."""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("{", "(")
        .replace("}", ")")
        .replace("\r\n", " ")
        .replace("\n", " ")
    )


def build_header(width: int, height: int) -> str:
    """Script info and the one style every cue uses.

    PlayRes is set to the real frame size so every number below is a PIXEL
    rather than a fraction of libass's default 384x288 canvas -- the scaling
    trap the SRT path has to work around (see build_caption_style).
    """
    short_side = min(width, height) or 1080
    font_size = max(12, int(round(short_side * HEIGHT_FRACTION)))
    margin_v = max(0, int(round(height * BOTTOM_MARGIN_FRACTION)))
    margin_h = max(0, int(round(width * SIDE_MARGIN_FRACTION)))
    # Outline scaled to the type: a fixed 2px vanishes at 1080 wide and
    # smothers the letters at 320.
    outline = max(2, int(round(font_size * 0.10)))
    shadow = max(0, int(round(font_size * 0.04)))
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "WrapStyle: 2",
            "ScaledBorderAndShadow: yes",
            f"PlayResX: {int(width)}",
            f"PlayResY: {int(height)}",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            # PrimaryColour is the SPOKEN colour and SecondaryColour the
            # not-yet-spoken one: \k fills from secondary to primary, which is
            # the reverse of how the names read.
            f"Style: Kinetic,DejaVu Sans,{font_size},{WHITE},{DIM},{OUTLINE},"
            f"&H00000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,"
            f"{margin_h},{margin_h},{margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text",
        ]
    )


def _render_cue(cue: CaptionCue, emphasis: Optional[set] = None) -> str:
    """One Dialogue line, with per-word karaoke timing and emphasis."""
    emphasis = emphasis or set()
    if not cue.words:
        return f"{{\\fad(80,80)}}{_escape(cue.text)}"

    parts: List[str] = ["{\\fad(80,80)}"]
    for index, word in enumerate(cue.words):
        # \k takes CENTISECONDS and applies to the run that follows it.
        centis = max(1, int(round((word.end - word.start) * 100)))
        # The gap before a word belongs to the word: without it the highlight
        # runs ahead of the voice by however long the speaker paused.
        if index == 0:
            lead = 0.0
        else:
            lead = max(0.0, word.start - cue.words[index - 1].end)
        if lead > 0.02:
            parts.append(f"{{\\k{int(round(lead * 100))}}} ")
        elif index > 0:
            parts.append(" ")
        stem = _stem(word.text)
        if stem and stem in emphasis and len(stem) >= MIN_EMPHASIS_CHARS:
            parts.append(
                f"{{\\k{centis}\\c{ACCENT}\\fscx{EMPHASIS_SCALE}"
                f"\\fscy{EMPHASIS_SCALE}}}{_escape(word.text)}"
                f"{{\\c{WHITE}\\fscx100\\fscy100}}"
            )
        else:
            parts.append(f"{{\\k{centis}}}{_escape(word.text)}")
    return "".join(parts)


def build_ass(
    cues: Sequence[CaptionCue],
    width: int,
    height: int,
    emphasis: Optional[set] = None,
) -> str:
    """A complete ASS document, or "" when there is nothing to show."""
    if not cues:
        return ""
    lines = [build_header(width, height)]
    for cue in cues:
        end = cue.end if cue.end > cue.start else cue.start + 0.8
        lines.append(
            f"Dialogue: 0,{_timestamp(cue.start)},{_timestamp(end)},Kinetic,,"
            f"0,0,0,,{_render_cue(cue, emphasis)}"
        )
    return "\n".join(lines) + "\n"
