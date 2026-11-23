"""A speaker's name, and what the screenwriter wrote beside it.

A script marks a voice the film does not show by writing the marker into the
name: ``Yusuf (O.S.)``, ``Anlatıcı (V.O.)``. Every place that compares a
speaker with a character -- who is on screen, who has a voice, whose mouth the
lip-sync provider is asked to drive -- compared the whole string, so
``Yusuf (O.S.)`` was a stranger to ``Yusuf`` and, worse, a SECOND visible
speaker in his own scene.

Delivered job 5b886720 (2026-11-23): four scenes, each with a line marked
(O.S.) or (V.O.), and every one of them was refused lip-sync with "multiple
visible speakers in one combined dialogue track" -- Deniz alone on screen in an
85 mm close-up, Yusuf's (O.S.) line heard over it. The writer had said, in the
script's own notation, exactly that this voice is not in the frame.

Two answers, kept apart because they are different questions:

* ``speaker_key`` -- WHO: the name with the marker removed, casefolded, so
  ``Yusuf (O.S.)`` and ``Yusuf`` are the same person.
* ``is_marked_unseen`` -- WHETHER THEIR MOUTH IS ON SCREEN: True when the
  writer marked this line as off-screen or voice-over.
"""
import re

_MARKER = r"o\.?\s?s\.?|v\.?\s?o\.?|off[\s-]?screen|voice[\s-]?over"
#: One trailing "(O.S.)" / "[V.O.]" / "(off-screen)" / "(voice over)". Anchored
#: to the END of the name, and only a bracketed marker: a character called
#: "Oscar" or "Vo" is not touched.
_TRAILING = re.compile(rf"\s*[\(\[]\s*(?:{_MARKER})\s*[\)\]]\s*$", re.IGNORECASE)


def _split(name) -> tuple:
    text = str(name or "").strip()
    marked = False
    while True:
        stripped = _TRAILING.sub("", text)
        if stripped == text:
            return text, marked
        text, marked = stripped.strip(), True


def speaker_key(name) -> str:
    """The speaker's name without any (O.S.)/(V.O.) marker, casefolded."""
    return _split(name)[0].casefold()


def is_marked_unseen(name) -> bool:
    """Whether the script marked this speaker as heard-not-seen on this line."""
    return _split(name)[1]
