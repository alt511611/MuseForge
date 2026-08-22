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


@pytest.fixture
def burns(monkeypatch):
    """Record which caption renderer was asked to do the work."""
    used = []

    async def fake_kinetic(video_path, output_path, tracks, scene_paths=None):
        used.append("kinetic")
        with open(output_path, "wb") as f:
            f.write(b"kinetic")
        return output_path

    def fake_srt(tracks, scene_paths=None):
        used.append("broadcast")
        return "1\n00:00:00,000 --> 00:00:02,000\nSöz.\n"

    monkeypatch.setenv("MUSEFORGE_WORD_CAPTIONS", "1")
    monkeypatch.setattr(mod, "_burn_kinetic_captions", fake_kinetic)
    monkeypatch.setattr(mod, "build_srt_from_dialogue_tracks", fake_srt)
    return used


async def _burn(tmp_path, size):
    clip = tmp_path / "master.mp4"
    clip.write_bytes(b"master")
    await mod.burn_subtitles(
        str(clip),
        str(tmp_path / "out.mp4"),
        [{"scene_index": 0, "line": "Söz.", "audio_url": "https://cdn/s0.mp3"}],
    )


@pytest.mark.asyncio
async def test_a_landscape_master_gets_broadcast_captions(
    burns, monkeypatch, tmp_path
):
    monkeypatch.setattr(mod, "_probe_video_size", lambda path: (1920, 1080))
    await _burn(tmp_path, (1920, 1080))
    assert burns == ["broadcast"], (
        "phone-style word captions were burnt into a cinema master"
    )


@pytest.mark.asyncio
async def test_a_vertical_master_still_gets_the_feed_style(
    burns, monkeypatch, tmp_path
):
    monkeypatch.setattr(mod, "_probe_video_size", lambda path: (1080, 1920))
    await _burn(tmp_path, (1080, 1920))
    assert burns == ["kinetic"]


@pytest.mark.asyncio
async def test_a_square_master_counts_as_a_feed(burns, monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "_probe_video_size", lambda path: (1080, 1080))
    await _burn(tmp_path, (1080, 1080))
    assert burns == ["kinetic"]


@pytest.mark.asyncio
async def test_an_unreadable_master_keeps_the_deployment_s_choice(
    burns, monkeypatch, tmp_path
):
    """(0, 0) is "could not probe", not "landscape". Guessing against the
    operator's own flag on a failed probe would silently change the house
    style of every job on a box whose ffmpeg is having a bad day."""
    monkeypatch.setattr(mod, "_probe_video_size", lambda path: (0, 0))
    await _burn(tmp_path, (0, 0))
    assert burns == ["kinetic"]


@pytest.mark.asyncio
async def test_the_flag_still_decides_before_the_shape_does(
    burns, monkeypatch, tmp_path
):
    monkeypatch.setenv("MUSEFORGE_WORD_CAPTIONS", "0")
    monkeypatch.setattr(mod, "_probe_video_size", lambda path: (1080, 1920))
    await _burn(tmp_path, (1080, 1920))
    assert burns == ["broadcast"]
