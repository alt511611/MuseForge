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

    assert resolve_output_dimensions(1920, 1080, "9:16") == (608, 1080)
    filters = build_geometry_filters(1920, 1080, "9:16")
    assert filters[0].startswith("scale=608:1080:force_original_aspect_ratio=increase")
    assert "crop=608:1080" in filters
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


# --- the size a provider actually hands back -----------------------------


def test_a_provider_house_size_still_ships_as_1080p():
    """Delivered, verbatim: a 16:9 order came back 1904x1072 (the provider
    works in multiples of 16) and the master shipped 1904x1070 -- not a
    standard resolution, and not exactly 16:9 either, to avoid a 0.8%
    upscale."""
    from pipelines.script2video import resolve_output_dimensions

    assert resolve_output_dimensions(1904, 1072, "16:9") == (1920, 1080)


def test_a_genuinely_smaller_render_is_still_never_inflated():
    """The no-upscaling rule is the point; the snap is only its last 5%."""
    from pipelines.script2video import resolve_output_dimensions

    assert resolve_output_dimensions(1280, 720, "16:9") == (1280, 720)
    assert resolve_output_dimensions(768, 1344, "9:16") == (756, 1344)


def test_a_landscape_master_never_snaps_to_a_vertical_it_does_not_have():
    """Both axes have to be close, or a 1920-wide clip would 'snap' to
    1080x1920 on the strength of its width alone and be blown up 78%."""
    from pipelines.script2video import resolve_output_dimensions

    width, height = resolve_output_dimensions(1920, 1080, "9:16")
    assert height == 1080


def test_the_derived_side_rounds_to_the_nearest_even_not_down():
    """9:16 out of a 1080-tall master wants 607.5px. Flooring it to 606 costs
    three times the ratio error of rounding to 608, every time, in the same
    direction."""
    from pipelines.script2video import resolve_output_dimensions

    width, height = resolve_output_dimensions(1920, 1080, "9:16")

    assert (width, height) == (608, 1080)
    assert abs(width / height - 9 / 16) / (9 / 16) < 0.001


@pytest.mark.parametrize("source", [(1920, 1080), (1904, 1072), (1280, 720), (960, 540)])
@pytest.mark.parametrize("ratio", ["16:9", "9:16", "1:1"])
def test_every_delivery_is_even_and_within_a_tenth_of_a_percent(source, ratio):
    from pipelines.script2video import TARGET_RESOLUTIONS, resolve_output_dimensions

    width, height = resolve_output_dimensions(source[0], source[1], ratio)
    target_w, target_h = TARGET_RESOLUTIONS[ratio]

    assert width % 2 == 0 and height % 2 == 0, "yuv420p refuses odd dimensions"
    wanted = target_w / target_h
    assert abs(width / height - wanted) / wanted < 0.0025
