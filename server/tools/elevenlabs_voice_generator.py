"""Character dialogue straight from ElevenLabs, no reseller in between.

Why this exists. The same feature runs through MuAPI's
``elevenlabs-text-to-dialogue-v3``, and that endpoint refuses the voices its
own playground publishes. Delivered logs, one drama, every spelling tried::

    Invalid voice parameter: XB0fDUnXU5powFXDhCwa   (its id)
    Invalid voice parameter: Charlotte - Clear      (its published label)
    Invalid voice parameter: Charlotte              (its name)

``XB0fDUnXU5powFXDhCwa`` is on the list that endpoint's own model page offers.
No cast we pick can satisfy a validator that rejects its own catalogue, so the
reseller is the thing to remove.

Three things get better by going direct, and only the first is about money:

  * VOICES ARE ENUMERABLE. ``GET /v1/voices`` answers what this account may
    use. Every voice failure in this product's history came from guessing at a
    list nobody published; that guessing ends here (see ``list_voices``).
  * TIMINGS ARE REAL. ``/v1/text-to-dialogue/with-timestamps`` returns a
    ``voice_segments`` entry per input with ``start_time_seconds`` and
    ``end_time_seconds``. The SRT builder already prefers explicit
    ``start_seconds``/``end_seconds`` over its own word-count guesses, so
    captions stop being estimated the moment this path is on -- which is the
    entire class of bug behind cues running past their scene.
  * IT IS CHEAPER HERE. MuAPI bills $0.10 per generation whatever the length;
    ElevenLabs bills ~1 credit per character, and a micro-drama's scene is a
    couple of hundred characters. Roughly six times less for this shape of
    work. (The opposite is true of video, where a flat per-clip price beats
    per-second billing -- do not generalise this.)

Kept deliberately interface-compatible with MuAPIVoiceGenerator: same
``cast_characters`` / ``generate_scene_dialogue``, same track dicts, so the
pipeline neither knows nor cares which one it is holding.
"""

import asyncio
import base64
import binascii
import hashlib
import logging
import os
import tempfile
import weakref
from typing import Any, Callable, Dict, Iterable, List, Optional

import httpx

from interfaces import acting
from interfaces.speaker import speaker_key
from interfaces import gender as gender_of
from interfaces.language import DEFAULT_LANGUAGE, is_default, normalize

logger = logging.getLogger(__name__)

ELEVENLABS_BASE = os.environ.get(
    "ELEVENLABS_BASE", "https://api.elevenlabs.io/v1"
)

#: How many dialogue requests may be in flight at once, per process.
#:
#: The account allows three at a time and answers a fourth with a 429
#: ("maximum 3 concurrent requests"). A drama renders its scenes' speech
#: together, and a job on 2026-11-22 lost a whole scene's dialogue that way:
#: the pipeline treats a missing voice as a silent scene and carries on, so the
#: film shipped with a line gone and nothing on screen said so. The ceiling is
#: two, not three, because the account's allowance is shared with every other
#: job on the server and with anything else using the key.
def _max_concurrency() -> int:
    try:
        return max(1, int(os.environ.get("ELEVENLABS_MAX_CONCURRENCY", "2")))
    except ValueError:
        return 2


#: A request refused for being over the limit is worth asking again: the
#: limit clears as soon as one of the requests ahead finishes. Anything else
#: (a bad voice, a bad key) is not, and is raised at once as before.
RATE_LIMIT_ATTEMPTS = 4
RATE_LIMIT_BACKOFF_SECONDS = (2.0, 4.0, 8.0)

# One semaphore per event loop: asyncio primitives bind to the loop they are
# first used on, and a long-lived process runs jobs on more than one.
_SLOTS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_sleep = asyncio.sleep


def _slot() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    slot = _SLOTS.get(loop)
    if slot is None:
        slot = _SLOTS[loop] = asyncio.Semaphore(_max_concurrency())
    return slot


def _seconds_to_wait(response: Any, attempt: int) -> float:
    """The provider's own Retry-After when it sent one, else a fixed backoff."""
    headers = getattr(response, "headers", None) or {}
    try:
        return min(30.0, max(0.0, float(headers.get("retry-after"))))
    except (TypeError, ValueError):
        return RATE_LIMIT_BACKOFF_SECONDS[
            min(attempt, len(RATE_LIMIT_BACKOFF_SECONDS) - 1)
        ]


#: Model that has to support text-to-dialogue. Overridable because the id is
#: the one part of this that the provider revises without warning; ask
#: ``GET /v1/models`` when a 4xx names it.
DIALOGUE_MODEL = os.environ.get("ELEVENLABS_DIALOGUE_MODEL", "eleven_v3")


class ElevenLabsError(Exception):
    """Raised when ElevenLabs refuses a dialogue request."""


def _voices(env_name: str, default: tuple) -> tuple:
    raw = os.environ.get(env_name, "")
    values = tuple(v.strip() for v in raw.split(",") if v.strip())
    return values or default


def _estimate_line_duration_seconds(line: str) -> float:
    """Fallback only. This path normally gets measured timings instead."""
    words = max(1, len((line or "").split()))
    return max(1.2, min(8.0, words / 2.5))


class ElevenLabsVoiceGenerator:
    """Lock each character to one voice for the whole drama, then speak it."""

    #: ElevenLabs library voices. Unlike the reseller's, these are the
    #: provider's own long-standing public ids -- and ``list_voices`` can
    #: check them against the account rather than trusting this tuple.
    _GEORGE = "JBFqnCBsd6RMkjVDRZzb"
    _BRIAN = "nPczCjzI2devNBz1zQrb"
    _CALLUM = "N2lVS1w4EtoT3dr4eOWO"
    _SARAH = "EXAVITQu4vr4xnSDxMaL"
    _LAURA = "FGY2WhTYpPnrIDTdsKH5"

    SYSTEM_VOICE_IDS = _voices(
        "ELEVENLABS_VOICE_IDS",
        (_GEORGE, _SARAH, _BRIAN, _CALLUM, _LAURA),
    )
    FEMALE_VOICE_IDS = _voices("ELEVENLABS_FEMALE_VOICE_IDS", (_SARAH, _LAURA))
    MALE_VOICE_IDS = _voices(
        "ELEVENLABS_MALE_VOICE_IDS", (_GEORGE, _BRIAN, _CALLUM)
    )

    def __init__(
        self,
        api_key: str = "",
        demo: bool = False,
        working_dir: str = "",
        timeout: float = 180.0,
    ):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self.demo = demo
        # The API hands back audio BYTES, not a URL. The mixer opens whatever
        # is in `audio_url` with moviepy, which takes a local path perfectly
        # well, so the scene is written into the job's own directory and the
        # path travels in that field -- no upload, no second round trip.
        self.working_dir = working_dir or tempfile.gettempdir()
        self.timeout = timeout
        self._character_voices: Dict[str, str] = {}
        # The gender each character was cast on, kept so verify_cast can
        # re-pick INSIDE the right pool when an id turns out to be unusable.
        self._character_gender: Dict[str, str] = {}
        # The age bucket (young / middle_aged / old) each character was cast
        # on, and the voices a library character brought with it, which no
        # re-casting is allowed to touch.
        self._character_age: Dict[str, str] = {}
        self._locked: set = set()

    # --- casting (identical rules to the MuAPI path) ---------------------

    @classmethod
    def _infer_gender(cls, description: str) -> str:
        return gender_of.infer(description)

    def _assign(self, key: str, pool) -> str:
        used = set(self._character_voices.values())
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        start = int.from_bytes(digest[:4], "big") % len(pool)
        voice_id = pool[start]
        for offset in range(len(pool)):
            candidate = pool[(start + offset) % len(pool)]
            if candidate not in used:
                voice_id = candidate
                break
        self._character_voices[key] = voice_id
        return voice_id

    def lock_voices(self, voices: Dict[str, str]) -> None:
        """Pin named characters to voices decided by an earlier episode.

        Casting is a deterministic hash of the character's name, which sounds
        like it is already stable across episodes -- and is not. ``_assign``
        walks past a voice another character has already taken, so the voice a
        name lands on depends on WHO ELSE is in the cast and in what order they
        were cast. Add one character to episode two and the returning lead can
        be bumped to the next free voice: same face, same wardrobe, same locked
        portrait, different person speaking.

        Nothing derived can fix that, because the collision is real -- two
        characters cannot share a voice inside one drama. The only thing that
        survives a change of cast is a decision that was written down, so a
        library character carries its voice with it and this is where that
        decision is read back in.

        Called BEFORE cast_characters, which skips any name already cast.
        """
        for name, voice_id in (voices or {}).items():
            key = str(name or "").strip().casefold()
            voice = str(voice_id or "").strip()
            if key and voice:
                self._character_voices[key] = voice
                self._locked.add(key)

    def cast_characters(self, characters: Iterable[Any]) -> Dict[str, str]:
        """Assign every named character a gender-matched voice up front."""
        for char in characters or []:
            name = str(getattr(char, "name", "") or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key in self._character_voices:
                continue
            description = str(
                getattr(char, "static_features", "")
                or getattr(char, "description", "")
                or ""
            )
            gender = self._infer_gender(f"{name} {description}")
            pool = (
                self.FEMALE_VOICE_IDS
                if gender == "female"
                else self.MALE_VOICE_IDS if gender == "male" else None
            )
            if pool is None:
                continue  # hash fallback assigns on the character's first line
            self._character_gender[key] = gender
            self._character_age[key] = gender_of.infer_age(description)
            self._assign(key, pool)
        # Written down at INFO because a wrong voice is invisible from the
        # code and obvious from the film: a delivered drama whose only
        # character is described "woman in her late thirties" came back with a
        # measured 120 Hz voice, and nothing anywhere said which id was asked
        # for. Now it does.
        logger.info(
            "Cast: %s",
            ", ".join(
                f"{name}={self._character_voices[name]}"
                for name in sorted(self._character_voices)
            )
            or "(nobody)",
        )
        return dict(self._character_voices)

    def voice_id_for_character(self, character: str) -> str:
        key = speaker_key(character) or "narrator"
        if key in self._character_voices:
            return self._character_voices[key]
        return self._assign(key, self.SYSTEM_VOICE_IDS)

    def _parse_lines(
        self, dialogue: Iterable[Any], emotion: str = ""
    ) -> List[Dict[str, str]]:
        lines: List[Dict[str, str]] = []
        for item in dialogue or []:
            if isinstance(item, dict):
                character = str(item.get("character", "Narrator"))
                line = str(item.get("line", ""))
            else:
                character = str(getattr(item, "character", "Narrator"))
                line = str(getattr(item, "line", ""))
            text = line.strip()
            if not text:
                continue
            lines.append(
                {
                    "character": character,
                    "line": text,
                    "voice_id": self.voice_id_for_character(character),
                }
            )
        return self._direct_delivery(lines, emotion)

    @staticmethod
    def _direct_delivery(
        lines: List[Dict[str, str]], emotion: str = ""
    ) -> List[Dict[str, str]]:
        """Put the scene's emotion into the DELIVERY, not just the words.

        Eleven v3 reads bracketed audio tags inline in the text -- "[furious]",
        "[voice breaking]" -- and interfaces/acting already decided which one
        this beat is, from the same table that decided the face. A scene whose
        picture is a woman with tears breaking over her lower lid, read in the
        even, pleasant default voice, is the single loudest tell that a drama
        was generated rather than performed.

        The tag goes on the FIRST line only, and deliberately:

        * v3 carries delivery forward through a dialogue turn, so tagging every
          line does not make the scene more emotional -- it makes each line
          restart the emotion from zero, which reads as an actor being
          re-directed between sentences.
        * The tag is spoken by nobody but it IS text, so it costs characters on
          a per-character bill, and it is one more thing that can survive into
          the caption if anything downstream ever reads `line` instead of the
          untouched copy kept in ``track["line"]``.

        ``spoken_text`` is what gets sent; ``line`` stays exactly what the
        screenwriter wrote, because that is what the subtitle shows.
        """
        for row in lines:
            row["spoken_text"] = row["line"]
        tag = acting.voice_tag(emotion)
        if tag and lines:
            lines[0]["spoken_text"] = f"{tag}{lines[0]['line']}"
        return lines

    # --- the provider ----------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {"xi-api-key": self.api_key, "Content-Type": "application/json"}

    def _recast_by_fit(self, available: List[Dict[str, str]]) -> None:
        """Give each character the voice of their own gender AND age.

        The configured pools are five ids and say nothing about age, so a man in
        his seventies and a man in his thirties were told apart only by a hash.
        The account lists every voice with the provider's own age label; this
        picks, for each character in turn, the unused voice whose gender matches
        and whose age is closest (an exact match, then the next age over, then
        the far one), preferring the voices already configured for ties so a
        deployment's choices still count. Locked voices (a library character's
        own) are never touched, nobody shares a voice inside one drama, and a
        character whose gender or age is unknown keeps the cast they have.
        """
        order = {gender_of.YOUNG: 0, gender_of.MIDDLE_AGED: 1, gender_of.OLD: 2}
        configured = list(self.SYSTEM_VOICE_IDS)
        taken = {v for k, v in self._character_voices.items() if k in self._locked}
        # Oldest first: the scarcest voices (old ones are few) go to the people
        # who need them, instead of to whoever happens to be cast first.
        keys = sorted(
            (k for k in self._character_voices if k not in self._locked),
            key=lambda k: (-order.get(self._character_age.get(k, ""), 1), k),
        )
        for key in keys:
            gender = self._character_gender.get(key, "")
            age = self._character_age.get(key, "")
            if not gender or not age:
                taken.add(self._character_voices[key])
                continue
            wanted = order[age]

            def distance(v):
                theirs = order.get(v.get("age", ""), 1)
                tie = configured.index(v["voice_id"]) if v["voice_id"] in configured else len(configured)
                digest = hashlib.sha256(f"{key}:{v['voice_id']}".encode()).digest()[0]
                return (abs(theirs - wanted), tie, digest)

            candidates = [
                v for v in available
                if v.get("voice_id") and v.get("gender") == gender
                and v["voice_id"] not in taken
            ]
            if not candidates:
                taken.add(self._character_voices[key])
                continue
            best = min(candidates, key=distance)
            current = self._character_voices[key]
            current_row = next((v for v in available if v.get("voice_id") == current), None)
            # Keep the cast they already have when it is no worse a fit.
            if (
                current_row is not None
                and current not in taken
                and current_row.get("gender") == gender
                and distance(current_row)[0] <= distance(best)[0]
            ):
                taken.add(current)
                continue
            logger.info(
                "Voice for %r (%s, %s) re-cast %s -> %s (%s, %s) to fit.",
                key, gender, age, current, best["voice_id"],
                best.get("name", "?"), best.get("age") or "age unlabelled",
            )
            self._character_voices[key] = best["voice_id"]
            taken.add(best["voice_id"])

    async def verify_cast(self) -> Dict[str, str]:
        """Check the cast against what this ACCOUNT can actually speak with.

        list_voices has existed since this module was written -- "a wrong id is
        a question with an answer instead of a drama that ships silent" -- and
        nothing ever called it. So an id the account cannot use was discovered
        the way every voice bug in this product has been discovered: by
        watching the finished film.

        What that costs is not silence, which would at least be obvious. The
        endpoint takes a voice_id per line and answers with audio either way,
        so an unusable id is heard as SOMEONE ELSE -- and the first thing a
        viewer notices is that the woman on screen has a man's voice.

        Fail-open in the direction of shipping: if the account cannot be
        asked, the cast stands as it is. A character whose voice is
        unavailable is re-cast inside their own gender pool, from ids the
        account actually holds.
        """
        if not self.api_key or self.demo or not self._character_voices:
            return dict(self._character_voices)
        try:
            available = await self.list_voices()
        except Exception as exc:
            logger.warning(
                "Could not ask ElevenLabs which voices this account holds, "
                "casting as-is: %s",
                self._describe(exc),
            )
            return dict(self._character_voices)

        usable = {v["voice_id"] for v in available}
        names = {v["voice_id"]: v.get("name", "") for v in available}
        if not usable:
            return dict(self._character_voices)

        self._recast_by_fit(available)

        for key, voice_id in list(self._character_voices.items()):
            if voice_id in usable:
                continue
            gender = self._character_gender.get(key, "")
            pool = (
                self.FEMALE_VOICE_IDS
                if gender == "female"
                else self.MALE_VOICE_IDS if gender == "male" else self.SYSTEM_VOICE_IDS
            )
            taken = set(self._character_voices.values())
            replacement = next(
                (v for v in pool if v in usable and v not in taken),
                next((v for v in pool if v in usable), ""),
            )
            if not replacement:
                # Nothing in the CONFIGURED pool survives. That is not the
                # account's problem to solve with silence: it holds voices of
                # its own, and this endpoint has just listed them along with
                # the gender it has on file for each.
                #
                # An id in that tuple is a guess about somebody else's
                # catalogue, and guesses rot. XB0fDUnXU5powFXDhCwa shipped as
                # "Charlotte" and is no longer a voice this account -- or, as
                # far as the library search can tell, anyone -- can use; the
                # Charlotte in the shared library today is a different voice
                # with a different id. Every delivered job logged the error
                # and cast a woman's line on whatever was left.
                replacement = self._from_the_account(gender, available, taken)
            if not replacement:
                logger.error(
                    "Voice %s for %r is not available to this account and no "
                    "%s voice is either — the line will be spoken by whatever "
                    "the provider substitutes.",
                    voice_id,
                    key,
                    gender or "listed",
                )
                continue
            logger.error(
                "Voice %s for %r is not available to this account; re-cast to "
                "%s (%s). Check ELEVENLABS_%sVOICE_IDS.",
                voice_id,
                key,
                replacement,
                names.get(replacement, "?"),
                (gender.upper() + "_") if gender else "",
            )
            self._character_voices[key] = replacement

        return dict(self._character_voices)

    @staticmethod
    def _from_the_account(gender: str, available: List[Dict[str, str]], taken: set) -> str:
        """A voice this account actually holds, of the right gender if it says.

        Preferred in that order: an unused voice the account labels with this
        character's gender, then any unused voice, then a labelled one even if
        another character already has it. Sharing a voice between two
        characters is a bad day; a woman speaking in a man's voice is the
        thing viewers write in about, and no voice at all is worse than both.
        """
        matching = [
            v["voice_id"] for v in available
            if v["voice_id"] and (not gender or v.get("gender") == gender)
        ]
        others = [v["voice_id"] for v in available if v["voice_id"]]
        return (
            next((v for v in matching if v not in taken), "")
            or (matching[0] if matching else "")
            or next((v for v in others if v not in taken), "")
            or (others[0] if others else "")
        )

    async def list_voices(self) -> List[Dict[str, str]]:
        """What this ACCOUNT may actually use, asked rather than assumed.

        The whole voice saga came from a provider that published no list. This
        one does, so a wrong id is a question with an answer instead of a
        drama that ships silent.
        """
        if not self.api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{ELEVENLABS_BASE}/voices", headers=self._headers()
            )
            response.raise_for_status()
            data = response.json()
        return [
            {
                "voice_id": v.get("voice_id", ""),
                "name": v.get("name", ""),
                # /v1/voices reports what it knows about each voice in
                # `labels`, and gender is the one field casting needs. Absent
                # on some cloned voices, which is why it is read rather than
                # required -- an unlabelled voice is still a voice.
                "gender": str((v.get("labels") or {}).get("gender", "")).strip().lower(),
                # young / middle_aged / old, as the provider labels it. Casting
                # on gender alone gave a man in his seventies the register of a
                # man in his thirties (job bb6c6f1f).
                "age": str((v.get("labels") or {}).get("age", "")).strip().lower().replace(" ", "_").replace("-", "_"),
            }
            for v in (data.get("voices") or [])
            if v.get("voice_id")
        ]

    @staticmethod
    def _describe(exc: Exception) -> str:
        """The provider's own sentence, not httpx's link to MDN."""
        response = getattr(exc, "response", None)
        if response is None:
            return str(exc)
        body = ""
        try:
            payload = response.json()
            detail = payload.get("detail", payload)
            if isinstance(detail, dict):
                body = str(detail.get("message") or detail)
            else:
                body = str(detail)
        except Exception:
            body = (getattr(response, "text", "") or "")[:500]
        return f"HTTP {response.status_code}: {body[:500]}"

    def _write_scene_audio(self, audio_base64: str) -> str:
        raw = base64.b64decode(audio_base64, validate=True)
        os.makedirs(self.working_dir, exist_ok=True)
        handle, path = tempfile.mkstemp(
            prefix="dialogue_", suffix=".mp3", dir=self.working_dir
        )
        with os.fdopen(handle, "wb") as out:
            out.write(raw)
        return path

    @staticmethod
    def _word_timings(
        alignment: Optional[Dict[str, Any]], lines: List[Dict[str, str]]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Per-WORD timings for each line, read off the character alignment.

        ``/with-timestamps`` returns two things this pipeline can use. The
        first, ``voice_segments``, gives a start and end per LINE and is what
        the SRT builder has always used. The second, ``alignment``, gives a
        start and end per CHARACTER of the whole combined audio -- which is
        everything needed for the word-at-a-time captions that vertical video
        has standardised on, and it costs nothing extra because it arrives in
        the same response that was already paid for.

        The walk is deliberately tolerant. The character stream is the
        provider's normalisation of what was sent, so it may differ from the
        written line in whitespace, punctuation, or the audio tag that was
        prefixed to it (see _direct_delivery) -- and a strict matcher would
        return nothing at the first surprise. Instead each line consumes the
        stream until its own non-space characters are accounted for; anything
        that does not line up is skipped rather than fatal, and a line that
        cannot be resolved simply has no word timings and falls back to the
        whole-line cue.
        """
        if not isinstance(alignment, dict):
            return {}
        characters = alignment.get("characters") or []
        starts = alignment.get("character_start_times_seconds") or []
        ends = alignment.get("character_end_times_seconds") or []
        if not characters or len(characters) != len(starts) or len(starts) != len(ends):
            return {}

        by_line: Dict[int, List[Dict[str, Any]]] = {}
        cursor = 0
        for index, row in enumerate(lines):
            written = row.get("line") or ""
            text = row.get("spoken_text") or written
            # The audio tag is a DIRECTION TO THE ACTOR, not a spoken word.
            # It has to be walked, because the character stream contains it
            # and skipping it here would throw the whole line out of
            # alignment -- but it must never be EMITTED, or the viewer reads
            # "[fearfully] Control's gone" burned into the picture. Seen in a
            # delivered drama exactly that way.
            prefix_len = max(0, len(text) - len(written)) if written else 0
            words: List[Dict[str, Any]] = []
            current: List[str] = []
            current_start: Optional[float] = None
            current_end: Optional[float] = None
            word_at = 0

            for position, wanted in enumerate(text):
                if wanted.isspace():
                    # Word boundary in the written line; the stream's own
                    # spacing is not trusted to agree.
                    if current:
                        if word_at >= prefix_len:
                            words.append(
                                {
                                    "text": "".join(current),
                                    "start": float(current_start or 0.0),
                                    "end": float(current_end or 0.0),
                                }
                            )
                        current, current_start, current_end = [], None, None
                    continue
                if not current:
                    word_at = position
                # Advance to this character in the stream, skipping whatever
                # the provider inserted or normalised away.
                found = -1
                for at in range(cursor, min(len(characters), cursor + 40)):
                    if str(characters[at]) == wanted:
                        found = at
                        break
                if found < 0:
                    continue
                cursor = found + 1
                if current_start is None:
                    current_start = float(starts[found])
                current_end = float(ends[found])
                current.append(wanted)

            if current and word_at >= prefix_len:
                words.append(
                    {
                        "text": "".join(current),
                        "start": float(current_start or 0.0),
                        "end": float(current_end or 0.0),
                    }
                )
            # A word list that never advanced is worse than none: it would
            # pin every cue of the line to zero.
            if words and words[-1]["end"] > words[0]["start"]:
                by_line[index] = words
        return by_line

    async def generate_scene_dialogue(
        self,
        dialogue: Iterable[Any],
        is_cancelled: Optional[Callable[[], bool]] = None,
        language: str = DEFAULT_LANGUAGE,
        emotion: str = "",
    ) -> List[Dict[str, Any]]:
        """Speak a whole scene in one request, and keep the timings it returns.

        The combined audio path rides on the FIRST track only, so the mixer
        lays it down once; the rest are caption rows, exactly as on the MuAPI
        path. What is new is ``start_seconds``/``end_seconds`` per line, which
        the SRT builder honours as given -- so this path's captions are
        measured rather than guessed from the word count.
        """
        lines = self._parse_lines(dialogue, emotion)
        if not lines or self.demo:
            return []
        if not self.api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not configured")

        payload: Dict[str, Any] = {
            # `inputs`, not the reseller's `dialogue`: the wrapper renamed the
            # field, and sending the wrong one is a 422 before a note is sung.
            "inputs": [
                {
                    # The tagged text, not the written line -- see
                    # _direct_delivery. The written line is what the caption
                    # shows and it is kept untouched on the track below.
                    "text": row.get("spoken_text") or row["line"],
                    "voice_id": row["voice_id"],
                }
                for row in lines
            ],
            "model_id": DIALOGUE_MODEL,
        }
        # How far the delivery may move from the voice's default reading.
        # Sent only when the scene declared an emotion: with no beat to play,
        # the provider's own default (0.5) is the right answer and stating it
        # would only pin a number we have no opinion about.
        if (emotion or "").strip():
            payload["stability"] = acting.voice_stability(emotion)
        # Sent only for non-English, same reasoning as the MuAPI path: omitted
        # means auto-detect, which is right for English and unreliable on the
        # two-word lines a micro-drama is made of.
        if not is_default(language):
            payload["language_code"] = normalize(language)

        if is_cancelled and is_cancelled():
            raise ElevenLabsError("Job cancelled before dialogue generation")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                for attempt in range(RATE_LIMIT_ATTEMPTS):
                    # The slot is held for the request only, not for the wait
                    # after a refusal, so the requests that are succeeding are
                    # not queued behind one that is sleeping.
                    async with _slot():
                        response = await client.post(
                            f"{ELEVENLABS_BASE}/text-to-dialogue/with-timestamps",
                            headers=self._headers(),
                            json=payload,
                        )
                    if response.status_code != 429 or attempt == RATE_LIMIT_ATTEMPTS - 1:
                        break
                    wait = _seconds_to_wait(response, attempt)
                    logger.warning(
                        "ElevenLabs refused a dialogue request for concurrency "
                        "(429); asking again in %.0fs (attempt %d of %d).",
                        wait, attempt + 1, RATE_LIMIT_ATTEMPTS,
                    )
                    await _sleep(wait)
                    if is_cancelled and is_cancelled():
                        raise ElevenLabsError("Job cancelled before dialogue generation")
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise ElevenLabsError(self._describe(exc)) from exc
        except httpx.HTTPError as exc:
            raise ElevenLabsError(str(exc)) from exc

        audio_base64 = data.get("audio_base64") or ""
        if not audio_base64:
            raise ElevenLabsError(f"No audio in response (keys: {sorted(data)})")
        try:
            audio_path = self._write_scene_audio(audio_base64)
        except (binascii.Error, ValueError) as exc:
            raise ElevenLabsError(f"Audio was not valid base64: {exc}") from exc

        # voice_segments carries dialogue_input_index, so a line is matched to
        # its own timing rather than to its position in a list the provider
        # never promised to preserve.
        timings: Dict[int, Dict[str, float]] = {}
        for segment in data.get("voice_segments") or []:
            index = segment.get("dialogue_input_index")
            if not isinstance(index, int):
                continue
            start = segment.get("start_time_seconds")
            end = segment.get("end_time_seconds")
            if start is None or end is None:
                continue
            timings[index] = {"start": float(start), "end": float(end)}

        if not timings:
            logger.warning(
                "ElevenLabs returned no voice_segments; captions fall back to "
                "estimated timings for this scene."
            )

        words_by_line = self._word_timings(data.get("alignment"), lines)

        tracks: List[Dict[str, Any]] = []
        for i, row in enumerate(lines):
            track: Dict[str, Any] = {
                "character": row["character"],
                "line": row["line"],
                "voice_id": row["voice_id"],
            }
            timing = timings.get(i)
            if timing and timing["end"] > timing["start"]:
                track["start_seconds"] = timing["start"]
                track["end_seconds"] = timing["end"]
                track["duration_seconds"] = timing["end"] - timing["start"]
            else:
                track["duration_seconds"] = _estimate_line_duration_seconds(
                    row["line"]
                )
            words = words_by_line.get(i)
            if words:
                # Scene-relative, exactly like start_seconds above, so the SRT
                # builder offsets them with the same anchor and cannot drift
                # from the line they belong to.
                track["words"] = words
            if i == 0:
                track["audio_url"] = audio_path
            tracks.append(track)
        return tracks
