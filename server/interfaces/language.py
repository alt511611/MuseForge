"""The drama's spoken language, in one place.

Language used to be nobody's decision. The screenwriter inferred it from the
wording of the idea — with an English system prompt and English example values
pulling it back towards English on any short or mixed brief — and the voice
model was left to auto-detect from lines as short as "Söz.". A Turkish user on
a Turkish interface could write a Turkish idea and get an English drama, with
no control anywhere to say otherwise.

Doing this per language does not scale: the product ships in twenty locales and
would need twenty prompts and twenty voice tables. It does not have to. The
whole thing reduces to ONE ISO-639-1 code threaded through three layers:

  * the screenwriter gets the language's English NAME in a binding instruction;
  * ElevenLabs gets the CODE as ``language_code``, which fixes pronunciation;
  * voices need nothing — ElevenLabs v3 voices are multilingual, so the same
    cast speaks any supported language once the code is passed.

So the only table in the system is this one, and it exists only because an LLM
needs a word where an API needs a code.
"""

from typing import Optional

#: ISO-639-1 code -> English name. Mirrors client/lib/i18n/locales.js; the keys
#: ARE the locale slugs the site is served on, and they are already the codes
#: ElevenLabs' language_code enum expects, so no second mapping is needed.
LANGUAGES = {
    "en": "English",
    "tr": "Turkish",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "ru": "Russian",
    "ar": "Arabic",
    "hi": "Hindi",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "id": "Indonesian",
    "vi": "Vietnamese",
    "th": "Thai",
    "pl": "Polish",
    "nl": "Dutch",
    "uk": "Ukrainian",
    "ro": "Romanian",
}

DEFAULT_LANGUAGE = "en"


def normalize(code: Optional[str]) -> str:
    """Best-effort ISO-639-1 code, falling back to English.

    Accepts what browsers and locale routers actually produce -- ``tr``,
    ``tr-TR``, ``TR``, ``pt_BR`` -- because the alternative is rejecting a
    perfectly clear request over a region suffix. An unknown language falls
    back rather than erroring: the drama is still worth making in English.
    """
    code = (code or "").strip().lower().replace("_", "-")
    if not code:
        return DEFAULT_LANGUAGE
    base = code.split("-", 1)[0]
    return base if base in LANGUAGES else DEFAULT_LANGUAGE


def name_of(code: Optional[str]) -> str:
    """The language's English name, for an instruction an LLM will follow."""
    return LANGUAGES[normalize(code)]


def is_default(code: Optional[str]) -> bool:
    return normalize(code) == DEFAULT_LANGUAGE
