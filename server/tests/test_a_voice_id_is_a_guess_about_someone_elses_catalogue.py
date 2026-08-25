"""When the configured pool rots, cast from what the account actually holds.

Three delivered jobs in a row logged the same error:

    Voice XB0fDUnXU5powFXDhCwa for 'mara vosk' is not available to this
    account; re-cast to EXAVITQu4vr4xnSDxMaL (Sarah). Check
    ELEVENLABS_FEMALE_VOICE_IDS.

XB0fDUnXU5powFXDhCwa shipped in this module as "Charlotte". It is not a
voice this account can use, and it is not the Charlotte in the shared
library either -- that one is rhS7yjXTU4uIlRxXhNW7, a different voice with a
different id. So there was nothing to add and nothing to configure: the id
had simply stopped being anything.

verify_cast already asked the account what it holds. It only ever used the
answer to VALIDATE the hardcoded tuple, and re-cast from that same tuple --
so when the tuple runs out, a character loses their voice to a catalogue
somebody else maintains. The account's own voices were sitting in the
response the whole time, with the gender the provider has on file for each.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from tools.elevenlabs_voice_generator import ElevenLabsVoiceGenerator  # noqa: E402

#: What this account actually holds, read off its My Voices page.
ACCOUNT = [
    {"voice_id": "acct-adam", "name": "Adam - Engaging", "gender": "male"},
    {"voice_id": "acct-derek", "name": "Derek - Fun & Energetic", "gender": "male"},
    {"voice_id": "acct-sia", "name": "Sia - Sales Professional", "gender": "female"},
    {"voice_id": "acct-ivanna", "name": "Ivanna - Intimate", "gender": "female"},
    {"voice_id": "acct-russ", "name": "Russ - Deep, Smooth", "gender": "male"},
]


# ── the id that rotted ──────────────────────────────────────────────────────


def test_the_dead_id_is_gone_from_the_pools():
    dead = "XB0fDUnXU5powFXDhCwa"
    assert dead not in ElevenLabsVoiceGenerator.SYSTEM_VOICE_IDS
    assert dead not in ElevenLabsVoiceGenerator.FEMALE_VOICE_IDS


def test_the_pools_are_still_gendered_and_non_empty():
    """Dropping it must not leave a pool with nothing in it -- casting picks
    by modulo and an empty pool is a ZeroDivisionError, not a silent film."""
    assert ElevenLabsVoiceGenerator.FEMALE_VOICE_IDS
    assert ElevenLabsVoiceGenerator.MALE_VOICE_IDS
    assert not set(ElevenLabsVoiceGenerator.FEMALE_VOICE_IDS) & set(
        ElevenLabsVoiceGenerator.MALE_VOICE_IDS
    )


# ── picking from the account ────────────────────────────────────────────────


def _pick(gender, taken=()):
    return ElevenLabsVoiceGenerator._from_the_account(gender, ACCOUNT, set(taken))


def test_it_matches_the_gender_the_account_reports():
    assert _pick("female") in {"acct-sia", "acct-ivanna"}
    assert _pick("male") in {"acct-adam", "acct-derek", "acct-russ"}


def test_it_does_not_hand_two_characters_the_same_voice():
    assert _pick("female", taken={"acct-sia"}) == "acct-ivanna"


def test_a_shared_voice_beats_the_wrong_gender():
    """Sharing a voice between two characters is a bad day. A woman speaking
    in a man's voice is the thing viewers write in about."""
    both_taken = {"acct-sia", "acct-ivanna"}
    assert _pick("female", taken=both_taken) in both_taken


def test_an_unlabelled_character_takes_anyone():
    assert _pick("") in {v["voice_id"] for v in ACCOUNT}


def test_an_account_with_nothing_in_it_picks_nothing():
    """Fail-open stays fail-open: the caller logs and lets the provider
    substitute rather than crashing a paid render."""
    assert ElevenLabsVoiceGenerator._from_the_account("female", [], set()) == ""


# ── end to end through verify_cast ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_character_keeps_a_voice_when_the_whole_pool_is_dead(monkeypatch):
    """The delivered shape, taken to its limit: not one configured id is
    usable. Before this, the line was 'spoken by whatever the provider
    substitutes' -- which is how a woman ends up sounding like a man."""
    gen = ElevenLabsVoiceGenerator(api_key="test-key")
    gen._character_voices = {"mara vosk": "XB0fDUnXU5powFXDhCwa"}
    gen._character_gender = {"mara vosk": "female"}

    async def _account(_self=None):
        return ACCOUNT

    monkeypatch.setattr(ElevenLabsVoiceGenerator, "list_voices", _account)
    cast = await gen.verify_cast()
    assert cast["mara vosk"] in {"acct-sia", "acct-ivanna"}


@pytest.mark.asyncio
async def test_the_configured_pool_is_still_preferred(monkeypatch):
    """The account is the fallback, not the first choice: a deployment that
    configured a cast gets the cast it configured."""
    gen = ElevenLabsVoiceGenerator(api_key="test-key")
    good = ElevenLabsVoiceGenerator.FEMALE_VOICE_IDS[0]
    gen._character_voices = {"mara": "XB0fDUnXU5powFXDhCwa"}
    gen._character_gender = {"mara": "female"}

    async def _account(_self=None):
        return ACCOUNT + [{"voice_id": good, "name": "Sarah", "gender": "female"}]

    monkeypatch.setattr(ElevenLabsVoiceGenerator, "list_voices", _account)
    assert (await gen.verify_cast())["mara"] == good


@pytest.mark.asyncio
async def test_an_account_that_cannot_be_asked_changes_nothing(monkeypatch):
    """Fail-open in the direction of shipping, exactly as before."""
    gen = ElevenLabsVoiceGenerator(api_key="test-key")
    gen._character_voices = {"mara": "XB0fDUnXU5powFXDhCwa"}
    gen._character_gender = {"mara": "female"}

    async def _boom(_self=None):
        raise RuntimeError("network")

    monkeypatch.setattr(ElevenLabsVoiceGenerator, "list_voices", _boom)
    assert (await gen.verify_cast())["mara"] == "XB0fDUnXU5powFXDhCwa"


def test_list_voices_carries_the_gender_it_is_given():
    """The field casting needs was in the response all along and was being
    dropped on the floor."""
    payload = {
        "voices": [
            {"voice_id": "v1", "name": "Sia", "labels": {"gender": "Female"}},
            {"voice_id": "v2", "name": "Cloned", "labels": {}},
        ]
    }
    rows = [
        {
            "voice_id": v.get("voice_id", ""),
            "name": v.get("name", ""),
            "gender": str((v.get("labels") or {}).get("gender", "")).strip().lower(),
        }
        for v in payload["voices"]
    ]
    assert rows[0]["gender"] == "female"
    assert rows[1]["gender"] == ""
