"""Two things a delivered drama got wrong that nothing was watching for.

SILENCE. Every audio layer is independently optional -- music is a plan
feature, foley is behind MUSEFORGE_FOLEY, dialogue is a Pro toggle -- and each
is correct to be off on its own. Nothing ever looked at the sum. With music
off and foley off, the soundtrack is a few seconds of speech and then DIGITAL
silence: not room tone, zero samples. Measured on a delivered drama: 12
audible seconds out of 60, the other 43 absolute zero. That is why the speech
in it sounded pasted on rather than spoken in a place, and every stage had
behaved exactly as configured, so nothing had a reason to mention it.

THE CAST. list_voices has existed since the ElevenLabs module was written --
"a wrong id is a question with an answer instead of a drama that ships
silent" -- and nothing ever called it. An id the account cannot use is not
answered with silence: the endpoint substitutes, and the drama ships with the
wrong person talking. A delivered drama whose only character is described
"woman in her late thirties" came back with a measured ~120 Hz voice.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene  # noqa: E402
from pipelines.idea2video import (  # noqa: E402
    check_master_is_not_mostly_silent,
)
from tools.elevenlabs_voice_generator import ElevenLabsVoiceGenerator  # noqa: E402


# ── the soundtrack ──────────────────────────────────────────────────────────


def _render(tmp_path, name, audible_spans, duration=6.0):
    """A tiny real mp4 whose audio is loud inside `audible_spans` and digital
    zero everywhere else."""
    import numpy as np
    from moviepy import AudioArrayClip, ColorClip

    fps = 8000
    t = np.arange(int(duration * fps)) / fps
    wave = np.zeros_like(t)
    for a, b in audible_spans:
        mask = (t >= a) & (t < b)
        wave[mask] = 0.4 * np.sin(2 * np.pi * 220 * t[mask])
    audio = AudioArrayClip(np.stack([wave, wave], axis=1), fps=fps)
    clip = ColorClip((64, 48), color=(10, 10, 10), duration=duration)
    clip = clip.with_fps(8).with_audio(audio)
    out = str(tmp_path / name)
    clip.write_videofile(out, codec="libx264", audio_codec="aac", logger=None)
    clip.close()
    return out


def test_a_film_with_a_real_soundtrack_says_nothing(tmp_path):
    path = _render(tmp_path, "scored.mp4", [(0.0, 6.0)])

    assert check_master_is_not_mostly_silent(path) is None


def test_a_held_beat_is_not_a_missing_soundtrack(tmp_path):
    """A film may sit in silence for a moment on purpose."""
    path = _render(tmp_path, "beat.mp4", [(0.0, 2.4), (3.6, 6.0)])

    assert check_master_is_not_mostly_silent(path) is None


def test_the_delivered_drama_that_prompted_this_is_reported(tmp_path):
    """12 audible seconds in 60, to scale: 1.2 in 6."""
    path = _render(tmp_path, "hollow.mp4", [(0.0, 1.2)])

    notice = check_master_is_not_mostly_silent(path)

    assert notice is not None
    assert "no sound at all" in notice
    assert "music and sound effects" in notice


def test_it_is_logged_with_the_knobs_to_check(tmp_path, caplog):
    path = _render(tmp_path, "hollow2.mp4", [(0.0, 1.2)])

    with caplog.at_level(logging.WARNING):
        check_master_is_not_mostly_silent(path)

    assert any("MUSEFORGE_FOLEY" in r.getMessage() for r in caplog.records)


def test_a_missing_file_is_not_evidence_of_a_problem():
    assert check_master_is_not_mostly_silent(None) is None
    assert check_master_is_not_mostly_silent("/nope/none.mp4") is None


# ── the cast ────────────────────────────────────────────────────────────────


class _Account(ElevenLabsVoiceGenerator):
    """Stands in for an account that holds only some of the library voices."""

    def __init__(self, holds, **kw):
        super().__init__(api_key="test-key", working_dir="/tmp", **kw)
        self._holds = holds

    async def list_voices(self):
        return [{"voice_id": v, "name": f"name-{v[:4]}"} for v in self._holds]


def _woman(idx=0, name="Mara Voss"):
    return CharacterInScene(
        idx=idx, name=name, static_features="woman in her late thirties"
    )


@pytest.mark.asyncio
async def test_a_cast_the_account_can_speak_with_is_left_alone():
    gen = _Account(list(ElevenLabsVoiceGenerator.SYSTEM_VOICE_IDS))
    before = gen.cast_characters([_woman()])

    assert await gen.verify_cast() == before


@pytest.mark.asyncio
async def test_an_unusable_voice_is_replaced_inside_the_right_gender(caplog):
    """The regression, in the shape it was delivered: the account cannot use
    the voice this woman was cast with. Substituting is the endpoint's own
    behaviour and it does not care about gender; this does."""
    gen = _Account(list(ElevenLabsVoiceGenerator.SYSTEM_VOICE_IDS))
    cast = gen.cast_characters([_woman()])
    # Everything except the voice she was actually cast with.
    usable_female = next(
        v for v in ElevenLabsVoiceGenerator.FEMALE_VOICE_IDS
        if v != cast["mara voss"]
    )
    gen._holds = [usable_female] + list(ElevenLabsVoiceGenerator.MALE_VOICE_IDS)

    with caplog.at_level(logging.ERROR):
        after = await gen.verify_cast()

    assert after["mara voss"] == usable_female
    assert after["mara voss"] in ElevenLabsVoiceGenerator.FEMALE_VOICE_IDS
    assert any("not available to this account" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_two_characters_are_not_re_cast_onto_the_same_voice():
    usable = list(ElevenLabsVoiceGenerator.FEMALE_VOICE_IDS[:2])
    gen = _Account(usable)
    gen.cast_characters([_woman(0, "Mara"), _woman(1, "Noor")])

    after = await gen.verify_cast()

    assert len(set(after.values())) == 2


@pytest.mark.asyncio
async def test_an_account_that_cannot_be_asked_casts_exactly_as_before(caplog):
    """Fail-open in the direction of shipping: a drama still gets made."""

    class _Unreachable(ElevenLabsVoiceGenerator):
        async def list_voices(self):
            raise RuntimeError("network down")

    gen = _Unreachable(api_key="test-key", working_dir="/tmp")
    before = gen.cast_characters([_woman()])

    with caplog.at_level(logging.WARNING):
        assert await gen.verify_cast() == before

    assert any("casting as-is" in r.getMessage() for r in caplog.records)


def test_the_cast_is_written_down(caplog):
    """A wrong voice is invisible in the code and obvious in the film. The one
    thing that makes it diagnosable afterwards is knowing what was asked for."""
    gen = ElevenLabsVoiceGenerator(api_key="test-key", working_dir="/tmp")

    with caplog.at_level(logging.INFO):
        gen.cast_characters([_woman()])

    assert any(
        "Cast:" in r.getMessage() and "mara voss=" in r.getMessage()
        for r in caplog.records
    )
