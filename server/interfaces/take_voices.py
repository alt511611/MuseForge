"""Which of the BACKEND'S OWN voices each character speaks in.

The cast exists so a character is the same person in every scene. Half of that
was built and half was not: the locked portrait carries the face through a
whole drama, and then a take with native audio picks its own voice per
generation, so the same woman can be two different people across a cut. Job
6f857aa0-903 shipped exactly that -- one locked portrait, three scenes, three
rolls of the model's own dice.

The endpoint's element takes a ``voice_id`` from the backend's library and
there is nowhere to upload a sample (tools/falai_video_generator, and the note
on MUSEFORGE_VOICE_PROVIDER in .env.example). So keeping the cast through a
speaking take is not a TTS problem at all. It is this: choose one id per
character, the same one every time, and bind it to their element.

WHY THE CATALOGUE IS EMPTY HERE. Because the ids are not ours to write down.
The provider does not publish the list of valid values, and this codebase has
already paid twice for guessing at one: .env.example records a voice_id that
failed AFTER five scenes were generated, with "Invalid voice parameter", and
the element field is worse than that -- a value the library does not hold is
not an error at all, it is a silent substitution, which is the delivered
drama speaking in a voice nobody chose. A guessed catalogue would turn a
known, logged gap into an invisible one.

So the catalogue is read from the deployment, which is the only place the
answer can be true: fill it with ``tools/probe_take_voices`` and put what came
back accepted into MUSEFORGE_TAKE_VOICE_IDS. Empty -- the default -- casts
nobody and leaves the picture choosing its own voices exactly as before, with
the warning that says so still in the log. This module never invents an id and
never passes on one it cannot see in the catalogue.
"""

import hashlib
import os
from typing import Any, Dict, FrozenSet, Iterable, Optional, Tuple

from interfaces import gender as gender_of

#: Ids the deployment has verified, comma separated. The gendered variants
#: fall back to the shared list, so a deployment that has only checked WHICH
#: ids work -- not who they sound like -- still casts consistently, just
#: without the gender match.
SHARED_ENV = "MUSEFORGE_TAKE_VOICE_IDS"
FEMALE_ENV = "MUSEFORGE_TAKE_FEMALE_VOICE_IDS"
MALE_ENV = "MUSEFORGE_TAKE_MALE_VOICE_IDS"


def _ids(variable: str) -> Tuple[str, ...]:
    """The ids in one environment variable, in the order they were written.

    Order is load-bearing: casting walks the pool from a hashed offset, so a
    reordered list re-casts the whole ensemble. Duplicates are dropped rather
    than left to collide with the walk that skips voices already taken.
    """
    seen: Dict[str, None] = {}
    for part in (os.environ.get(variable, "") or "").split(","):
        cleaned = part.strip()
        if cleaned:
            seen.setdefault(cleaned, None)
    return tuple(seen)


def catalogue() -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """``(female, male)`` pools, read at CALL time rather than at import.

    At import the value is fixed by whatever the environment happened to hold
    when the module was first touched, which is a fine way to make a test pass
    and a bad way to run a worker whose configuration is reloaded.
    """
    shared = _ids(SHARED_ENV)
    return (_ids(FEMALE_ENV) or shared, _ids(MALE_ENV) or shared)


def known_ids() -> FrozenSet[str]:
    """Every id this deployment has declared, of either gender."""
    female, male = catalogue()
    return frozenset(female) | frozenset(male)


def _pool(gender: str) -> Tuple[str, ...]:
    """The voices a character of this gender may be cast from.

    An UNGENDERED character is cast from both pools rather than skipped, which
    is where this parts company with the TTS path. There, a character with no
    gender falls through to a per-line hash and still gets a consistent voice
    (tools/elevenlabs_voice_generator._assign). Here there is no per-line
    anything: an element with no voice_id is the model choosing again on every
    generation, which is the exact failure this module exists to close. A
    consistent voice of an uncertain gender is the better of the two -- and
    the gender markers are the same ones the FACE was drawn from
    (interfaces/gender), so a description that left it open left it open for
    the picture too.
    """
    female, male = catalogue()
    if gender == gender_of.FEMALE:
        return female or male
    if gender == gender_of.MALE:
        return male or female
    merged: Dict[str, None] = {}
    for voice in female + male:
        merged.setdefault(voice, None)
    return tuple(merged)


def _describe(character: Any) -> str:
    return str(
        getattr(character, "static_features", "")
        or getattr(character, "description", "")
        or ""
    )


def cast(
    characters: Iterable[Any],
    locked: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """One voice per named character, keyed by their DISPLAY name.

    Keyed by the display name because that is what the element is built with
    (script2video: ``voice_ids.get(name, "")``), unlike the TTS path's
    casefolded keys -- a lookup that silently misses here does not raise, it
    ships a take whose voice was chosen by the model.

    The assignment rules are the ones the TTS cast already uses, and
    deliberately so: a deterministic hash of the name picks the starting
    offset, then the walk takes the first voice nobody else in this drama
    holds. Two characters sharing a voice inside one film is the collision
    worth spending a worse-matched voice to avoid; across films it does not
    matter, so the hash keeps a lone protagonist on the same voice forever.

    ``locked`` is a returning character's voice, decided by an earlier episode
    and carried on their library entry. It is applied first and it is
    VALIDATED, which the TTS path has no need to do: that field holds whichever
    provider's id was current when the character was saved, and an ElevenLabs
    id bound to a Kling element is not a wrong voice, it is an unknown one --
    substituted in silence. An id the catalogue does not list is therefore
    dropped here and the character is cast fresh, which is the recoverable
    direction: a voice that changes between episodes is visible, and a voice
    that was never in the library is not.

    Returns {} when the catalogue is empty, which is the untouched behaviour:
    no element carries a voice_id and the picture chooses, as it always did.
    """
    known = known_ids()
    if not known:
        return {}

    cast_by_name: Dict[str, str] = {}
    taken = set()
    for name, voice_id in (locked or {}).items():
        display = str(name or "").strip()
        voice = str(voice_id or "").strip()
        if display and voice in known:
            cast_by_name[display] = voice
            taken.add(voice)

    for character in characters or []:
        name = str(getattr(character, "name", "") or "").strip()
        if not name or name in cast_by_name:
            continue
        pool = _pool(gender_of.infer(f"{name} {_describe(character)}"))
        if not pool:
            continue
        digest = hashlib.sha256(name.casefold().encode("utf-8")).digest()
        start = int.from_bytes(digest[:4], "big") % len(pool)
        chosen = pool[start]
        for offset in range(len(pool)):
            candidate = pool[(start + offset) % len(pool)]
            if candidate not in taken:
                chosen = candidate
                break
        cast_by_name[name] = chosen
        taken.add(chosen)

    return cast_by_name
