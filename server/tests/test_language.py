"""The drama's spoken language, end to end.

Language used to be nobody's decision: the screenwriter inferred it from the
wording of the idea, the voice model auto-detected it from two-word lines, and
the twenty locales the site is served in never reached the backend at all.

The point of these tests is that ONE ISO-639-1 code does the whole job, so
adding the twenty-first language stays a one-line change to a table rather
than a new prompt and a new voice list.
"""

import os
import re
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
    for prompt in (agent._system_prompt("en"), agent._system_prompt(None)):
        assert agent.SYSTEM_PROMPT in prompt, "the direction must survive intact"
        assert "Write ALL" not in prompt and "language" not in prompt.split(
            agent.SYSTEM_PROMPT
        )[1]


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


# ── the half of the script no viewer reads ──────────────────────────────────
#
# Delivered job 4631cc44-d30 sent flux-2-pro "Character reference sheet of a
# woman, Sci-Fi style. otuzlu yaşlarının sonunda bi..." and a location plate
# reading "yağmurla ıslanmış kargo limanı, konteyner...". Nobody watching the
# film sees either sentence; both are prompts. The clause said "only the prose
# changes" and a model writing a Turkish drama read that as all of the prose,
# which is how it should be read -- so the clause had to say which prose.


#: Fields that end up inside an image, video or music prompt. Kept as a list
#: rather than one assertion per field so that adding a field to the schema
#: and forgetting it here is a diff a reviewer can see.
MODEL_FACING = (
    "setting_location",
    "setting_time_of_day",
    "setting_era",
    "mood",
    "theme",
    "visual_motif",
    "description",
    "wardrobe",
    "emotion",
    "world_change",
)


@pytest.mark.parametrize("field", MODEL_FACING)
def test_the_fields_that_are_prompts_are_ordered_in_english(field):
    """Each of these is pasted into a generative model's prompt and read by no
    one: the two settings and the character blocks go to the image model, and
    "mood", "theme" and "emotion" build the music request."""
    prompt = ScreenwriterAgent(demo=True)._system_prompt("tr")
    english_rule = prompt.split("WRITE THESE FIELDS IN ENGLISH")[1]
    assert f'"{field}"' in english_rule, (
        f"{field} reaches a model's prompt but is not named as an English field"
    )


def test_what_the_viewer_hears_is_still_the_drama_s_language():
    """The carve-out must not swallow the feature. A Turkish drama whose
    dialogue came back in English is the bug this clause was added for."""
    prompt = ScreenwriterAgent(demo=True)._system_prompt("tr")
    ordered = prompt.split("LANGUAGE. Write the drama in")[1]
    viewer_rule = ordered.split("WRITE THESE FIELDS IN ENGLISH")[0]
    for field in ("title", "logline", "line"):
        assert f'"{field}"' in viewer_rule
    assert "Turkish" in viewer_rule
    # And the carve-out names none of them.
    english_rule = prompt.split("WRITE THESE FIELDS IN ENGLISH")[1]
    for field in ("title", "logline", '"line"'):
        assert field not in english_rule


def test_an_english_drama_is_told_none_of_this():
    """There is nothing to carve out when both halves are the same language,
    and the clause is paid for on every job that carries it."""
    prompt = ScreenwriterAgent(demo=True)._system_prompt("en")
    assert "WRITE THESE FIELDS IN ENGLISH" not in prompt


def test_the_storyboard_writes_english_whatever_it_is_handed():
    """The storyboard agent never sees a language code, and does not need one:
    every field it writes is a prompt. It drifted into Turkish anyway, because
    the script it reads is in Turkish -- contagion, not instruction, so the
    instruction is unconditional."""
    from agents.storyboard_artist import StoryboardArtist

    prompt = StoryboardArtist.SYSTEM_PROMPT
    assert "WRITE EVERY FIELD IN ENGLISH" in prompt
    assert "even when the script you are handed is in another" in prompt


def test_the_language_reaches_both_provider_paths():
    """The MuAPI LLM route is tried FIRST, so a clause added only to the
    Anthropic fallback would do nothing on the primary path."""
    import inspect

    source = inspect.getsource(ScreenwriterAgent.write_script)
    # Matched on the arguments rather than one exact call spelling: the call
    # has since gained an argument and been wrapped over several lines, and a
    # test that breaks on reformatting stops being read.
    call = re.search(r"self\._system_prompt\(([^)]*)\)", source, re.DOTALL)
    assert call, "MuAPI path calls _system_prompt"
    assert "language" in call.group(1), "MuAPI path passes the language"
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
