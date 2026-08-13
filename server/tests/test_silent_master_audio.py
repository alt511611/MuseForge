"""A master with nothing to mix still has to be a normal video file.

Music off and a voice provider that failed leaves nothing to lay over the
picture, and the result was an mp4 with NO audio stream at all -- which
editors, some phone players and several upload pipelines read as malformed.

The first attempt at fixing that is the reason this file exists. Silence was
synthesised as a moviepy AudioClip and written with the video, and the
container came out ~2000x too long: a 3-second clip muxed to 5923 seconds, a
three-scene drama to 13 hours. Nothing raised and nothing was logged -- every
LATER stage simply started decoding a million frames, and a job that should
have taken a minute ran until it was killed. So the DURATION is asserted
here, not just the presence of a stream.
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _has_ffmpeg():
    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")


def _make_clip(tmp_path, duration=3.0, name="src.mp4"):
    from moviepy import ColorClip

    path = str(tmp_path / name)
    clip = ColorClip(size=(160, 90), color=(10, 20, 30), duration=duration)
    clip.write_videofile(path, fps=12, codec="libx264", audio=False, logger=None)
    clip.close()
    return path


def _probe(path):
    """(duration_seconds, stream kinds) from ffmpeg itself.

    Deliberately not moviepy: the bug was in what moviepy WROTE, and the
    container is what every later stage and every player reads.
    """
    from pipelines.idea2video import resolve_ffmpeg_binary

    out = subprocess.run(
        [resolve_ffmpeg_binary(), "-hide_banner", "-i", path],
        capture_output=True,
        text=True,
    ).stderr
    duration = 0.0
    kinds = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            clock = line.split("Duration:")[1].split(",")[0].strip()
            hours, minutes, seconds = clock.split(":")
            duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        elif "Stream #" in line:
            if "Audio:" in line:
                kinds.append("audio")
            elif "Video:" in line:
                kinds.append("video")
    return duration, kinds


@pytest.mark.asyncio
async def test_a_master_with_nothing_to_mix_gets_a_silent_track(tmp_path):
    from pipelines.idea2video import add_background_music

    source = _make_clip(tmp_path, duration=3.0)
    output = str(tmp_path / "mixed.mp4")

    await add_background_music(source, output, None)

    duration, kinds = _probe(output)
    assert "audio" in kinds, "a missing audio stream reads as a malformed file"
    assert "video" in kinds


@pytest.mark.asyncio
async def test_the_silent_track_does_not_stretch_the_file(tmp_path):
    """The whole bug: a 3-second clip came out 5923 seconds long, and every
    stage after it tried to decode the difference."""
    from pipelines.idea2video import add_background_music

    source = _make_clip(tmp_path, duration=3.0)
    output = str(tmp_path / "mixed.mp4")

    await add_background_music(source, output, None)

    source_duration, _ = _probe(source)
    duration, _ = _probe(output)
    assert abs(duration - source_duration) < 0.5, (
        f"{duration}s out of a {source_duration}s master"
    )


@pytest.mark.asyncio
async def test_caption_only_dialogue_still_counts_as_nothing_to_mix(tmp_path):
    """The path this actually shipped on: the voice provider failed, so the
    tracks carry text and no audio."""
    from pipelines.idea2video import add_background_music, caption_only_tracks

    source = _make_clip(tmp_path, duration=3.0)
    output = str(tmp_path / "mixed.mp4")
    tracks = caption_only_tracks([{"character": "Mara", "line": "It's warm."}], 0)

    await add_background_music(source, output, None, dialogue_tracks=tracks)

    duration, kinds = _probe(output)
    assert "audio" in kinds
    assert abs(duration - 3.0) < 0.5


@pytest.mark.asyncio
async def test_the_picture_is_not_re_encoded_to_add_silence(tmp_path):
    """There is no mix to perform, so the master must not pay a generation
    loss for it. ``-c:v copy`` keeps the video bitstream byte-for-byte."""
    from pipelines.idea2video import mux_silent_audio

    source = _make_clip(tmp_path, duration=2.0)
    output = str(tmp_path / "muxed.mp4")

    assert await mux_silent_audio(source, output) is True

    from pipelines.idea2video import resolve_ffmpeg_binary

    def _video_md5(path):
        return subprocess.run(
            [
                resolve_ffmpeg_binary(), "-hide_banner", "-loglevel", "error",
                "-i", path, "-map", "0:v", "-c", "copy", "-f", "md5", "-",
            ],
            capture_output=True,
            text=True,
        ).stdout.strip()

    assert _video_md5(source) == _video_md5(output)


@pytest.mark.asyncio
async def test_a_video_that_cannot_be_muxed_still_ships(tmp_path):
    """Fail-open, same as every other finishing stage: a master with no audio
    beats no master."""
    from pipelines.idea2video import add_background_music

    source = _make_clip(tmp_path, duration=2.0)
    output = str(tmp_path / "mixed.mp4")

    import pipelines.idea2video as pipeline_mod

    async def _fail(video_path, output_path):
        return False

    original = pipeline_mod.mux_silent_audio
    pipeline_mod.mux_silent_audio = _fail
    try:
        await add_background_music(source, output, None)
    finally:
        pipeline_mod.mux_silent_audio = original

    assert os.path.getsize(output) == os.path.getsize(source)


@pytest.mark.asyncio
async def test_real_audio_is_mixed_as_it_always_was(tmp_path):
    """The silent path must not have moved the case that has something to
    play: music still reaches the master, at the master's own length."""
    from moviepy import AudioClip

    from pipelines.idea2video import add_background_music

    music = str(tmp_path / "music.mp3")
    tone = AudioClip(
        lambda t: [0.2 * ((t * 220) % 1.0 - 0.5)], duration=5.0, fps=44100
    )
    tone.write_audiofile(music, logger=None)
    tone.close()

    source = _make_clip(tmp_path, duration=3.0)
    output = str(tmp_path / "mixed.mp4")

    await add_background_music(source, output, music)

    duration, kinds = _probe(output)
    assert "audio" in kinds
    # Clipped to the picture, not stretched to the music.
    assert abs(duration - 3.0) < 0.5
