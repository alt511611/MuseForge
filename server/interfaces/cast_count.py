"""How many people the brief says are in the story, when it counts them.

"Three sailors" is three faces to cast. A screenwriter that lists one captain
and leaves "the sailors" to the scenes has not cast them: anyone who appears in
an action line without an entry in ``characters`` comes back as a different
stranger every shot, which is how a delivered three-sailor drama showed five.

This reads ONLY an explicit count in front of a person noun (English and
Turkish), because a wrong reading here costs a second model call and a changed
cast: "two years later" must never ask for two more characters. So the nouns
are a list, not a guess, and anything not on it is not a count.
"""

from __future__ import annotations

import re
from typing import Optional

_NUMBERS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6,
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
}

#: English people nouns, whole words (a prefix match would read "manager").
_PEOPLE_EN = {
    "sailor", "sailors", "man", "men", "woman", "women", "guard", "guards",
    "soldier", "soldiers", "friend", "friends", "brother", "brothers",
    "sister", "sisters", "kid", "kids", "child", "children", "worker",
    "workers", "thief", "thieves", "fisherman", "fishermen", "pirate",
    "pirates", "boy", "boys", "girl", "girls", "survivor", "survivors",
    "villager", "villagers", "hunter", "hunters", "climber", "climbers",
    "detective", "detectives", "officer", "officers", "student", "students",
    "teenager", "teenagers", "stranger", "strangers", "passenger",
    "passengers", "miner", "miners", "traveler", "travelers", "traveller",
    "travellers", "explorer", "explorers", "knight", "knights", "monk",
    "monks", "fighters", "fighter",
}

#: Turkish stems; a Turkish noun takes suffixes, so these match as prefixes.
_PEOPLE_TR = (
    "denizci", "adam", "erkek", "kadın", "kız", "asker", "arkadaş",
    "kardeş", "çocuk", "işçi", "hırsız", "balıkçı", "korsan", "gezgin",
    "avcı", "yolcu", "öğrenci", "madenci", "dağcı", "kurtulan", "bekçi",
    "muhafız", "polis", "dedektif", "savaşçı", "köylü",
)

_MAX_WANTED = 8


def _tokens(text: str) -> list:
    # Turkish dotted capital I lowercases to "i" + a combining dot.
    lowered = (text or "").lower().replace("i̇", "i")
    return re.findall(r"[^\W_]+", lowered)


def _is_person(token: str) -> bool:
    return token in _PEOPLE_EN or token.startswith(_PEOPLE_TR)


def counted_group(brief: str) -> int:
    """The largest explicit head-count in the brief, or 0.

    A count word must be followed within two words (one adjective: "three old
    sailors") by a person noun.
    """
    tokens = _tokens(brief)
    best = 0
    for i, token in enumerate(tokens):
        n = _NUMBERS.get(token)
        if not n:
            continue
        if any(_is_person(t) for t in tokens[i + 1 : i + 3]):
            best = max(best, n)
    return min(best, _MAX_WANTED)


def shortfall(brief: str, cast_size: int) -> int:
    """How many people the brief counted, when the cast lists fewer; else 0."""
    wanted = counted_group(brief)
    return wanted if wanted and cast_size < wanted else 0
