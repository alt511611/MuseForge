"""Word-at-a-time captions, and the emotion that drives the delivery.

Two things arrive in the same ElevenLabs response and only one of them was
ever read: ``voice_segments`` (a start and end per line, already used) and
``alignment`` (a start and end per CHARACTER). The second is what vertical
video's word-by-word caption style needs, and it costs nothing extra -- it is
in a response the job has already paid for.

Everything here is measured or absent. A karaoke caption whose highlight is on
the wrong word is worse than no karaoke caption at all, so a provider that
returns no alignment produces no word cues rather than estimated ones.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines.idea2video import (  # noqa: E402
    build_srt_from_dialogue_tracks,
    chunk_words_into_cues,
)
from tools.elevenlabs_voice_generator import ElevenLabsVoiceGenerator  # noqa: E402


def _alignment(text: str, per_char: float = 0.1):
    """A character alignment of the shape the provider returns."""
    return {
        "characters": list(text),
        "character_start_times_seconds": [i * per_char for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) * per_char for i in range(len(text))],
    }


# --- reading the alignment ---------------------------------------------


def test_words_are_read_off_the_character_stream():
    lines = [{"line": "Beni burada bırakma", "spoken_text": "Beni burada bırakma"}]
    words = ElevenLabsVoiceGenerator._word_timings(_alignment("Beni burada bırakma"), lines)
    assert [w["text"] for w in words[0]] == ["Beni", "burada", "bırakma"]
    assert words[0][0]["start"] == pytest.approx(0.0)
    assert words[0][1]["start"] < words[0][2]["start"]


def test_an_audio_tag_does_not_shift_the_words():
    """The tag is sent but not spoken; the words after it must still land."""
    lines = [{"line": "Gitme", "spoken_text": "[voice breaking] Gitme"}]
    words = ElevenLabsVoiceGenerator._word_timings(
        _alignment("[voice breaking] Gitme"), lines
    )
    assert [w["text"] for w in words[0]] == ["Gitme"]


def test_an_audio_tag_is_never_shown_to_the_viewer():
    """Measured on a delivered drama: the picture read "[fearfully] Control's
    gone" in burned-in captions.

    The tag is a direction to the actor. It has to be WALKED, because the
    character stream contains it and skipping it would throw the rest of the
    line out of alignment — but it must never be emitted as a caption word.
    """
    lines = [{"line": "Control's gone.", "spoken_text": "[fearfully] Control's gone."}]
    words = ElevenLabsVoiceGenerator._word_timings(
        _alignment("[fearfully] Control's gone."), lines
    )

    shown = [w["text"] for w in words[0]]
    assert shown == ["Control's", "gone."]
    assert not any("[" in w or "]" in w for w in shown)
    # ...and the surviving words still carry the times the provider measured,
    # which start AFTER the tag's characters.
    assert words[0][0]["start"] == pytest.approx(1.2)


def test_two_lines_do_not_share_a_cursor():
    lines = [
        {"line": "Bir", "spoken_text": "Bir"},
        {"line": "Iki", "spoken_text": "Iki"},
    ]
    words = ElevenLabsVoiceGenerator._word_timings(_alignment("Bir Iki"), lines)
    assert words[0][0]["text"] == "Bir"
    assert words[1][0]["text"] == "Iki"
    # The second line starts after the first has finished.
    assert words[1][0]["start"] >= words[0][-1]["end"]


def test_a_missing_or_malformed_alignment_yields_nothing():
    lines = [{"line": "Gitme", "spoken_text": "Gitme"}]
    assert ElevenLabsVoiceGenerator._word_timings(None, lines) == {}
    assert ElevenLabsVoiceGenerator._word_timings({}, lines) == {}
    assert (
        ElevenLabsVoiceGenerator._word_timings(
            {"characters": ["a", "b"], "character_start_times_seconds": [0.0]}, lines
        )
        == {}
    )


# --- grouping into cues ------------------------------------------------


def test_cues_are_short_bursts():
    words = [
        {"text": f"w{i}", "start": i * 0.3, "end": (i + 1) * 0.3} for i in range(7)
    ]
    cues = chunk_words_into_cues(words)
    assert all(len(cue["text"].split()) <= 3 for cue in cues)
    assert cues[0]["start"] == pytest.approx(0.0)
    assert cues[-1]["end"] == pytest.approx(2.1)


def test_a_cue_never_runs_across_the_end_of_a_sentence():
    words = [
        {"text": "Bitti.", "start": 0.0, "end": 0.5},
        {"text": "Yeni", "start": 0.6, "end": 1.0},
    ]
    cues = chunk_words_into_cues(words)
    assert cues[0]["text"] == "Bitti."


def test_a_slow_word_closes_its_cue_on_time():
    words = [
        {"text": "Uzuuuun", "start": 0.0, "end": 2.0},
        {"text": "sonra", "start": 2.0, "end": 2.4},
    ]
    cues = chunk_words_into_cues(words)
    assert cues[0]["text"] == "Uzuuuun"


# --- end to end in the SRT ---------------------------------------------


def _track(**extra):
    base = {
        "scene_index": 0,
        "character": "Ayse",
        "line": "Beni burada bırakma",
        "start_seconds": 0.0,
        "end_seconds": 1.9,
        "duration_seconds": 1.9,
    }
    base.update(extra)
    return base


def _cue_count(srt: str) -> int:
    return sum(1 for line in srt.splitlines() if " --> " in line)


def test_word_captions_are_off_by_default(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_WORD_CAPTIONS", raising=False)
    import pipelines.idea2video as pipeline

    monkeypatch.setattr(pipeline, "_scene_boundaries", lambda paths: [0.0, 6.0])
    srt = build_srt_from_dialogue_tracks(
        [
            _track(
                words=[
                    {"text": "Beni", "start": 0.0, "end": 0.5},
                    {"text": "burada", "start": 0.5, "end": 1.2},
                    {"text": "bırakma", "start": 1.2, "end": 1.9},
                ]
            )
        ],
        scene_paths=["a.mp4"],
    )
    assert _cue_count(srt) == 1
    assert "Beni burada bırakma" in srt


def test_word_captions_replace_the_line_cue_when_enabled(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_WORD_CAPTIONS", "1")
    import pipelines.idea2video as pipeline

    monkeypatch.setattr(pipeline, "_scene_boundaries", lambda paths: [0.0, 6.0])
    srt = build_srt_from_dialogue_tracks(
        [
            _track(
                words=[
                    {"text": "Beni", "start": 0.0, "end": 0.5},
                    {"text": "burada", "start": 0.5, "end": 1.2},
                    {"text": "bırakma", "start": 1.2, "end": 1.9},
                ]
            )
        ],
        scene_paths=["a.mp4"],
    )
    # One burst, not one block held for the whole line -- and no duplicate
    # whole-line cue underneath it.
    assert _cue_count(srt) == 1
    assert "Beni burada bırakma" in srt
    assert "Ayse:" not in srt


def test_a_provider_without_word_timings_still_gets_line_captions(monkeypatch):
    """The MuAPI voice path measures nothing per word; it must not lose its
    captions because a flag was switched on."""
    monkeypatch.setenv("MUSEFORGE_WORD_CAPTIONS", "1")
    import pipelines.idea2video as pipeline

    monkeypatch.setattr(pipeline, "_scene_boundaries", lambda paths: [0.0, 6.0])
    srt = build_srt_from_dialogue_tracks([_track()], scene_paths=["a.mp4"])
    assert "Beni burada bırakma" in srt


# --- delivery ----------------------------------------------------------


def test_the_scenes_emotion_reaches_the_first_spoken_line():
    lines = ElevenLabsVoiceGenerator._direct_delivery(
        [{"line": "Gitme", "character": "Ayse", "voice_id": "v"},
         {"line": "Kal", "character": "Kemal", "voice_id": "w"}],
        emotion="tearful goodbye",
    )
    assert lines[0]["spoken_text"].startswith("[voice breaking] ")
    # Only the first: v3 carries delivery forward, and re-tagging every line
    # reads as an actor being re-directed between sentences.
    assert lines[1]["spoken_text"] == "Kal"
    # The written line is untouched, because that is what the caption shows.
    assert lines[0]["line"] == "Gitme"


def test_an_unmapped_emotion_leaves_the_line_alone():
    lines = ElevenLabsVoiceGenerator._direct_delivery(
        [{"line": "Gitme", "character": "Ayse", "voice_id": "v"}],
        emotion="something nobody mapped",
    )
    assert lines[0]["spoken_text"] == "Gitme"
