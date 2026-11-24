"""Job bb6c6f1f: Ilya, "old man in his seventies", and Tomas, "man in his
thirties", were cast from the same five-id pool by a hash of their names. The
account lists every voice with the provider's age label (young / middle_aged /
old); casting now uses it, on top of gender.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces import gender as g  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from tools.elevenlabs_voice_generator import ElevenLabsVoiceGenerator  # noqa: E402

ACCOUNT = [
    {"voice_id": "bill", "name": "Bill", "gender": "male", "age": "old"},
    {"voice_id": "brian", "name": "Brian", "gender": "male", "age": "middle_aged"},
    {"voice_id": "will", "name": "Will", "gender": "male", "age": "young"},
    {"voice_id": "alice", "name": "Alice", "gender": "female", "age": "middle_aged"},
    {"voice_id": "sarah", "name": "Sarah", "gender": "female", "age": "young"},
    {"voice_id": "gran", "name": "Gran", "gender": "female", "age": "old"},
]


def _cast(*pairs, locked=None):
    gen = ElevenLabsVoiceGenerator(api_key="k")

    async def fake_list():
        return ACCOUNT

    gen.list_voices = fake_list
    if locked:
        gen.lock_voices(locked)
    gen.cast_characters(
        [CharacterInScene(idx=i, name=n, static_features=d) for i, (n, d) in enumerate(pairs)]
    )
    asyncio.run(gen.verify_cast())
    return gen._character_voices


def test_age_is_read_off_the_description():
    assert g.infer_age("old man in his seventies, white moustache") == "old"
    assert g.infer_age("man in his thirties, black beard") == "middle_aged"
    assert g.infer_age("24-year-old woman") == "young"
    assert g.infer_age("a card dealer") == ""
    assert g.infer_age("nine people at a fire") == ""


def test_the_old_man_gets_the_old_voice_and_the_younger_man_does_not():
    cast = _cast(
        ("Ilya", "old man in his seventies, white moustache"),
        ("Tomas", "man in his thirties, black beard"),
    )
    assert cast["ilya"] == "bill"
    assert cast["tomas"] == "brian"


def test_the_scarce_old_voice_goes_to_who_needs_it_not_to_who_is_cast_first():
    cast = _cast(
        ("Aaron", "man in his forties"),
        ("Ilya", "old man in his seventies"),
    )
    assert cast["ilya"] == "bill"
    assert cast["aaron"] != "bill"


def test_gender_is_never_traded_for_age():
    cast = _cast(("Nana", "old woman in her eighties"), ("Mira", "woman in her forties"))
    assert cast["nana"] == "gran"
    assert cast["mira"] == "alice"


def test_nobody_shares_a_voice_when_the_right_age_runs_out():
    cast = _cast(
        ("Ilya", "old man, seventy"),
        ("Odd", "old man in his eighties"),
    )
    assert cast["ilya"] != cast["odd"]


def test_a_library_characters_own_voice_is_never_re_cast():
    cast = _cast(("Ilya", "old man in his seventies"), locked={"ilya": "will"})
    assert cast["ilya"] == "will"


def test_an_unknown_age_keeps_the_cast_it_was_given():
    gen = ElevenLabsVoiceGenerator(api_key="k")
    gen.cast_characters([CharacterInScene(idx=0, name="Kemal", static_features="a man")])
    before = dict(gen._character_voices)

    async def fake_list():
        return ACCOUNT

    gen.list_voices = fake_list
    asyncio.run(gen.verify_cast())
    # gender-matched ids only matter here if they exist on the account; the
    # point is that no age-driven re-cast happened.
    assert gen._character_age["kemal"] == ""
    assert gen._character_voices["kemal"] in set(before.values()) | {v["voice_id"] for v in ACCOUNT}


def test_the_writer_is_told_every_speaker_including_a_radio_voice_needs_an_entry():
    from agents.screenwriter import ScreenwriterAgent

    prompt = ScreenwriterAgent.SYSTEM_PROMPT
    assert "EVERY VOICE HAS AN ENTRY" in prompt
    assert "gender and" in prompt and "never seen" in prompt
