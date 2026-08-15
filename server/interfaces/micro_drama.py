"""The micro-drama shape: open on the shock, end on the question.

A three-act film and a vertical micro-drama are not the same object told at
different lengths. A film earns its opening; a feed does not give it the
chance — the first two seconds decide whether the rest exists. And a film
resolves, while a micro-drama's last frame is the reason anyone opens the next
one.

So the default dramatic curve this pipeline writes to (tension rising to a
climax and settling into a resolution) is exactly wrong for the format:

    cinematic     setup -> rising -> climax -> resolution
    micro_drama   SHOCK -> how we got here -> rising -> reveal, and cut

This module holds that shape in one place, because it is enforced in three:
the screenwriter's prompt, the deterministic template behind it, and the cut
itself (the cold open is assembled from footage the climax already paid for).

Nothing here costs a generation. The teaser is a second and a half of a clip
that already exists, shown twice — which is what a flash-forward IS.
"""

from __future__ import annotations

import os
from typing import Optional

from interfaces.language import DEFAULT_LANGUAGE, normalize

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}

CINEMATIC = "cinematic"
MICRO_DRAMA = "micro_drama"

#: How much of the climax is shown up front. Long enough to register a face
#: and an action, short enough that it reads as a glimpse rather than as the
#: scene being played out of order.
COLD_OPEN_SECONDS = 1.5

#: The card that follows it. Under a second and the viewer cannot read it;
#: much over and the film has stopped moving before it started.
TITLE_CARD_SECONDS = 1.0

#: What the card says.
#:
#: Deliberately NOT "12 HOURS EARLIER", which is the convention: this pipeline
#: has no idea how much time the story spans, and a specific number contradicts
#: a script that covers ten minutes. The generic form does the same job -- it
#: tells the viewer the shock they just saw has not happened yet.
_CARD_TEXT = {
    "tr": "DAHA ÖNCE",
    "en": "EARLIER",
    "es": "ANTES",
    "de": "ZUVOR",
    "fr": "PLUS TÔT",
    "it": "PRIMA",
    "pt": "ANTES",
    "ru": "РАНЕЕ",
    "ar": "قبل ذلك",
}


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in TRUTHY:
        return True
    if raw in FALSY:
        return False
    return default


def resolve_mode(requested: Optional[str] = None) -> str:
    """Which narrative shape this drama is written to.

    An explicit request wins; otherwise MUSEFORGE_NARRATIVE_MODE decides, and
    the default stays cinematic so nothing changes for existing deployments.
    """
    value = (requested or "").strip().lower()
    if value in (CINEMATIC, MICRO_DRAMA):
        return value
    env = os.environ.get("MUSEFORGE_NARRATIVE_MODE", "").strip().lower()
    return MICRO_DRAMA if env == MICRO_DRAMA else CINEMATIC


def is_micro_drama(mode: Optional[str] = None) -> bool:
    return resolve_mode(mode) == MICRO_DRAMA


def is_cold_open_enabled() -> bool:
    """Whether to put a glimpse of the climax at the very front.

    On by default IN MICRO-DRAMA MODE only (the caller checks the mode first):
    it is the format's defining move, it costs nothing, and a micro-drama
    without a hook is a micro-drama nobody watches past its first second.
    """
    return _flag("MUSEFORGE_COLD_OPEN", True)


def card_text(language: str = DEFAULT_LANGUAGE) -> str:
    """The title card, in the drama's own language.

    Falls back to English rather than to nothing: a card in the wrong language
    still tells the viewer that time has moved, while no card at all makes the
    teaser read as a continuity error.
    """
    return _CARD_TEXT.get(normalize(language or DEFAULT_LANGUAGE), _CARD_TEXT["en"])


#: Appended to the screenwriter's system prompt in micro-drama mode.
#:
#: It has to CONTRADICT the base prompt in two places -- the rising curve and
#: the resolution -- so it is worded as an override and placed last, where a
#: model weighs it against what came before rather than merging the two into a
#: shape that is neither.
SCREENWRITER_CLAUSE = """

MICRO-DRAMA FORM. This is not a short film; it is an episode in a vertical
feed, and the rules above about dramatic shape are REPLACED by these:

OPEN ON THE WORST MOMENT. Scene 1 is not a setup. It is the shock — the slap,
the accusation, the document on the table, the sentence that cannot be taken
back — and it happens in the first line, not after an establishing beat. Give
scene 1 a "tension" of 8 or higher. A viewer who is not gripped by your first
scene never sees your second.

THEN FALL, THEN CLIMB. After the opening shock the tension DROPS (scene 2 is
how this became possible) and climbs again to the reveal. Your tension values
should look like 9, 5, 7, 10 — not 3, 5, 7, 9.

NO RESOLUTION. Do NOT write a "resolution" scene, and do not let the last
scene settle, explain or console. The final scene ends ON the reveal: the
truth said out loud, the door opening, the name spoken. Set its
"dramatic_function" to "climax".

END ON THE QUESTION. Set "cliffhanger" to the unanswered question the last
frame leaves in the viewer's mind, in one sentence ("whose child is it", "who
was standing in the doorway"). The last line of dialogue should provoke that
question rather than answer it. A drama that ties itself off has no reason for
anyone to come back."""
