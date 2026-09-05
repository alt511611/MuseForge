"""The frame that sells a slap: flash, shake, aberration — on the cut.

Generated video renders contact smoothly, because smooth is what the model was
rewarded for, so every physical beat a micro-drama is built on lands soft.
Editors have always fixed this in the cut rather than in the footage, which is
why it costs nothing here.

The rule that keeps it from becoming a gimmick: an impact needs a CUT to sit
on. Before a scene could hold two angles there was no cut inside one, and a
hit placed mid-take punctuates nothing — so this plans nothing when there is
no join, rather than inventing a position for the effect.
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.impact import (  # noqa: E402
    ABERRATION_FRAMES,
    FLASH_FRAMES,
    IMPACT_TENSION,
    SHAKE_SECONDS,
    build_impact_filters,
    plan_impacts,
)


@pytest.fixture(autouse=True)
def _auto_mode(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_IMPACT", raising=False)


# --- when it fires -----------------------------------------------------


def test_no_cut_means_no_impact():
    """A hit in the middle of a continuous take punctuates nothing."""
    assert plan_impacts(None, tension=10, duration=10.0) == []


def test_only_the_hardest_beat_gets_hit():
    assert plan_impacts(8.0, tension=IMPACT_TENSION - 1, duration=10.0) == []
    assert plan_impacts(8.0, tension=IMPACT_TENSION, duration=10.0)


def test_an_operator_can_force_it_either_way(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_IMPACT", "on")
    assert plan_impacts(4.0, tension=1, duration=10.0)
    monkeypatch.setenv("MUSEFORGE_IMPACT", "off")
    assert plan_impacts(4.0, tension=10, duration=10.0) == []


def test_a_shake_that_would_not_fit_is_not_started():
    """Cut off by the end of the scene, a decaying shake looks like a broken
    encode rather than a blow."""
    assert plan_impacts(9.95, tension=10, duration=10.0) == []
    assert plan_impacts(10.0 - SHAKE_SECONDS - 0.1, tension=10, duration=10.0)


# --- the filters -------------------------------------------------------


def _window(expression: str) -> tuple:
    """The (start, end) of the single ``between(t,a,b)`` in a filter."""
    inner = expression.split("between(t,", 1)[1].split(")", 1)[0]
    start, end = inner.split(",")
    return float(start), float(end)


def _frames_inside(window: tuple, fps: float = 24.0) -> int:
    """How many real frame timestamps an INCLUSIVE ffmpeg window covers."""
    start, end = window
    step = 1.0 / fps
    return sum(
        1
        for n in range(int(round(end * fps)) + 2)
        if start <= round(n * step, 9) <= end
    )


def test_the_flash_is_one_frame_long():
    """Named for the intent since the module was written; it was two.

    `between` is inclusive at both ends and the window used to end exactly on
    the NEXT frame's timestamp, so the delivered drama took 83ms of white --
    the precise duration FLASH_FRAMES=1 exists to avoid.
    """
    beats = plan_impacts(4.0, tension=10, duration=10.0)
    filters = build_impact_filters(beats, 1080, 1920, fps=24.0)
    flash = [f for f in filters if f.startswith("eq=")][0]
    assert _frames_inside(_window(flash)) == FLASH_FRAMES == 1


def test_the_aberration_is_two_frames_long():
    beats = plan_impacts(4.0, tension=10, duration=10.0)
    filters = build_impact_filters(beats, 1080, 1920, fps=24.0)
    shift = [f for f in filters if f.startswith("rgbashift=")][0]
    assert _frames_inside(_window(shift)) == ABERRATION_FRAMES == 2


@pytest.mark.parametrize("fps", [24.0, 25.0, 30.0])
def test_the_flash_is_one_frame_at_any_frame_rate(fps):
    filters = build_impact_filters(
        plan_impacts(4.0, tension=10, duration=10.0), 1080, 1920, fps=fps
    )
    flash = [f for f in filters if f.startswith("eq=")][0]
    assert _frames_inside(_window(flash), fps) == 1


def test_a_cut_between_two_frames_still_lights_exactly_one():
    """A coverage share is whole seconds today, but nothing guarantees the
    join lands on a frame boundary -- and a window that falls between two of
    them lights whichever the rounding favours, or neither."""
    filters = build_impact_filters(
        plan_impacts(4.017, tension=10, duration=10.0), 1080, 1920, fps=24.0
    )
    flash = [f for f in filters if f.startswith("eq=")][0]
    assert _frames_inside(_window(flash)) == 1


def test_the_shake_decays_and_is_evaluated_per_frame():
    filters = build_impact_filters(
        plan_impacts(4.0, tension=10, duration=10.0), 1080, 1920
    )
    crop = [f for f in filters if f.startswith("crop=")][0]
    # crop re-evaluates x/y every frame by definition -- and REJECTS the
    # eval=frame option that scale and pad require, which is how this chain
    # failed its first real encode.
    assert "eval=frame" not in crop
    assert "t," in crop  # the offset really is a function of time
    assert "random(" in crop
    assert f"(1-(t-4.000)/{SHAKE_SECONDS})" in crop


def test_the_frame_is_given_room_to_move_before_it_shakes():
    """Shaking a full-frame picture exposes black edges."""
    filters = build_impact_filters(
        plan_impacts(4.0, tension=10, duration=10.0), 1000, 2000
    )
    crop = [f for f in filters if f.startswith("crop=")][0]
    crop_w = int(crop.split("=")[1].split(":")[0])
    crop_h = int(crop.split(":")[1])
    assert crop_w < 1000 and crop_h < 2000
    assert crop_w % 2 == 0 and crop_h % 2 == 0  # yuv420p halves both axes
    assert any(f.startswith("scale=1000:2000") for f in filters)


def test_the_two_axes_do_not_move_as_one_diagonal():
    filters = build_impact_filters(
        plan_impacts(4.0, tension=10, duration=10.0), 1080, 1920
    )
    crop = [f for f in filters if f.startswith("crop=")][0]
    x_part, y_part = crop.split(":x=")[1].split(":y=")
    assert "random(1)" in x_part
    assert "random(2)" in y_part


def test_nothing_to_plan_means_no_filters():
    assert build_impact_filters([], 1080, 1920) == []


# --- against a real encoder --------------------------------------------


def _has_ffmpeg():
    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
def test_ffmpeg_accepts_the_filter_chain_and_the_flash_is_visible(tmp_path):
    """The expressions are the risky part of this module -- ffmpeg's filter
    grammar fails at runtime, not at review time. So a real encode runs, and
    the flashed frame is then measured to prove it did something."""
    import numpy as np
    from moviepy import VideoFileClip

    from pipelines.script2video import _resolve_ffmpeg_binary

    ff = _resolve_ffmpeg_binary()
    source = str(tmp_path / "scene.mp4")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i",
         "color=c=0x202020:s=320x180:r=24:d=6", "-pix_fmt", "yuv420p", source],
        check=True, capture_output=True,
    )

    beats = plan_impacts(3.0, tension=10, duration=6.0)
    filters = build_impact_filters(beats, 320, 180, fps=24.0)
    out = str(tmp_path / "hit.mp4")
    result = subprocess.run(
        [ff, "-y", "-i", source, "-vf", ",".join(filters),
         "-pix_fmt", "yuv420p", out],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr[-1000:]

    with VideoFileClip(out) as clip:
        assert clip.duration == pytest.approx(6.0, abs=0.2)
        calm = np.asarray(clip.get_frame(1.0)).mean()
        after = np.asarray(clip.get_frame(4.5)).mean()
        # Every frame across the hit, not one sample near it: a window that
        # is one frame too wide is invisible to a single get_frame and is
        # exactly what shipped.
        step = 1.0 / 24.0
        across = [
            np.asarray(clip.get_frame(3.0 - 3 * step + n * step)).mean()
            for n in range(8)
        ]

    assert max(across) > calm + 40, "the impact frame is not brighter"
    assert sum(1 for value in across if value > calm + 40) == FLASH_FRAMES
    # ...and it is a FLASH: the picture is back to normal immediately after.
    assert after == pytest.approx(calm, abs=6)


@pytest.mark.asyncio
@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
async def test_a_broken_scene_ships_unhit(tmp_path):
    """Fail-open, like every finishing stage: never fail a paid job for an
    effect."""
    from pipelines.script2video import Script2VideoPipeline

    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")
    pipeline = Script2VideoPipeline(api_key="k", demo=False)

    class _Shot:
        deliver_seconds = 4.0

    result = await pipeline._apply_impact(
        str(broken), working_dir=str(tmp_path), shots=[_Shot()], scene_tension=10
    )
    assert result == str(broken)
