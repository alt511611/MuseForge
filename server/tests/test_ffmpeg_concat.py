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
