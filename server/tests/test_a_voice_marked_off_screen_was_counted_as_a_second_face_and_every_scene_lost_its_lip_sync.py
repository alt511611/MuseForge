"""Job 5b886720 (2026-11-23): four scenes, four refusals, no lip-sync at all.

The script wrote the off-screen voices the way scripts do -- "Yusuf (O.S.)",
"Anlatıcı (V.O.)" -- and every comparison in the pipeline took the whole string
for the name. "Yusuf (O.S.)" was therefore a second visible speaker in a scene
where only Deniz is on screen, and the log said "multiple visible speakers in
one combined dialogue track; keeping it as voice-over" for all four.

The same string also failed to find its own voice (a hash-assigned stranger
spoke Yusuf's O.S. line) and made "Arif (O.S.)" look like a speaker nobody
staged.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from interfaces.speaker import is_marked_unseen, speaker_key
from pipelines.idea2video import (
    _format_scene_dialogue,
    _has_one_visible_speaker,
    _off_screen_speech_spans,
)


def _lines(*names, **timing):
    out = []
    for i, name in enumerate(names):
        track = {"character": name, "line": f"line {i}"}
        if timing:
            track["start_seconds"], track["end_seconds"] = float(i), float(i) + 1.0
        out.append(track)
    return out


# ── the name ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "written",
    ["Yusuf (O.S.)", "yusuf (o.s.)", "Yusuf (OS)", "Yusuf [O.S.]", "Yusuf (off-screen)",
     "Yusuf (V.O.)", "Yusuf (voice over)", "Yusuf (voiceover)", "Yusuf (O.S.) (V.O.)", "  Yusuf  (O.S.) "],
)
def test_every_spelling_of_the_marker_is_the_same_person(written):
    assert speaker_key(written) == "yusuf"
    assert is_marked_unseen(written)


@pytest.mark.parametrize("plain", ["Yusuf", "Oscar", "Vo", "Os", "Yusuf (young)", "Anna (angry)", "", None])
def test_a_name_that_only_looks_like_a_marker_is_left_alone(plain):
    assert not is_marked_unseen(plain)
    assert speaker_key(plain) == str(plain or "").strip().casefold()


# ── the lip-sync gate ────────────────────────────────────────────────────────


def test_a_close_up_with_one_face_and_an_off_screen_voice_can_be_synced():
    assert _has_one_visible_speaker(_lines("Deniz", "Yusuf (O.S.)"))


def test_a_narrator_over_one_face_can_be_synced():
    assert _has_one_visible_speaker(_lines("Deniz", "Anlatıcı (V.O.)"))


def test_two_visible_speakers_are_still_refused():
    assert not _has_one_visible_speaker(_lines("Deniz", "Yusuf"))


def test_a_marked_speaker_does_not_hide_a_real_second_face():
    assert not _has_one_visible_speaker(_lines("Deniz", "Yusuf", "Arif (O.S.)"))


def test_the_same_person_marked_and_unmarked_is_still_one_speaker():
    assert _has_one_visible_speaker(_lines("Deniz", "Deniz (V.O.)"))


def test_the_older_off_screen_set_still_works():
    assert _has_one_visible_speaker(_lines("Deniz", "Yusuf"), {"yusuf"})


# ── what the provider is handed ──────────────────────────────────────────────


def test_a_marked_line_is_silenced_in_the_guide_track_so_the_mouth_does_not_say_it():
    spans, syncable = _off_screen_speech_spans(_lines("Deniz", "Yusuf (O.S.)", timing=True), set())
    assert spans == [(1.0, 2.0)]
    assert syncable


def test_a_scene_spoken_only_by_marked_voices_has_no_mouth_to_drive():
    _, syncable = _off_screen_speech_spans(_lines("Anlatıcı (V.O.)", "Yusuf (O.S.)", timing=True), set())
    assert not syncable


# ── the dialogue the storyboard artist reads ─────────────────────────────────


def test_a_marker_the_writer_already_wrote_is_not_written_twice():
    text = _format_scene_dialogue(
        [{"character": "Yusuf (O.S.)", "line": "Sabret."}], off_screen={"yusuf"}
    )
    assert text.count("O.S.") == 1


# ── the voice ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("module", ["tools.elevenlabs_voice_generator", "tools.muapi_voice_generator"])
def test_a_marked_line_is_spoken_in_the_characters_own_voice(module):
    import importlib

    mod = importlib.import_module(module)
    cls = next(v for k, v in vars(mod).items() if k.endswith("VoiceGenerator") and isinstance(v, type))
    gen = cls(api_key="k")
    gen._character_voices["yusuf"] = "voice-yusuf"
    assert gen.voice_id_for_character("Yusuf (O.S.)") == "voice-yusuf"
    assert gen.voice_id_for_character("YUSUF") == "voice-yusuf"
