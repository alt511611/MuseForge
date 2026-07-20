"""Center-crop alternate-format export (naive, not subject-aware)."""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _ffprobe_size(path: str):
    """Return (width, height) via ffprobe, or None if unavailable."""
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                path,
            ],
            text=True,
        ).strip()
        w, h = out.split(",")
        return int(w), int(h)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        return None


@pytest.mark.asyncio
async def test_export_alternate_format_9_16_center_crop(tmp_path):
    """Build a tiny 16:9 clip, crop to 9:16, assert output aspect ≈ 9/16."""
    from moviepy import ColorClip

    from pipelines.idea2video import export_alternate_format

    src = str(tmp_path / "src_16x9.mp4")
    out = str(tmp_path / "out_9x16.mp4")

    clip = ColorClip(size=(640, 360), color=(20, 100, 200), duration=0.4)
    clip.write_videofile(src, fps=8, codec="libx264", audio=False, logger=None)
    clip.close()

    result = await export_alternate_format(src, out, "9:16")
    assert result == out
    assert os.path.isfile(out)

    size = _ffprobe_size(out)
    if size is None:
        # Fallback: read via moviepy when ffprobe isn't on PATH.
        from moviepy import VideoFileClip

        v = VideoFileClip(out)
        size = (int(v.w), int(v.h))
        v.close()

    w, h = size
    assert h > w, f"expected portrait, got {w}x{h}"
    ratio = w / h
    assert abs(ratio - 9 / 16) < 0.05, f"ratio {ratio} not near 9/16"


@pytest.mark.asyncio
async def test_export_alternate_format_1_1(tmp_path):
    from moviepy import ColorClip

    from pipelines.idea2video import export_alternate_format

    src = str(tmp_path / "src.mp4")
    out = str(tmp_path / "out_1x1.mp4")
    clip = ColorClip(size=(320, 180), color=(0, 200, 80), duration=0.3)
    clip.write_videofile(src, fps=8, codec="libx264", audio=False, logger=None)
    clip.close()

    await export_alternate_format(src, out, "1:1")
    from moviepy import VideoFileClip

    v = VideoFileClip(out)
    assert abs(v.w - v.h) <= 2
    v.close()


@pytest.mark.asyncio
async def test_export_rejects_bad_ratio(tmp_path):
    from pipelines.idea2video import export_alternate_format

    with pytest.raises(ValueError):
        await export_alternate_format(str(tmp_path / "x.mp4"), str(tmp_path / "y.mp4"), "not-a-ratio")
