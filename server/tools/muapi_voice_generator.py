"""Optional, fail-open character dialogue generation via MuAPI.

Uses ElevenLabs text-to-dialogue v3: one request per scene with all lines
in a single ``dialogue`` list.

Schema CONFIRMED against MuAPI's own OpenAPI spec
(https://api.muapi.ai/openapi.json -> ElevenlabsTextToDialogueV3Request):

    {"dialogue": [{"text": str, "voice_id": str}, ...],
     "stability": float, "language_code": str}

Two details that are easy to get wrong and fail EVERY request when wrong:
  * the list field is ``dialogue`` -- ``inputs`` is not a declared field, so
    the endpoint rejected the whole body with a 422 before generating a note;
  * ``voice_id`` is a real ElevenLabs voice ID hash (the sibling
    ``elevenlabs-tts-turbo-2-5`` schema defaults it to ``21m00Tcm4TlvDq8ikWAM``),
    NOT a playground display label like "George - Warm".

The schema being right is not the same as the VALUES being accepted. The spec
declares ``voice_id`` as a bare string and publishes no list of allowed ones,
so a rejected voice is not a 422 at submit time -- the request is accepted, a
prediction is queued, and it comes back ``{"status": "failed", "error":
"Invalid voice parameter: ..."}``, i.e. an entire drama's worth of scenes
already spent. ``tools/probe_dialogue_voices.py`` asks the provider what it
accepts for the price of one word of speech, and ``MUSEFORGE_VOICE_IDS``
applies the answer without a deploy.
"""

import hashlib
import logging
import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional

from interfaces import acting
from interfaces import gender as gender_of
from interfaces.language import DEFAULT_LANGUAGE, is_default, normalize
from tools.muapi_client import MuAPICancelled, MuAPIClient

logger = logging.getLogger(__name__)

TRUTHY = {"1", "true", "yes", "on"}


def is_dialogue_enabled() -> bool:
    """Dialogue is opt-in because every spoken line makes a paid API call."""
    return os.environ.get("MUSEFORGE_DIALOGUE_ENABLED", "0").strip().lower() in TRUTHY


def _voices(env_name: str, default: tuple) -> tuple:
    """A cast list, overridable without a deploy.

    The accepted values for ``voice_id`` are the provider's to define and it
    publishes no list: they are absent from its OpenAPI spec, and a wrong one
    is only discovered by a whole drama coming back silent. When the provider
    changes them, ``MUSEFORGE_VOICE_IDS`` etc. (comma-separated) put the new
    ones in without waiting on a release. See tools/probe_dialogue_voices.py
    for finding out what the provider currently accepts.
    """
    raw = os.environ.get(env_name, "")
    values = tuple(v.strip() for v in raw.split(",") if v.strip())
    return values or default


def _estimate_line_duration_seconds(line: str) -> float:
    """Rough spoken duration (~2.5 words/sec) when the API returns no timings."""
    words = max(1, len((line or "").split()))
    return max(1.2, min(8.0, words / 2.5))


class MuAPIVoiceGenerator:
    """Lock each character to one ElevenLabs dialogue voice for the whole drama.

    Voice IDs are ElevenLabs library voice IDs. The display names are kept in
    ``VOICE_NAMES`` for logs and debugging only -- sending a name where an ID
    belongs is what silenced every drama.
    """

    VOICE_ENDPOINT = os.environ.get(
        "MUAPI_VOICE_MODEL", "elevenlabs-text-to-dialogue-v3"
    )

    # The cast, taken from the voice selector on MuAPI's own playground page
    # for THIS endpoint (muapi.ai/playground/elevenlabs-text-to-dialogue-v3),
    # which offers 26 voices as id/label pairs. That selector is the "list of
    # supported voices" the rejection message keeps pointing at and which no
    # documentation or OpenAPI schema contains -- so these six are the first
    # values in this file that were read from the provider rather than
    # guessed. Names and labels below are its strings, character for
    # character; do not retype them from memory.
    _GEORGE = "JBFqnCBsd6RMkjVDRZzb"   # warm, male
    _BRIAN = "zPhCVfO2NBER7bRLIdbq"    # deep, resonant, male
    _CALLUM = "N2lVS1w4EtoT3dr4eOWO"   # husky, male
    _SARAH = "EXAVITQu4vr4xnSDxMaL"    # soft, female
    _CHARLOTTE = "XB0fDUnXU5powFXDhCwa"  # clear, female
    _LAURA = "FGY2WhTYpPnrIDTdsKH5"    # bright, female

    #: ID -> display name, used for logs and as one of the forms below.
    VOICE_NAMES = {
        _GEORGE: "George",
        _BRIAN: "Brian",
        _CALLUM: "Callum",
        _SARAH: "Sarah",
        _CHARLOTTE: "Charlotte",
        _LAURA: "Laura",
    }

    #: ID -> the provider's own label for it, verbatim from that same
    #: selector. Kept because which spelling the API wants is still not
    #: knowable from documentation -- the playground publishes the pairs, not
    #: which half the endpoint validates against.
    VOICE_LABELS = {
        _GEORGE: "George - Warm",
        _BRIAN: "Brian - Deep, Resonant and Comforting",
        _CALLUM: "Callum - Husky Trickster",
        _SARAH: "Sarah - Soft",
        _CHARLOTTE: "Charlotte - Clear",
        _LAURA: "Laura - Enthusiast, Quirky Attitude",
    }

    #: The single voice the whole scene falls back to. Was Rachel
    #: (``21m00Tcm4TlvDq8ikWAM``), reasoned across from the sibling
    #: ``elevenlabs-tts-turbo-2-5`` schema, whose OpenAPI declares it as that
    #: endpoint's default. A sibling's default is not this endpoint's
    #: whitelist: Rachel is absent from the 26 voices this one publishes, and
    #: a drama duly came back with "Invalid voice parameter:
    #: 21m00Tcm4TlvDq8ikWAM" -- a last resort that could only ever fail, at
    #: the cost of one more generation per scene. Now the first entry of the
    #: provider's own list.
    _PROVIDER_DEFAULT = "ZQe5CZNOzWyzPSCn5a3c"  # James - Husky, Engaging and Bold

    #: The forms a voice value can take, in the order they are tried. Each has
    #: been shipped as "confirmed" at some point and each has silenced a drama.
    #: ``default`` is the last resort and is not a spelling of the cast at all:
    #: it puts the WHOLE scene in the provider's own published voice. One voice
    #: for every character is a real loss, and it is still the smaller loss --
    #: the alternative at that point is a drama that says nothing.
    VOICE_FORMS = ("id", "label", "name", "default")

    #: The form the provider accepted, once anything has succeeded. Class-level
    #: on purpose: which form is right is a fact about the provider, not about
    #: one drama, so the second job of a process should not re-pay the
    #: discovery. Only ever set from a request that actually worked.
    _accepted_form: Optional[str] = None

    #: Set once a scene has tried every form and been refused all of them.
    #:
    #: Whether ANY spelling works is a fact about the provider too, and the
    #: search is not cheap: the refusal arrives on the FINISHED prediction
    #: (the error names ``/predictions/<id>/result``, not the submit), so
    #: every form tried is a generation that actually ran. Without this a
    #: three-scene drama that cannot be voiced at all pays the full search
    #: three times over -- twelve generations and the wait that goes with them
    #: -- to learn the same thing the first scene already learned.
    #:
    #: Deliberately not permanent for the process: each later scene still
    #: makes ONE attempt, so a provider that recovers mid-drama is picked up
    #: and every scene still reports its own failure. Cleared by any success.
    #: That one attempt uses the first form only -- exhaustion means no
    #: spelling worked at that moment, which points at the provider being down
    #: rather than at us holding the wrong spelling, and re-running the whole
    #: search per scene is the cost this exists to avoid.
    _forms_exhausted: bool = False

    SYSTEM_VOICE_IDS = _voices(
        "MUSEFORGE_VOICE_IDS", (_GEORGE, _SARAH, _BRIAN, _CHARLOTTE, _CALLUM, _LAURA)
    )
    # Gender pools over the same voices, for description-aware casting: a
    # character described as a woman must not be voiced by George.
    FEMALE_VOICE_IDS = _voices(
        "MUSEFORGE_FEMALE_VOICE_IDS", (_SARAH, _CHARLOTTE, _LAURA)
    )
    MALE_VOICE_IDS = _voices("MUSEFORGE_MALE_VOICE_IDS", (_GEORGE, _BRIAN, _CALLUM))

    # The marker table lives in interfaces/gender.py: the screenwriter writes
    # the gender INTO the description, and this step reads it back out. Two
    # copies of the word list would let a character be written as a woman and
    # cast as a man.
    _FEMALE_MARKERS = gender_of.FEMALE_MARKERS
    _MALE_MARKERS = gender_of.MALE_MARKERS

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)
        self._character_voices: Dict[str, str] = {}

    @classmethod
    def _infer_gender(cls, description: str) -> str:
        """"female" / "male" / "" from a visual description."""
        return gender_of.infer(description)

    def cast_characters(self, characters: Iterable[Any]) -> Dict[str, str]:
        """Assign every named character a voice UP FRONT, matched to the
        gender implied by their visual description.

        Called once per drama before any dialogue is generated. Without this
        the per-line hash fallback picks from the full enum, which can voice
        a mother with "George - Warm" — instantly amateurish. Characters
        whose description implies no gender keep the hash-based fallback
        (still stable and collision-avoiding).
        """
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
                continue  # hash fallback assigns on first line, as before
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
        return dict(self._character_voices)

    def voice_id_for_character(self, character: str) -> str:
        """Return a stable voice ID, assigning it on the character's first line."""
        key = (character or "Narrator").strip().casefold()
        if key in self._character_voices:
            return self._character_voices[key]

        digest = hashlib.sha256(key.encode("utf-8")).digest()
        start = int.from_bytes(digest[:4], "big") % len(self.SYSTEM_VOICE_IDS)
        used = set(self._character_voices.values())
        voice_id = self.SYSTEM_VOICE_IDS[start]
        for offset in range(len(self.SYSTEM_VOICE_IDS)):
            candidate = self.SYSTEM_VOICE_IDS[(start + offset) % len(self.SYSTEM_VOICE_IDS)]
            if candidate not in used:
                voice_id = candidate
                break

        self._character_voices[key] = voice_id
        return voice_id

    def _parse_lines(self, dialogue: Iterable[Any]) -> List[Dict[str, str]]:
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
            voice_id = self.voice_id_for_character(character)
            lines.append(
                {
                    "character": character,
                    "line": text,
                    "voice_id": voice_id,
                }
            )
        return lines

    @classmethod
    def _as_form(cls, voice_id: str, form: str) -> str:
        """``voice_id`` expressed in one of ``VOICE_FORMS``.

        A value with no entry in the tables -- anything set through
        ``MUSEFORGE_VOICE_IDS`` -- is passed through untouched: an override
        exists precisely because someone learned what the provider wants, so
        translating it into a form they did not ask for would undo that.
        """
        if form == "label":
            return cls.VOICE_LABELS.get(voice_id, voice_id)
        if form == "name":
            return cls.VOICE_NAMES.get(voice_id, voice_id)
        if form == "default":
            return cls._PROVIDER_DEFAULT
        return voice_id

    @classmethod
    def _forms_to_try(cls) -> List[str]:
        """Which forms this request may use, best-known first."""
        if cls._accepted_form:
            return [cls._accepted_form]
        if cls._forms_exhausted:
            return [cls.VOICE_FORMS[0]]
        return list(cls.VOICE_FORMS)

    @staticmethod
    def _is_voice_rejection(exc: Exception) -> bool:
        """Whether respelling the voice could plausibly fix this failure.

        The named case is ``{"status": "failed", "error": "Invalid voice
        parameter: ..."}`` on a queued prediction. Matching only that word is
        what made the fix stop working: the same rejection also arrives as a
        submit-time ``HTTP 400: Internal Error, Please try again later.`` --
        the provider knowing perfectly well which voice it disliked (it says so
        on the prediction record) and telling us nothing. Three scenes gave up
        after one request each and the drama shipped silent, with the two
        remaining spellings never tried.

        So the test is the STATUS, not the wording: a 4xx is the provider
        refusing what we sent, and what we sent that it could refuse is the
        voice. 5xx, timeouts, cancellation and a missing key are none of our
        business to respell -- they cannot be fixed by another spelling and
        each attempt is a round trip the user waits through.
        """
        if isinstance(exc, MuAPICancelled):
            return False
        text = str(exc or "")
        if "voice" in text.lower():
            return True
        status = re.search(r"HTTP (\d{3})", text)
        return bool(status) and status.group(1).startswith("4")

    async def generate_scene_dialogue(
        self,
        dialogue: Iterable[Any],
        is_cancelled: Optional[Callable[[], bool]] = None,
        language: str = DEFAULT_LANGUAGE,
        emotion: str = "",
    ) -> List[Dict[str, Any]]:
        """Generate all non-empty scene lines in ONE ElevenLabs dialogue request.

        Returns per-line track metadata for captions. The combined audio URL
        (when the API returns a single file) is attached only to the first
        track so the mixer plays it once; later tracks are caption-only.
        """
        lines = self._parse_lines(dialogue)
        if not lines or self.demo:
            return []
        # The scene's beat, spoken. This endpoint is Eleven v3 behind a
        # reseller, so it reads the same bracketed audio tags -- on the first
        # line only, for the reasons in ElevenLabsVoiceGenerator.
        # ``spoken_text`` is what is sent; ``line`` stays the written line,
        # which is what the caption shows.
        for row in lines:
            row["spoken_text"] = row["line"]
        tag = acting.voice_tag(emotion)
        if tag:
            lines[0]["spoken_text"] = f"{tag}{lines[0]['line']}"

        payload = {
            "dialogue": [],
            # Per-beat rather than a flat 0.5: interfaces/acting maps the
            # scene's emotion to how far the read may move from the voice's
            # default. Same table that picks the face, so the delivery and the
            # expression cannot disagree. Without an emotion this is exactly
            # the 0.5 it always was.
            "stability": acting.voice_stability(emotion) if (emotion or "").strip() else 0.5,
        }
        # The field is `language_code`, not `language` -- the old key was not a
        # field this endpoint declares, so it carried no hint at all and every
        # drama fell through to auto-detection. Auto-detect is fine on a
        # paragraph and unreliable on the two-word lines a micro-drama is made
        # of ("Söz."), where it can switch language mid-scene.
        #
        # Sent only for non-English: omitted means auto-detect, which is the
        # right behaviour for English and keeps the payload identical to what
        # the endpoint saw before for every existing job.
        #
        # No per-language voice table is needed to go with it: ElevenLabs v3
        # voices are multilingual, so the same cast speaks any supported
        # language once the code is passed.
        if not is_default(language):
            payload["language_code"] = normalize(language)

        # Which spelling of a voice this endpoint wants is not in its OpenAPI
        # spec (``voice_id`` is declared as a bare string) and not in any
        # documentation, and getting it wrong does not fail at submit time --
        # the prediction is queued, then comes back "Invalid voice parameter"
        # with the scenes already rendered. So the answer is asked for rather
        # than assumed: the forms are tried in order, and the one that works
        # is remembered for every later request in the process. Only a
        # rejection OF THE VOICE advances; anything else is raised at once.
        audio_url = ""
        last_exc: Optional[Exception] = None
        # Two forms that spell this cast identically are one attempt, not two:
        # an operator's MUSEFORGE_VOICE_IDS value is passed through untouched
        # by "id", "label" and "name" alike, so the search used to send the
        # same rejected body three times before reaching anything new.
        attempts: List[tuple] = []
        for form in self._forms_to_try():
            values = [self._as_form(row["voice_id"], form) for row in lines]
            if attempts and attempts[-1][1] == values:
                continue
            attempts.append((form, values))

        forms = [form for form, _ in attempts]
        for position, (form, values) in enumerate(attempts):
            payload["dialogue"] = [
                {"text": row.get("spoken_text") or row["line"], "voice_id": value}
                for row, value in zip(lines, values)
            ]
            try:
                audio_url = await self.client.generate(
                    self.VOICE_ENDPOINT,
                    payload,
                    poll_interval=2.0,
                    max_polls=120,
                    is_cancelled=is_cancelled,
                )
            except Exception as exc:
                last_exc = exc
                if not self._is_voice_rejection(exc) or position + 1 >= len(forms):
                    # Every spelling refused, and this scene paid a generation
                    # for each. The rest of the drama gets one attempt apiece.
                    if self._is_voice_rejection(exc) and len(forms) > 1:
                        type(self)._forms_exhausted = True
                    break
                logger.warning(
                    "Provider rejected the %r voice form (%s); retrying as %r.",
                    form,
                    exc,
                    forms[position + 1],
                )
                continue
            if type(self)._accepted_form != form:
                if form == "default":
                    logger.warning(
                        "Provider rejected every cast voice; the drama is being "
                        "spoken entirely in the provider's default voice (%s). "
                        "Run tools/probe_dialogue_voices.py and set "
                        "MUSEFORGE_VOICE_IDS to restore the cast.",
                        self._PROVIDER_DEFAULT,
                    )
                else:
                    logger.info("Provider accepted the %r voice form.", form)
                type(self)._accepted_form = form
            # Something works after all -- whatever made the earlier scene give
            # up is over, so later scenes get the full search back.
            type(self)._forms_exhausted = False
            last_exc = None
            break

        if last_exc is not None:
            # Deliberately NOT swallowed here. Returning [] made a broken
            # request schema indistinguishable from a scene with no lines:
            # every drama shipped silent while the only trace was a warning
            # with no scene number. The caller (idea2video) still fails open
            # per scene -- it just gets to say WHICH scene and WHY.
            logger.error(
                "Scene dialogue generation failed (%s voice(s), %s line(s)): %s",
                len({row["voice_id"] for row in lines}),
                len(lines),
                last_exc,
            )
            raise last_exc

        if not audio_url:
            return []

        # Single combined audio file for the whole scene (confirmed typical
        # MuAPI outputs[0] shape). Per-line duration_seconds are fail-safe
        # estimates for SRT when the API does not return cue timings.
        tracks: List[Dict[str, Any]] = []
        for i, row in enumerate(lines):
            track: Dict[str, Any] = {
                "character": row["character"],
                "line": row["line"],
                "voice_id": row["voice_id"],
                "duration_seconds": _estimate_line_duration_seconds(row["line"]),
            }
            if i == 0:
                track["audio_url"] = audio_url
            tracks.append(track)
        return tracks
