"""Output encode quality.

A finished drama is re-encoded several times on its way out (colour grade,
audio mix, caption burn, watermark, aspect export). Every pass used bare
`libx264` with no rate control, so each ran at ffmpeg's default CRF 23 over an
already-degraded picture and the loss compounded. These tests pin the shared
encode settings and the two correctness constraints that come with them:
4:2:0 needs even dimensions, and web playback needs a front-loaded moov atom.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipelines.idea2video import _even  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    VIDEO_PIX_FMT,
    moviepy_encode_kwargs,
    video_encode_args,
)


def _ffmpeg():
    import shutil

    return os.environ.get("MUSEFORGE_FFMPEG_BINARY") or shutil.which("ffmpeg") or (
        __import__("imageio_ffmpeg").get_ffmpeg_exe()
    )


def _probe(path, entries):
    import shutil

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        pytest.skip("ffprobe not available")
    out = subprocess.check_output(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         entries, "-of", "default=noprint_wrappers=1:nokey=1", path],
        text=True,
    )
    return out.strip().splitlines()


# --- the shared settings -----------------------------------------------


def test_encode_args_set_rate_control_not_just_a_codec():
    args = video_encode_args()
    assert "-crf" in args, "bare libx264 means ffmpeg's default CRF 23"
    crf = int(args[args.index("-crf") + 1])
    assert crf < 23, "the whole point is to beat the default across re-encodes"
    assert args[args.index("-pix_fmt") + 1] == "yuv420p"
    assert "+faststart" in args


def test_encode_args_are_env_tunable(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_CRF", "20")
    monkeypatch.setenv("MUSEFORGE_VIDEO_PRESET", "slow")
    args = video_encode_args()
    assert args[args.index("-crf") + 1] == "20"
    assert args[args.index("-preset") + 1] == "slow"


def test_moviepy_kwargs_do_not_duplicate_preset():
    """moviepy takes `preset` as its own argument; passing it in ffmpeg_params
    as well makes ffmpeg fail with a duplicated option."""
    kwargs = moviepy_encode_kwargs()
    assert kwargs["preset"]
    assert "-preset" not in kwargs["ffmpeg_params"]
    # Codec is moviepy's `codec=` argument, not ours to repeat either.
    assert "-c:v" not in kwargs["ffmpeg_params"]
    # But the settings that matter must survive.
    assert "-crf" in kwargs["ffmpeg_params"]
    assert "-pix_fmt" in kwargs["ffmpeg_params"]


# --- even dimensions ---------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [(202.5, 202), (203, 202), (360, 360), (1.4, 2), (0, 2), (-5, 2)],
)
def test_even_rounds_down_and_never_reaches_zero(value, expected):
    assert _even(value) == expected


def test_even_never_exceeds_the_source_dimension():
    """Rounding UP could crop outside the frame."""
    for value in (100.9, 201.99, 3.5):
        assert _even(value) <= value or value < 2


@pytest.mark.asyncio
async def test_odd_crop_dimensions_still_encode(tmp_path):
    """Regression: 4:2:0 cannot encode an odd width/height, so a 640x360
    source cropped to 9:16 (202.5px wide) failed outright once pix_fmt was
    pinned. The crop must normalise to an even size."""
    from moviepy import ColorClip, VideoFileClip

    from pipelines.idea2video import export_alternate_format

    src = str(tmp_path / "src.mp4")
    clip = ColorClip(size=(640, 360), color=(120, 90, 60), duration=0.6)
    clip.write_videofile(src, fps=10, codec="libx264", audio=False, logger=None)
    clip.close()

    out = str(tmp_path / "out.mp4")
    await export_alternate_format(src, out, "9:16")

    with VideoFileClip(out) as got:
        assert got.w % 2 == 0 and got.h % 2 == 0, (got.w, got.h)
        assert abs((got.w / got.h) - (9 / 16)) < 0.02


# --- the settings actually reach the file ------------------------------


async def _grade_a_clip(tmp_path):
    from moviepy import ColorClip

    from pipelines.script2video import apply_color_grade

    src = str(tmp_path / "src.mp4")
    clip = ColorClip(size=(160, 90), color=(200, 150, 120), duration=0.6)
    clip.write_videofile(src, fps=10, codec="libx264", audio=False, logger=None)
    clip.close()

    out = str(tmp_path / "graded.mp4")
    await apply_color_grade(src, out)
    return out


@pytest.mark.asyncio
async def test_graded_output_is_faststart(tmp_path):
    """moov before mdat, so the browser player can start before the whole
    file has downloaded. Deliberately free of any ffprobe dependency."""
    out = await _grade_a_clip(tmp_path)
    with open(out, "rb") as f:
        head = f.read(8192)
    assert b"moov" in head and b"mdat" in head, "expected both atoms near the start"
    assert head.index(b"moov") < head.index(b"mdat"), (
        "moov atom not front-loaded; browser playback will wait for the "
        "whole file"
    )


@pytest.mark.asyncio
async def test_graded_output_is_yuv420p(tmp_path):
    out = await _grade_a_clip(tmp_path)
    [pix_fmt] = _probe(out, "stream=pix_fmt")
    assert pix_fmt == VIDEO_PIX_FMT


@pytest.mark.asyncio
async def test_regrade_keeps_more_detail_than_default_crf(tmp_path):
    """The concrete payoff: at the pipeline's CRF a re-encode preserves the
    picture far better than ffmpeg's default would."""
    import shutil

    from moviepy import ColorClip

    from pipelines.script2video import apply_color_grade

    src = str(tmp_path / "src.mp4")
    # Detailed noise-like content so quantisation loss is measurable.
    import numpy as np
    from moviepy import ImageSequenceClip

    rng = np.random.default_rng(7)
    frames = [rng.integers(0, 255, (180, 320, 3), dtype=np.uint8) for _ in range(6)]
    ImageSequenceClip(frames, fps=10).write_videofile(
        src, codec="libx264", audio=False, logger=None,
        ffmpeg_params=["-crf", "14"],
    )

    ours = str(tmp_path / "ours.mp4")
    await apply_color_grade(src, ours)

    # Same operation at ffmpeg's bare default, for comparison.
    baseline = str(tmp_path / "baseline.mp4")
    ffmpeg = _ffmpeg()
    subprocess.run(
        [ffmpeg, "-y", "-i", src, "-vf", "eq=contrast=1.04", "-c:v", "libx264",
         baseline], capture_output=True, check=True,
    )

    assert os.path.getsize(ours) > os.path.getsize(baseline), (
        "our encode should retain more data than the bare-default one; "
        f"ours={os.path.getsize(ours)} baseline={os.path.getsize(baseline)}"
    )
    assert shutil.which  # keep import meaningful


# --- frame resolution --------------------------------------------------


def test_video_frames_render_above_one_megapixel():
    """Frames are the conditioning image for Kling, which renders at a higher
    output resolution -- anything below that gets upscaled and the softness is
    baked into every frame of the shot."""
    from tools.muapi_image_generator import ASPECT_RATIO_MAP

    for ratio in ("16:9", "9:16", "4:3"):
        dims = ASPECT_RATIO_MAP[ratio]
        megapixels = dims["width"] * dims["height"] / 1_000_000
        assert megapixels > 1.2, f"{ratio} is only {megapixels:.2f}MP"
        # Even dimensions keep the frames encodable downstream too.
        assert dims["width"] % 2 == 0 and dims["height"] % 2 == 0


def test_portrait_ratio_stays_cheap():
    """1:1 is only ever the character reference portrait, never shown."""
    from tools.muapi_image_generator import ASPECT_RATIO_MAP

    assert ASPECT_RATIO_MAP["1:1"] == {"width": 1024, "height": 1024}


def test_resolution_override_applies_and_fails_safe(monkeypatch):
    from tools.muapi_image_generator import ASPECT_RATIO_MAP, resolve_dimensions

    default = ASPECT_RATIO_MAP["16:9"]
    monkeypatch.delenv("MUSEFORGE_IMAGE_WIDTH", raising=False)
    monkeypatch.delenv("MUSEFORGE_IMAGE_HEIGHT", raising=False)
    assert resolve_dimensions("16:9") == default

    monkeypatch.setenv("MUSEFORGE_IMAGE_WIDTH", "1920")
    monkeypatch.setenv("MUSEFORGE_IMAGE_HEIGHT", "1080")
    assert resolve_dimensions("16:9") == {"width": 1920, "height": 1080}

    # Half-configured must not produce a broken payload.
    monkeypatch.delenv("MUSEFORGE_IMAGE_HEIGHT")
    assert resolve_dimensions("16:9") == default

    monkeypatch.setenv("MUSEFORGE_IMAGE_HEIGHT", "not-a-number")
    assert resolve_dimensions("16:9") == default

    monkeypatch.setenv("MUSEFORGE_IMAGE_HEIGHT", "-4")
    assert resolve_dimensions("16:9") == default


def test_resolution_override_reaches_the_payload(monkeypatch):
    from tools.muapi_image_generator import MuAPIImageGenerator

    monkeypatch.setenv("MUSEFORGE_IMAGE_WIDTH", "1920")
    monkeypatch.setenv("MUSEFORGE_IMAGE_HEIGHT", "1080")
    gen = MuAPIImageGenerator(api_key="k", demo=False)
    assert gen._text_to_image_payload("x", "16:9")["size"] == "1920*1080"


# --- prompt-side image quality -----------------------------------------


def test_frame_prompt_carries_craft_direction():
    """FLUX has no true CFG, so quality is steered positively rather than
    with a negative_prompt the endpoint would ignore or 422 on."""
    from types import SimpleNamespace

    from pipelines.script2video import build_frame_prompt

    shot = SimpleNamespace(
        visual_desc="two women at a table", shot_type="close-up", lens="85mm"
    )
    prompt = build_frame_prompt("Cinematic", shot)
    assert "anatomically correct hands" in prompt
    assert "catchlights in the eyes" in prompt
    # Spurious captions/watermarks are a common FLUX failure on cinematic prompts.
    assert "No text, captions, subtitles, watermarks" in prompt


def test_no_negative_prompt_field_is_sent_to_flux():
    """A negative_prompt on a distilled FLUX endpoint risks a 422 that would
    silently demote every frame to the fallback model."""
    from tools.muapi_image_generator import MuAPIImageGenerator

    gen = MuAPIImageGenerator(api_key="k", demo=False)
    assert "negative_prompt" not in gen._text_to_image_payload("x", "16:9")
