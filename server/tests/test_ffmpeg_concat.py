"""Low-memory ffmpeg concat and moviepy-chain fallback tests."""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_clips(tmp_path, count=3, duration=0.4):
    """Create codec/size-matched real MP4 clips."""
    from moviepy import ColorClip

    paths = []
    for idx in range(count):
        path = str(tmp_path / f"clip_{idx}.mp4")
        clip = ColorClip(
            size=(160, 90),
            color=((idx + 1) * 40, 80, 140),
            duration=duration,
        )
        clip.write_videofile(
            path,
            fps=10,
            codec="libx264",
            audio=False,
            logger=None,
        )
        clip.close()
        paths.append(path)
    return paths


def _duration_seconds(path):
    """Probe duration with ffprobe; moviepy fallback supports local dev."""
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        output = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            text=True,
        )
        return float(output.strip())

    # The production Docker image and CI have ffprobe (ffmpeg apt package).
    # Some local moviepy installs only provide an imageio ffmpeg binary.
    from moviepy import VideoFileClip

    clip = VideoFileClip(path)
    try:
        return float(clip.duration)
    finally:
        clip.close()


@pytest.mark.asyncio
async def test_concat_demuxer_stream_copy_has_total_duration(tmp_path, monkeypatch):
    """Three matching MP4s should use native concat and preserve duration."""
    import moviepy

    from pipelines.script2video import concatenate_videos

    paths = _make_clips(tmp_path)
    output = str(tmp_path / "concat_fast.mp4")

    # Fast-path success must not touch moviepy's concatenate fallback.
    def _fallback_must_not_run(*_args, **_kwargs):
        raise AssertionError("moviepy fallback ran despite compatible clips")

    monkeypatch.setattr(moviepy, "concatenate_videoclips", _fallback_must_not_run)

    result = await concatenate_videos(paths, output)

    assert result == output
    assert os.path.isfile(output)
    assert abs(_duration_seconds(output) - 1.2) < 0.25


@pytest.mark.asyncio
async def test_failed_ffmpeg_concat_uses_moviepy_chain(tmp_path, monkeypatch):
    """A failed concat process must fall back to a valid moviepy chain output."""
    import moviepy
    import pipelines.script2video as script2video

    paths = _make_clips(tmp_path)
    output = str(tmp_path / "concat_chain.mp4")

    class FailedProcess:
        returncode = 1

        async def communicate(self):
            return b"", b"synthetic concat-demuxer failure"

    async def _failed_create_subprocess(*_args, **_kwargs):
        return FailedProcess()

    real_concatenate = moviepy.concatenate_videoclips
    methods = []

    def _recording_concatenate(clips, method="chain"):
        methods.append(method)
        return real_concatenate(clips, method=method)

    monkeypatch.setattr(
        script2video.asyncio,
        "create_subprocess_exec",
        _failed_create_subprocess,
    )
    monkeypatch.setattr(moviepy, "concatenate_videoclips", _recording_concatenate)

    result = await script2video.concatenate_videos(paths, output)

    assert result == output
    assert methods == ["chain"]
    assert os.path.isfile(output)
    assert abs(_duration_seconds(output) - 1.2) < 0.25


def _ffmpeg_for_tests():
    from pipelines.script2video import _ffmpeg_binary

    return _ffmpeg_binary()


def _make_clip_with_timescale(tmp_path, name, timescale, duration=0.5):
    """A clip written with an explicit container timescale.

    The pipeline produces these without asking for them: a clip that came back
    from a provider and a clip `trim_clip` re-encoded locally do not agree
    about their timebase, and the concat demuxer writes the join against the
    first one's.
    """
    path = str(tmp_path / name)
    subprocess.run(
        [
            _ffmpeg_for_tests(), "-y", "-v", "error",
            "-f", "lavfi",
            "-i", f"testsrc=size=160x90:rate=24:duration={duration}",
            "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-video_track_timescale", str(timescale),
            "-an", path,
        ],
        check=True,
    )
    return path


@pytest.mark.asyncio
async def test_disagreeing_timebases_are_repaired_by_a_packet_copy(
    tmp_path, monkeypatch
):
    """Clips with different timebases must be joined by a copy, not a re-encode.

    The concat demuxer copies packets without re-timing them and writes them
    against the FIRST input's timebase, so mismatched inputs come out at a
    length that does not describe them -- these two join as 137s of "1s", and
    the delivered job that prompted this got 5.46s out of 10.04s. Both of the
    tiers under the fast path decode every frame, which on a lip-sync rejoin
    spends a generation of quality on footage that was never damaged. A
    stream-copy remux to a shared timescale repairs the join without decoding,
    so neither re-encode tier may run.
    """
    import moviepy

    import pipelines.script2video as script2video

    head = _make_clip_with_timescale(tmp_path, "head.mp4", 600)
    tail = _make_clip_with_timescale(tmp_path, "tail.mp4", 90000)
    output = str(tmp_path / "rejoined.mp4")

    # Counted rather than raised: tier 2 swallows exceptions and falls to
    # tier 3, so a raising guard would be silently absorbed and pass.
    reencodes = {"moviepy": 0, "filter": 0}

    real_filter = script2video._concat_by_filter
    real_moviepy = moviepy.concatenate_videoclips

    async def _counting_filter(*args, **kwargs):
        reencodes["filter"] += 1
        return await real_filter(*args, **kwargs)

    def _counting_moviepy(*args, **kwargs):
        reencodes["moviepy"] += 1
        return real_moviepy(*args, **kwargs)

    monkeypatch.setattr(script2video, "_concat_by_filter", _counting_filter)
    monkeypatch.setattr(moviepy, "concatenate_videoclips", _counting_moviepy)

    result = await script2video.concatenate_videos([head, tail], output)

    assert result == output
    assert os.path.isfile(output)
    # Both halves are present and the timeline describes them.
    assert abs(_duration_seconds(output) - 1.0) < 0.05
    # Nothing decoded a frame to get there.
    assert reencodes == {"moviepy": 0, "filter": 0}
    # The normalisation temporaries are cleaned up behind it.
    leftovers = [n for n in os.listdir(str(tmp_path)) if n.startswith("museforge_tb_")]
    assert leftovers == []
