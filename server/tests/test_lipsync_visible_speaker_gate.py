"""Lip sync may drive one visible speaker, never a combined two-hander."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines.idea2video import _has_one_visible_speaker


def _line(character, line="One short line."):
    return {"character": character, "line": line}


def test_one_visible_speaker_is_syncable():
    assert _has_one_visible_speaker([_line("Mara"), _line("Mara", "Wait.")])


def test_two_visible_speakers_stay_voice_over():
    assert not _has_one_visible_speaker([_line("Mara"), _line("Ilan")])


def test_off_screen_voice_does_not_disqualify_the_visible_speaker():
    assert _has_one_visible_speaker(
        [_line("Mara"), _line("Control Room")], {"control room"}
    )


def test_blank_legacy_speaker_names_fail_open():
    assert _has_one_visible_speaker([_line("", "Who is there?")])
