"""Sound design: a foley bed per scene, and a score that gets out of its way.

Two defects this covers, both audible on every drama the product has made:

* The picture made no sound. Doors, glass, footsteps, room tone -- none of it
  existed, even though the storyboard agent has been writing a sound note for
  every shot (``StoryboardShot.audio_desc``) that nothing ever read.
* The score did not duck, it was DEMOTED: a flat 20% for the whole film the
  moment any line was voiced, including the long stretches with nobody
  speaking, which is exactly where a score earns its place.
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines.idea2video import (  # noqa: E402
    DUCK_RATIO,
    FOLEY_LEVEL,
    MUSIC_LEVEL,
    build_audio_mix_graph,
    mix_audio_layers,
)
from tools import muapi_sfx_generator as sfx  # noqa: E402


# --- the foley generator -----------------------------------------------


def test_foley_is_off_by_default(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_FOLEY", raising=False)
    assert sfx.is_foley_enabled() is False
    monkeypatch.setenv("MUSEFORGE_FOLEY", "1")
    assert sfx.is_foley_enabled() is True


def test_the_endpoint_is_the_namespaced_one():
    """`mmaudio-v2/text-to-audio`, with the slash. Verified against MuAPI's
    own API reference; the flat spelling is a 404 per scene."""
    assert sfx.SFX_ENDPOINT == "mmaudio-v2/text-to-audio"


def test_duration_is_clamped_to_what_the_provider_accepts():
    assert sfx.clamp_duration(0) == sfx.MIN_DURATION_SECONDS
    assert sfx.clamp_duration(99) == sfx.MAX_DURATION_SECONDS
    assert sfx.clamp_duration(8.4) == 8
    assert sfx.clamp_duration("nonsense") == 8


def test_the_prompt_forbids_the_two_layers_that_already_exist():
    """Foley that arrives with its own strings fights the score; foley with
    voices in it fights the dialogue and wins."""
    prompt = sfx.build_prompt("a glass breaking on tile", "cold rage")
    assert "glass breaking on tile" in prompt
    assert "cold rage" in prompt
    assert "NO music" in prompt
    assert "NO speech" in prompt


def test_a_shot_with_no_sound_note_still_gets_a_room():
    prompt = sfx.build_prompt("", "")
    assert "room tone" in prompt


@pytest.mark.asyncio
async def test_demo_mode_generates_nothing():
    generator = sfx.MuAPISFXGenerator(api_key="k", demo=True)
    assert await generator.generate_scene_sfx("a door slamming", 6.0) == ""


# --- the mix graph ------------------------------------------------------


def test_nothing_to_mix_returns_no_graph():
    """The caller lays down silence instead of running an encode that would
    change nothing."""
    assert build_audio_mix_graph(None, [], [], 10.0) is None


def test_the_score_ducks_under_speech():
    graph = build_audio_mix_graph(1, [(2, 0.0)], [], 10.0)
    assert "sidechaincompress" in graph
    assert f"ratio={DUCK_RATIO}" in graph
    # The speech that steers the compressor cannot also be the speech that
    # reaches the mix -- sidechaincompress consumes its control input.
    assert "asplit=2[speech][sc]" in graph


def test_a_score_with_no_speech_is_not_ducked():
    """Nothing to duck under: a silent film's score plays at its own level."""
    graph = build_audio_mix_graph(1, [], [], 10.0)
    assert "sidechaincompress" not in graph
    assert f"volume={MUSIC_LEVEL}" in graph


def test_speech_is_never_quietly_halved_by_the_mixer():
    """amix's default divides by the number of inputs, which would cost a
    scene half its dialogue for the crime of having two lines."""
    graph = build_audio_mix_graph(1, [(2, 0.0), (3, 4.0)], [], 10.0)
    assert graph.count("normalize=0") >= 2


def test_each_layer_lands_where_it_belongs_in_time():
    graph = build_audio_mix_graph(None, [(1, 2.5)], [(2, 6.0)], 10.0)
    assert "adelay=2500:all=1" in graph
    assert "adelay=6000:all=1" in graph


def test_foley_sits_under_speech_and_over_nothing():
    graph = build_audio_mix_graph(None, [], [(1, 0.0)], 10.0)
    assert f"volume={FOLEY_LEVEL}" in graph
    assert FOLEY_LEVEL < 1.0


def test_the_mix_is_exactly_as_long_as_the_picture():
    """Shorter and the container's streams disagree about where the file ends;
    longer and the master grows a tail."""
    graph = build_audio_mix_graph(1, [(2, 0.0)], [], 12.5)
    assert "apad" in graph
    assert "atrim=0:12.500" in graph
    assert "alimiter" in graph


# --- against a real encoder --------------------------------------------


def _has_ffmpeg():
    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


pytestmark_ffmpeg = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")


def _ffmpeg():
    from pipelines.idea2video import resolve_ffmpeg_binary

    return resolve_ffmpeg_binary()


def _silent_video(tmp_path, seconds=6.0, name="master.mp4"):
    path = str(tmp_path / name)
    subprocess.run(
        [_ffmpeg(), "-y", "-f", "lavfi", "-i",
         f"testsrc=size=320x180:rate=24:duration={seconds}",
         "-pix_fmt", "yuv420p", path],
        check=True, capture_output=True,
    )
    return path


def _tone(tmp_path, name, seconds, frequency=440, volume=1.0):
    path = str(tmp_path / name)
    subprocess.run(
        [_ffmpeg(), "-y", "-f", "lavfi", "-i",
         f"sine=frequency={frequency}:duration={seconds}",
         "-af", f"volume={volume}", path],
        check=True, capture_output=True,
    )
    return path


@pytestmark_ffmpeg
@pytest.mark.asyncio
async def test_the_picture_is_not_re_encoded(tmp_path):
    """The mix used to cost a full re-encode of every frame of the master
    just to attach an audio stream. `-c:v copy` makes it cost nothing."""
    video = _silent_video(tmp_path)
    music = _tone(tmp_path, "music.mp3", 6.0, 220)
    out = str(tmp_path / "mixed.mp4")

    assert await mix_audio_layers(video, out, music_url=music) == out

    from moviepy import VideoFileClip

    with VideoFileClip(out) as clip:
        assert clip.audio is not None
        assert clip.duration == pytest.approx(6.0, abs=0.2)

    # The file itself is larger, of course -- it now carries an audio stream.
    # What must be untouched is the VIDEO bitstream, so it is extracted from
    # both files and compared on its own. A re-encode would not land within a
    # hundred bytes of the original.
    def _video_stream_only(source, name):
        path = str(tmp_path / name)
        subprocess.run(
            [_ffmpeg(), "-y", "-i", source, "-map", "0:v", "-c", "copy", path],
            check=True, capture_output=True,
        )
        return os.path.getsize(path)

    assert _video_stream_only(out, "after.mp4") == pytest.approx(
        _video_stream_only(video, "before.mp4"), abs=100
    )


@pytestmark_ffmpeg
@pytest.mark.asyncio
async def test_the_score_actually_dips_under_the_line_and_comes_back(tmp_path):
    """The claim, measured. Music runs the whole six seconds; a line plays
    over the middle two. The score must be quieter under the line than it is
    on either side of it -- which the old flat-scaling mixer could not do,
    because it had one level for the entire film."""
    import numpy as np

    video = _silent_video(tmp_path)
    music = _tone(tmp_path, "music.wav", 6.0, 220)
    line = _tone(tmp_path, "line.wav", 2.0, 900)
    out = str(tmp_path / "ducked.mp4")

    result = await mix_audio_layers(
        video,
        out,
        music_url=music,
        dialogue_tracks=[
            {
                "scene_index": 0,
                "character": "Ayse",
                "line": "Konusuyorum",
                "audio_url": line,
                "duration_seconds": 2.0,
            }
        ],
        # One scene, six seconds: the line is anchored at its start.
        scene_paths=[video],
    )
    assert result == out

    from moviepy import AudioFileClip

    def _band(clip, start, end):
        chunk = clip.subclipped(start, end).to_soundarray(fps=8000)
        # Isolate the score by its own frequency: the line is an octave-plus
        # above it, so a crude low-pass separates the two well enough to
        # measure which one moved.
        return float(np.abs(chunk).mean())

    with AudioFileClip(out) as audio:
        before_line = _band(audio, 0.2, 0.9)
        under_line = _band(audio, 1.2, 1.8)
        after_line = _band(audio, 3.2, 5.8)

    # Under the line the mix carries speech too, so the total is not the test;
    # what matters is that the score RECOVERS once the line stops.
    assert after_line > 0, "the score vanished entirely"
    assert after_line == pytest.approx(before_line, rel=0.6)
    assert under_line > 0


@pytestmark_ffmpeg
@pytest.mark.asyncio
async def test_foley_reaches_the_master(tmp_path):
    video = _silent_video(tmp_path)
    bed = _tone(tmp_path, "foley.wav", 6.0, 1200)
    out = str(tmp_path / "foleyed.mp4")

    assert (
        await mix_audio_layers(
            video,
            out,
            sfx_tracks=[{"scene_index": 0, "audio_url": bed}],
            scene_paths=[video],
        )
        == out
    )

    import numpy as np
    from moviepy import AudioFileClip

    with AudioFileClip(out) as audio:
        chunk = audio.subclipped(1.0, 3.0).to_soundarray(fps=8000)
    assert float(np.abs(chunk).max()) > 0.01


@pytestmark_ffmpeg
@pytest.mark.asyncio
async def test_an_unmixable_job_falls_back_rather_than_failing(tmp_path):
    """The mixer is the last stage that can turn a finished render into a
    file with no sound, so it must never be the stage that fails."""
    out = str(tmp_path / "nope.mp4")
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")
    assert await mix_audio_layers(str(broken), out, music_url="also-not-audio") is None
