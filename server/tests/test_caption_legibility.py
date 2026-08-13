"""Burned-in captions have to fit the frame they are burned into.

The style was one fixed string -- ``FontSize=22 ... MarginV=36`` -- for every
delivery format. Those numbers are not pixels: libass renders an ASS script at
its declared PlayRes (ffmpeg's SRT converter declares 384x288) and scales the
result to the frame, so the same FontSize is a different physical size in
every format, derived from the frame's HEIGHT.

Measured on one 69-character line, before:

    1920x1080  ->  2 lines,  14.1% of frame height
    1080x1920  ->  6 lines,  44.5% of frame height, 91.1% of its width

The vertical master -- the one delivered to the feeds that most need burned-in
captions -- had nearly half its picture under a wall of text, because the font
was sized as if the line had 1920px to run along when it had 1080. Nothing
errored; it simply shipped.

These tests measure the rendered pixels rather than asserting on the style
string, because the style string was never the thing that was wrong.
"""

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

LINE = "Mara Voss: Control, I've got a container out here that's... humming."


def _has_ffmpeg():
    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")


async def _render(tmp_path, width, height, line=LINE):
    """Burn one caption onto a black frame and measure the text it produced."""
    import numpy as np
    from moviepy import ColorClip, VideoFileClip

    from pipelines.idea2video import burn_subtitles

    source = str(tmp_path / f"src_{width}x{height}.mp4")
    clip = ColorClip(size=(width, height), color=(0, 0, 0), duration=2)
    clip.write_videofile(source, fps=8, codec="libx264", audio=False, logger=None)
    clip.close()

    output = str(tmp_path / f"sub_{width}x{height}.mp4")
    await burn_subtitles(
        source,
        output,
        [
            {
                "character": "Mara Voss",
                "line": line,
                "scene_index": 0,
                "start_seconds": 0.0,
                "end_seconds": 2.0,
            }
        ],
        scene_paths=[source],
    )

    with VideoFileClip(output) as rendered:
        frame = rendered.get_frame(1.0)

    # White text on black: anything bright is caption.
    bright = frame.max(axis=2) > 120
    rows = np.where(bright.any(axis=1))[0]
    cols = np.where(bright.any(axis=0))[0]
    assert len(rows), "no caption was rendered at all"
    lines = 1 + int((np.diff(rows) > 5).sum())
    return {
        "lines": lines,
        "block_fraction": (rows[-1] - rows[0] + 1) / height,
        "width_fraction": (cols[-1] - cols[0] + 1) / width,
        "bottom_fraction": (height - 1 - rows[-1]) / height,
    }


@pytest.mark.asyncio
async def test_a_vertical_master_is_not_half_covered_in_text(tmp_path):
    """The failure that prompted this: 6 lines over 44.5% of the frame."""
    measured = await _render(tmp_path, 1080, 1920)

    assert measured["lines"] <= 3
    assert measured["block_fraction"] < 0.15, measured
    assert measured["width_fraction"] < 0.88, measured


@pytest.mark.asyncio
async def test_the_landscape_master_stays_readable_too(tmp_path):
    measured = await _render(tmp_path, 1920, 1080)

    assert measured["lines"] <= 3
    assert measured["block_fraction"] < 0.15, measured
    assert measured["width_fraction"] < 0.88, measured


@pytest.mark.asyncio
async def test_captions_clear_the_player_control_bar(tmp_path):
    """A video player's controls cover roughly the bottom tenth. The second
    line of every caption was rendered underneath them in the results-page
    preview."""
    measured = await _render(tmp_path, 1920, 1080)

    assert measured["bottom_fraction"] > 0.09, measured


@pytest.mark.asyncio
async def test_the_same_line_reads_the_same_in_both_formats(tmp_path):
    """The point of sizing from width: a caption should not be a different
    proportion of the picture depending on which button the user pressed."""
    landscape = await _render(tmp_path, 1920, 1080)
    vertical = await _render(tmp_path, 1080, 1920)

    assert abs(landscape["width_fraction"] - vertical["width_fraction"]) < 0.30, (
        landscape,
        vertical,
    )


def test_the_two_formats_get_the_same_physical_font():
    """A FontSize is not a pixel count -- libass multiplies it by
    height/PlayResY. The two formats therefore need DIFFERENT FontSize values
    to reach the same size on screen, and one fixed value (the old bug) can
    only be right for one of them."""
    from pipelines.idea2video import _ASS_PLAY_RES_Y, build_caption_style

    def _rendered_px(width, height):
        style = build_caption_style(width, height)
        font_size = int(style.split("FontSize=")[1].split(",")[0])
        return font_size * height / _ASS_PLAY_RES_Y

    landscape = _rendered_px(1920, 1080)
    vertical = _rendered_px(1080, 1920)

    # Same short side (1080), so the caption should be about the same size.
    assert abs(landscape - vertical) / landscape < 0.25, (landscape, vertical)
    # And that is only possible because the FontSize values differ.
    assert build_caption_style(1920, 1080) != build_caption_style(1080, 1920)


def test_an_unmeasurable_frame_still_gets_captions():
    """A probe failure must not leave the video with no captions at all."""
    from pipelines.idea2video import build_caption_style

    style = build_caption_style(0, 0)

    assert "FontSize=22" in style
    assert "Alignment=2" in style


def test_the_style_always_carries_the_readability_settings():
    from pipelines.idea2video import build_caption_style

    for size in [(1920, 1080), (1080, 1920), (0, 0)]:
        style = build_caption_style(*size)
        assert "BorderStyle=3" in style, size  # opaque box behind the text
        assert "PrimaryColour=&H00FFFFFF" in style, size
        assert "MarginL=" in style and "MarginR=" in style, size
