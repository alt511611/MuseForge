"""The drama's spoken language, end to end.

Language used to be nobody's decision: the screenwriter inferred it from the
wording of the idea, the voice model auto-detected it from two-word lines, and
the twenty locales the site is served in never reached the backend at all.

The point of these tests is that ONE ISO-639-1 code does the whole job, so
adding the twenty-first language stays a one-line change to a table rather
than a new prompt and a new voice list.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces import language as lang  # noqa: E402


# ── the one table ───────────────────────────────────────────────────────────


def test_every_site_locale_can_be_spoken():
    """The backend table and the site's locale list are the same set. A locale
    the site ships in but the pipeline cannot speak is a page that offers a
    language it will silently ignore."""
    import re

    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "client", "lib", "i18n", "locales.js"
    )
    with open(path, encoding="utf-8") as f:
        locales = set(re.findall(r"^\s{2}(\w{2}):\s*\{", f.read(), re.M))

    assert locales, "could not read the site's locale list"
    assert locales == set(lang.LANGUAGES), (
        f"only on the site: {locales - set(lang.LANGUAGES)}; "
        f"only in the backend: {set(lang.LANGUAGES) - locales}"
    )


def test_region_suffixes_and_case_are_accepted():
    """Browsers and locale routers produce tr-TR, pt_BR, TR. Rejecting a
    perfectly clear request over a region suffix helps nobody."""
    assert lang.normalize("tr-TR") == "tr"
    assert lang.normalize("PT_br") == "pt"
    assert lang.normalize("  ja  ") == "ja"


def test_an_unknown_language_falls_back_rather_than_failing():
    """The drama is still worth making in English."""
    assert lang.normalize("klingon") == "en"
    assert lang.normalize(None) == "en"
    assert lang.normalize("") == "en"
    assert lang.name_of("xx") == "English"


# ── layer 1: the script ─────────────────────────────────────────────────────


def test_english_adds_no_clause():
    """The prompt is already written in English; a redundant instruction only
    spends tokens on every job."""
    agent = ScreenwriterAgent(demo=True)
    assert agent._system_prompt("en") == agent.SYSTEM_PROMPT
    assert agent._system_prompt(None) == agent.SYSTEM_PROMPT


def test_a_non_english_drama_gets_a_binding_instruction():
    agent = ScreenwriterAgent(demo=True)
    prompt = agent._system_prompt("tr")

    assert agent.SYSTEM_PROMPT in prompt, "the direction must survive intact"
    assert "Turkish" in prompt, "the model needs the name, not the code"
    # It has to outrank the brief: a Turkish user often writes the idea in
    # English and still wants a Turkish drama.
    assert "brief itself is written in another language" in prompt
    # ...and it must not invite the model to translate the JSON keys.
    assert "field NAMES" in prompt


def test_the_language_reaches_both_provider_paths():
    """The MuAPI LLM route is tried FIRST, so a clause added only to the
    Anthropic fallback would do nothing on the primary path."""
    import inspect

    source = inspect.getsource(ScreenwriterAgent.write_script)
    assert (
        "self._system_prompt(language, require_dialogue, narrative_mode)" in source
    ), "MuAPI path"
    assert "language" in inspect.signature(
        ScreenwriterAgent._write_with_claude
    ).parameters


# ── layer 2: the voice ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_voice_model_is_given_the_language_code(monkeypatch):
    """The field is `language_code`. The old payload sent `language`, which is
    not a field this endpoint declares -- so it carried no hint at all and
    every drama fell through to auto-detection, which is unreliable on the
    two-word lines a micro-drama is made of."""
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    seen = {}

    async def fake_generate(self, endpoint, payload, **kwargs):
        seen.update(payload)
        return "https://cdn/voice.mp3"

    monkeypatch.setattr("tools.muapi_client.MuAPIClient.generate", fake_generate)

    gen = MuAPIVoiceGenerator("k")
    await gen.generate_scene_dialogue(
        [{"character": "Kemal", "line": "Söz."}], language="tr"
    )
    assert seen["language_code"] == "tr"
    assert "language" not in seen, "the undeclared key must be gone"


@pytest.mark.asyncio
async def test_english_omits_the_code_entirely(monkeypatch):
    """Omitted means auto-detect, which is right for English and keeps the
    payload byte-identical to what the endpoint saw before."""
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    seen = {}

    async def fake_generate(self, endpoint, payload, **kwargs):
        seen.update(payload)
        return "https://cdn/voice.mp3"

    monkeypatch.setattr("tools.muapi_client.MuAPIClient.generate", fake_generate)

    await MuAPIVoiceGenerator("k").generate_scene_dialogue(
        [{"character": "Kemal", "line": "Promise."}]
    )
    assert "language_code" not in seen
    assert "language" not in seen


def test_voices_are_not_per_language():
    """ElevenLabs v3 voices are multilingual: the same cast speaks any
    supported language once the code is passed. A per-language voice table
    would be twenty tables to maintain for no gain."""
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    assert set(MuAPIVoiceGenerator.FEMALE_VOICE_IDS) | set(
        MuAPIVoiceGenerator.MALE_VOICE_IDS
    ) == set(MuAPIVoiceGenerator.SYSTEM_VOICE_IDS)


# ── layer 3: the request ────────────────────────────────────────────────────


def test_the_api_normalises_what_the_browser_sends():
    from api import GenerateRequest

    assert GenerateRequest(idea="a drama").language == "en"
    assert GenerateRequest(idea="bir drama", language="tr").language == "tr"
    # Validation happens at the Job boundary, not the schema, so a stray
    # region suffix is a request we can still honour rather than a 422.
    assert (
        lang.normalize(GenerateRequest(idea="bir drama", language="tr-TR").language)
        == "tr"
    )


def test_the_client_sends_the_locale_it_is_being_read_in():
    path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "client", "app", "[locale]", "HomeContent.js",
    )
    with open(path, encoding="utf-8") as f:
        page = f.read()
    assert "language: locale" in page
