"""Delivery geometry: a job ordered in 9:16 must SHIP in 9:16.

The ratio is honoured at generation time (frames are rendered vertically and
image-to-video inherits the frame's shape); this covers the guarantee pass
that conforms the master inside the colour-grade encode when a provider hands
back a differently-shaped clip.
"""

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _has_ffmpeg():
    """The pipeline falls back to moviepy's bundled binary when ffmpeg is not
    on PATH (local dev), so the encode tests must too."""
    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


def _make_clip(tmp_path, size=(160, 90), duration=0.5, name="clip.mp4"):
    from moviepy import ColorClip

    path = str(tmp_path / name)
    clip = ColorClip(size=size, color=(90, 40, 120), duration=duration)
    clip.write_videofile(path, fps=10, codec="libx264", audio=False, logger=None)
    clip.close()
    return path


def _dimensions(path):
    from moviepy import VideoFileClip

    with VideoFileClip(path) as clip:
        width, height = clip.size
        return int(width), int(height)


def test_vertical_source_is_left_alone():
    """The normal case: frames were generated 9:16, so nothing to conform."""
    from pipelines.script2video import build_geometry_filters

    assert build_geometry_filters(1080, 1920, "9:16") == []


def test_landscape_source_is_conformed_to_vertical():
    from pipelines.script2video import build_geometry_filters, resolve_output_dimensions

    assert resolve_output_dimensions(1920, 1080, "9:16") == (606, 1080)
    filters = build_geometry_filters(1920, 1080, "9:16")
    assert filters[0].startswith("scale=606:1080:force_original_aspect_ratio=increase")
    assert "crop=606:1080" in filters
    # Cropping to fill, never padding: black bars in a vertical feed read as
    # a broken upload.
    assert not any("pad=" in f for f in filters)


def test_resolution_is_capped_but_never_upscaled():
    from pipelines.script2video import resolve_output_dimensions

    # Bigger than the delivery ceiling -> capped at the canonical size.
    assert resolve_output_dimensions(2160, 3840, "9:16") == (1080, 1920)
    # Smaller -> kept at the ratio, not inflated to a resolution the pixels
    # do not actually have.
    width, height = resolve_output_dimensions(768, 1344, "9:16")
    assert (width, height) == (756, 1344)
    assert abs(width / height - 9 / 16) < 0.01


def test_exact_resolution_flag_forces_canonical_size(monkeypatch):
    from pipelines.script2video import resolve_output_dimensions

    monkeypatch.setenv("MUSEFORGE_EXACT_RESOLUTION", "1")
    assert resolve_output_dimensions(768, 1344, "9:16") == (1080, 1920)


def test_unknown_ratio_leaves_the_video_untouched():
    from pipelines.script2video import build_geometry_filters, resolve_output_dimensions

    assert resolve_output_dimensions(1920, 1080, "4:3") is None
    assert build_geometry_filters(1920, 1080, "") == []


def test_square_target():
    from pipelines.script2video import resolve_output_dimensions

    assert resolve_output_dimensions(1920, 1080, "1:1") == (1080, 1080)


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
@pytest.mark.asyncio
async def test_color_grade_ships_the_ordered_ratio(tmp_path):
    """End to end through the real ffmpeg encode: a landscape master graded
    for a 9:16 job comes out vertical, in one pass."""
    from pipelines.script2video import apply_color_grade

    source = _make_clip(tmp_path, size=(320, 180))
    output = str(tmp_path / "graded.mp4")

    result = await apply_color_grade(source, output, aspect_ratio="9:16")

    width, height = _dimensions(result)
    assert height > width
    assert abs(width / height - 9 / 16) < 0.02


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
@pytest.mark.asyncio
async def test_color_grade_without_ratio_keeps_dimensions(tmp_path):
    """Callers that pass no ratio (and every existing test) are unaffected."""
    from pipelines.script2video import apply_color_grade

    source = _make_clip(tmp_path, size=(160, 90))
    output = str(tmp_path / "graded_plain.mp4")

    await apply_color_grade(source, output)

    assert _dimensions(output) == (160, 90)


def test_generate_request_rejects_an_unsupported_ratio():
    import pydantic

    from api import GenerateRequest

    assert GenerateRequest(idea="a vertical brand film").aspect_ratio == "16:9"
    assert GenerateRequest(idea="idea", aspect_ratio="9:16").aspect_ratio == "9:16"
    with pytest.raises(pydantic.ValidationError):
        GenerateRequest(idea="idea", aspect_ratio="vertical")
