"""Watermark tests — Free plan only, real ffmpeg/moviepy rendering.

Uses tiny real ColorClip-generated videos (no mocks) so we actually exercise
the ffmpeg pipeline, not just branch logic.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_test_video(path: str, duration: float = 0.5) -> str:
    from moviepy import ColorClip

    clip = ColorClip(size=(64, 48), color=(20, 20, 20), duration=duration).with_fps(10)
    clip.write_videofile(path, codec="libx264", audio=False, logger=None)
    clip.close()
    return path


@pytest.mark.asyncio
async def test_watermark_applied_when_font_available(tmp_path):
    from pipelines.idea2video import _find_watermark_font, add_watermark

    if not _find_watermark_font():
        pytest.skip("No TTF font available on this machine to render watermark text")

    src = _make_test_video(str(tmp_path / "in.mp4"))
    out = str(tmp_path / "out.mp4")

    result = await add_watermark(src, out)

    assert result == out
    assert os.path.isfile(out)
    assert os.path.getsize(out) > 0


@pytest.mark.asyncio
async def test_watermark_fails_open_without_font(tmp_path, monkeypatch):
    """If no usable font is found, the original video is copied through untouched."""
    import pipelines.idea2video as idea2video

    monkeypatch.setattr(idea2video, "_WATERMARK_FONT_CANDIDATES", [])

    src = str(tmp_path / "in.mp4")
    with open(src, "wb") as f:
        f.write(b"fake-video-bytes")
    out = str(tmp_path / "out.mp4")

    result = await idea2video.add_watermark(src, out)

    assert result == out
    with open(out, "rb") as f:
        assert f.read() == b"fake-video-bytes"


def test_watermark_only_applies_to_free_plan():
    from pipelines.idea2video import WATERMARK_PLANS

    assert WATERMARK_PLANS == {"free"}
    assert "creator" not in WATERMARK_PLANS
    assert "pro" not in WATERMARK_PLANS


@pytest.mark.asyncio
async def test_assemble_final_drama_skips_watermark_for_paid_plans(tmp_path, monkeypatch):
    from pipelines.idea2video import Idea2VideoPipeline

    watermark_calls = []

    async def _fake_add_watermark(video_path, output_path):
        watermark_calls.append((video_path, output_path))
        return output_path

    async def _fake_add_music(video_path, output_path, music_url=None):
        with open(output_path, "wb") as f:
            f.write(b"concatenated")
        return output_path

    async def _fake_concat(scene_paths, output_path):
        with open(output_path, "wb") as f:
            f.write(b"concatenated")
        return output_path

    monkeypatch.setattr("pipelines.idea2video.add_watermark", _fake_add_watermark)
    monkeypatch.setattr("pipelines.idea2video.add_background_music", _fake_add_music)
    monkeypatch.setattr("pipelines.idea2video.concatenate_videos", _fake_concat)

    pipeline = Idea2VideoPipeline(api_key="", demo=False)
    working_dir = str(tmp_path / "job")

    for plan in ("creator", "pro"):
        watermark_calls.clear()
        await pipeline._assemble_final_drama(["scene0.mp4"], working_dir, plan=plan)
        assert watermark_calls == [], f"watermark should NOT run for plan={plan}"

    await pipeline._assemble_final_drama(["scene0.mp4"], working_dir, plan="free")
    assert len(watermark_calls) == 1, "watermark SHOULD run for plan=free"
