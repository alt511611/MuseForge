"""Jobs 8d082bf7 and 21a87c5a: "Scene 2 has multiple visible speakers" -- who?

The scene is Mira and a dispatcher heard over a radio. Either the dispatcher
was counted or a second visible voice exists; the line named neither, so the
cause could not be read from the log. It now names the speakers it counted and
the off-screen set it subtracted.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines.idea2video import _has_one_visible_speaker, _visible_speaker_names  # noqa: E402

LINES = [
    {"character": "Lena", "line": "Refuge, this is dispatch."},
    {"character": "Mira", "line": "I'm here."},
]


def test_the_names_are_the_ones_the_check_counts():
    assert _visible_speaker_names(LINES, set()) == ["Lena", "Mira"]
    assert _has_one_visible_speaker(LINES, set()) is False


def test_an_off_screen_voice_is_subtracted_from_both():
    assert _visible_speaker_names(LINES, {"lena"}) == ["Mira"]
    assert _has_one_visible_speaker(LINES, {"lena"}) is True


def test_a_marked_voice_is_not_a_visible_speaker():
    lines = [{"character": "Lena (O.S.)", "line": "Say again."}, LINES[1]]
    assert _visible_speaker_names(lines, set()) == ["Mira"]
