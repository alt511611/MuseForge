"""Word-by-word captions are a vertical-feed style, not a house style.

interfaces/ass_captions exists because a vertical drama is watched muted on a
feed: three words at a time, in accent yellow, sized for a phone at arm's
length, with the word being spoken picked out. That is right for 9:16 and it
is the single most recognisably un-cinematic thing you can burn into a 16:9
master -- which is exactly what a delivered 1920x1080 drama came back with.

The flag that turns the style on (MUSEFORGE_WORD_CAPTIONS) is set per
DEPLOYMENT; the shape of the picture is chosen per JOB. So a deployment that
serves both had no way to get the right captions on either. The style now
follows the picture it is being written onto.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as mod  # noqa: E402


TRACKS = [
    {
        "scene_index": 0,
        "line": "Söz.",
        "audio_url": "https://cdn/s0.mp3",
        "words": [{"word": "Söz.", "start": 0.0, "end": 0.6}],
    }
]


@pytest.fixture
def master(monkeypatch, tmp_path):
    """A master file whose measured size the test chooses."""
    clip = tmp_path / "drama_with_music.mp4"
    clip.write_bytes(b"master")

    def _size(size):
        monkeypatch.setattr(mod, "_probe_video_size", lambda path: size)

    monkeypatch.setenv("MUSEFORGE_WORD_CAPTIONS", "1")
    monkeypatch.setattr(
        mod,
        "build_srt_from_dialogue_tracks",
        lambda tracks, scene_paths=None: "1\n00:00:00,000 --> 00:00:02,000\nSöz.\n",
    )
    monkeypatch.setattr(
        mod, "build_kinetic_ass", lambda *a, **kw: "[Script Info]\nDialogue: kinetic\n"
    )
    return str(clip), _size


def _style(video_path):
    """Which renderer's filter came back: "kinetic", "broadcast" or None."""
    vf, path = mod.build_caption_filter(video_path, TRACKS)
    if path:
        os.unlink(path)
    if not vf:
        return None
    return "kinetic" if vf.startswith("ass=") else "broadcast"


def test_a_landscape_master_gets_broadcast_captions(master):
    path, size = master
    size((1920, 1080))
    assert _style(path) == "broadcast", (
        "phone-style word captions were burnt into a cinema master"
    )


def test_a_vertical_master_still_gets_the_feed_style(master):
    path, size = master
    size((1080, 1920))
    assert _style(path) == "kinetic"


def test_a_square_master_counts_as_a_feed(master):
    path, size = master
    size((1080, 1080))
    assert _style(path) == "kinetic"


def test_an_unreadable_master_keeps_the_deployment_s_choice(master):
    """(0, 0) is "could not probe", not "landscape". Guessing against the
    operator's own flag on a failed probe would silently change the house
    style of every job on a box whose ffmpeg is having a bad day."""
    path, size = master
    size((0, 0))
    assert _style(path) == "kinetic"


def test_the_flag_still_decides_before_the_shape_does(master, monkeypatch):
    path, size = master
    monkeypatch.setenv("MUSEFORGE_WORD_CAPTIONS", "0")
    size((1080, 1920))
    assert _style(path) == "broadcast"


def test_a_drama_with_no_dialogue_has_nothing_to_burn(master):
    path, _ = master
    assert mod.build_caption_filter(path, []) == ("", None)
