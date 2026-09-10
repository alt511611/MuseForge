"""The video model, or us -- and what stops happening once it is the model.

A backend that speaks changes three stages at once, and getting any one of
them wrong is worse than not having the feature:

* the voice generator, which would otherwise make a track nobody needs;
* the lip-sync pass -- 329 seconds, 36% of a delivered render -- which exists
  ONLY because the picture used to arrive mute;
* the mixer, which would lay a second voice over a picture that is already
  speaking, so every line is heard twice, slightly out of phase.

The decision is therefore made once, in picture_carries_dialogue, and every
stage reads it from there.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipelines.idea2video import caption_only_tracks, picture_carries_dialogue

MULTISHOT = "fal-ai/kling-video/v3/standard/image-to-video"
SINGLE = "kling-v3.0-standard-image-to-video"


class _Speaks:
    MULTISHOT_ENDPOINT = MULTISHOT
    multishot = True

    async def generate_scene_take(self, *a, **k):  # pragma: no cover
        ...


class _CannotCut:
    MULTISHOT_ENDPOINT = SINGLE
    multishot = True

    async def generate_scene_take(self, *a, **k):  # pragma: no cover
        ...


class _NotSelected:
    MULTISHOT_ENDPOINT = MULTISHOT
    multishot = False

    async def generate_scene_take(self, *a, **k):  # pragma: no cover
        ...


# --------------------------------------------------------------------------
# The decision
# --------------------------------------------------------------------------

def test_the_picture_speaks_only_when_it_can_speak_this_films_language():
    """"Has native audio" is not a property an endpoint has; a LANGUAGE is.

    Kling v3 covers English and Chinese. A Turkish drama rendered on it comes
    back spoken in translated English -- which is not a degraded version of
    the product, it is a different film.
    """
    assert picture_carries_dialogue(_Speaks(), "en") is True
    assert picture_carries_dialogue(_Speaks(), "zh") is True
    assert picture_carries_dialogue(_Speaks(), "tr") is False
    assert picture_carries_dialogue(_Speaks(), "es") is False


def test_a_backend_that_cannot_cut_never_speaks_for_the_picture():
    """The take path is where a backend's own audio can reach the film."""
    assert picture_carries_dialogue(_CannotCut(), "en") is False
    assert picture_carries_dialogue(_NotSelected(), "en") is False
    assert picture_carries_dialogue(object(), "en") is False
    assert picture_carries_dialogue(None, "en") is False


# --------------------------------------------------------------------------
# The lip-sync pass leaves a scene that was never out of sync alone
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_lipsync_skips_a_scene_that_said_its_own_lines(monkeypatch, tmp_path):
    """Driving a mouth from the audio it already produced is a generation
    spent re-creating sync that was never lost -- and the sync pass returns
    only the spoken stretch, so it would also cut the scene down to its line.
    """
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    pipeline = Idea2VideoPipeline(api_key="test-key", demo=False)

    synced_calls = []

    class _FakeLipsync:
        def available(self):
            return True

        async def sync(self, *a, **k):  # pragma: no cover
            synced_calls.append(a)
            return "https://cdn/synced.mp4"

    monkeypatch.setattr(
        "tools.muapi_lipsync.make_lipsync", lambda demo=False: _FakeLipsync()
    )

    clip = tmp_path / "scene0.mp4"
    clip.write_bytes(b"fake")

    tracks = [
        {
            "character": "Vivian Marsh",
            "line": "Play your cards.",
            "scene_index": 0,
            "audio_url": str(tmp_path / "take.m4a"),
            "speaks_for_itself": True,
        }
    ]

    synced = await pipeline._lipsync_scenes(
        scene_paths=[str(clip)],
        dialogue_tracks=tracks,
        working_dir=str(tmp_path),
        progress=_noop_progress,
        requested=True,
    )

    assert synced == [], "A self-voiced scene must not be sent to the sync pass."
    assert synced_calls == []


async def _noop_progress(*a, **k):
    return None


# --------------------------------------------------------------------------
# The take's own voice becomes an ordinary dialogue layer
# --------------------------------------------------------------------------

def test_the_takes_audio_rides_the_first_line_like_any_voiced_scene():
    """The convention the voice generator already uses: one combined file per
    scene, attached to its first line, the rest read for captions alone."""
    lines = [
        {"character": "Vivian Marsh", "line": "Play your cards."},
        {"character": "Julian Voss", "line": "Chips don't lie."},
    ]
    rows = caption_only_tracks(lines, 0)
    assert len(rows) == 2
    assert all("audio_url" not in row for row in rows), (
        "caption_only_tracks must stay audio-free; the caller attaches it."
    )

    rows[0]["audio_url"] = "file:///tmp/take.m4a"
    rows[0]["speaks_for_itself"] = True
    assert rows[1].get("audio_url") is None, "Only the first row carries audio."


@pytest.mark.asyncio
async def test_a_take_that_came_back_mute_is_voiced_the_usual_way(monkeypatch, tmp_path):
    """extract_audio_track returns None for a clip with no audio stream, and
    the scene must then behave exactly like every scene before this feature."""
    from pipelines.script2video import extract_audio_track

    silent = tmp_path / "silent.mp4"
    silent.write_bytes(b"not really a video")

    result = await extract_audio_track(str(silent), str(tmp_path / "out.m4a"))
    assert result is None
    assert not (tmp_path / "out.m4a").exists(), (
        "A failed extraction must not leave an empty file the mixer would try "
        "to lay down."
    )


@pytest.mark.asyncio
async def test_a_real_soundtrack_is_lifted_out_of_the_picture(tmp_path):
    """The join is `-an` and the mixer maps `0:v`, so dialogue left inside the
    picture never reaches the master. This is what rescues it."""
    import asyncio

    from pipelines.script2video import _ffmpeg_binary, extract_audio_track

    source = tmp_path / "withsound.mp4"
    process = await asyncio.create_subprocess_exec(
        _ffmpeg_binary(), "-y",
        "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", str(source),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()
    if process.returncode != 0:
        pytest.skip("ffmpeg could not build the fixture")

    out = await extract_audio_track(str(source), str(tmp_path / "voice.m4a"))
    assert out is not None
    assert os.path.getsize(out) > 0
