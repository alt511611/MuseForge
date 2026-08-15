"""Internal cutting: micro-drama rhythm out of a single paid generation.

The invariant that matters most is arithmetic, not taste: the framings must
TILE the source clip. A pacing pass that shortened a scene would deliver less
video than the credit bought and would trip check_master_duration on the
finished master, so the tiling is pinned here — including against a real
ffmpeg run, because "the plan sums correctly" and "the encoded file is the
same length" are two different claims.
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces import pacing  # noqa: E402
from interfaces import pacing as pacing_mod  # noqa: E402
from interfaces.pacing import (  # noqa: E402
    MIN_CLIP_SECONDS,
    MIN_HOLD_SECONDS,
    TAIL_GUARD_SECONDS,
    plan_internal_cuts,
    total_duration,
)
from pipelines.script2video import (  # noqa: E402
    _probe_duration,
    apply_internal_cuts,
    build_internal_cut_filter,
)


def _fast(monkeypatch):
    """A director style that wants its scenes cut."""
    monkeypatch.delenv("MUSEFORGE_INTERNAL_CUTS", raising=False)


# --- when it runs at all -----------------------------------------------


def test_slow_styles_are_left_alone(monkeypatch):
    _fast(monkeypatch)
    assert plan_internal_cuts(10.0, tension=9, pacing="slow") == []
    assert plan_internal_cuts(10.0, tension=9, pacing="medium") == []


def test_fast_styles_are_cut(monkeypatch):
    _fast(monkeypatch)
    assert len(plan_internal_cuts(10.0, tension=9, pacing="fast")) >= 2


def test_operator_can_force_it_on_or_off(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_INTERNAL_CUTS", "on")
    assert plan_internal_cuts(10.0, pacing="slow")
    monkeypatch.setenv("MUSEFORGE_INTERNAL_CUTS", "off")
    assert plan_internal_cuts(10.0, pacing="fast") == []


def test_short_clips_are_not_worth_a_re_encode(monkeypatch):
    _fast(monkeypatch)
    assert plan_internal_cuts(MIN_CLIP_SECONDS - 0.1, pacing="fast") == []


def test_unreadable_duration_changes_nothing(monkeypatch):
    _fast(monkeypatch)
    assert plan_internal_cuts(0.0, pacing="fast") == []
    assert plan_internal_cuts(None, pacing="fast") == []


# --- the invariants ----------------------------------------------------


@pytest.mark.parametrize("duration", [5.0, 6.0, 8.0, 9.5, 10.0, 12.0])
@pytest.mark.parametrize("tension", [1, 5, 8, 10])
def test_framings_tile_the_clip_exactly(monkeypatch, duration, tension):
    """No gap, no overlap, no lost second: the scene is exactly as long as
    the credit that bought it."""
    _fast(monkeypatch)
    cuts = plan_internal_cuts(duration, tension=tension, pacing="fast")
    if not cuts:
        return
    assert cuts[0].start == 0.0
    assert cuts[-1].end == pytest.approx(duration)
    for earlier, later in zip(cuts, cuts[1:]):
        assert later.start == pytest.approx(earlier.end)
    assert total_duration(cuts) == pytest.approx(duration)


@pytest.mark.parametrize("duration", [5.0, 6.0, 8.0, 9.5, 10.0, 12.0])
@pytest.mark.parametrize("tension", [1, 5, 8, 10])
def test_no_framing_is_too_short_to_read(monkeypatch, duration, tension):
    _fast(monkeypatch)
    for cut in plan_internal_cuts(duration, tension=tension, pacing="fast"):
        assert cut.duration >= MIN_HOLD_SECONDS - 1e-6


@pytest.mark.parametrize("duration", [6.0, 8.0, 10.0, 12.0])
def test_nothing_is_cut_inside_the_tail_guard(monkeypatch, duration):
    """The acted peak lands in the final second, and a dissolve may start
    there. A cut across either steps on it."""
    _fast(monkeypatch)
    cuts = plan_internal_cuts(duration, tension=9, pacing="fast")
    joins = [cut.start for cut in cuts[1:]]
    for join in joins:
        assert join <= duration - TAIL_GUARD_SECONDS + 1e-6


def test_the_scene_opens_on_an_unzoomed_establishing_hold(monkeypatch):
    _fast(monkeypatch)
    cuts = plan_internal_cuts(10.0, tension=9, pacing="fast")
    assert cuts[0].zoom == 1.0
    assert cuts[0].duration >= MIN_HOLD_SECONDS


def test_higher_tension_cuts_faster(monkeypatch):
    _fast(monkeypatch)
    calm = plan_internal_cuts(12.0, tension=2, pacing="fast")
    frantic = plan_internal_cuts(12.0, tension=10, pacing="fast")
    assert len(frantic) > len(calm)


def test_punch_ins_favour_the_face_except_on_wide_shots(monkeypatch):
    _fast(monkeypatch)
    close = plan_internal_cuts(10.0, tension=9, shot_type="close-up", pacing="fast")
    wide = plan_internal_cuts(10.0, tension=9, shot_type="wide shot", pacing="fast")
    assert close[1].y_bias < 0.5  # eyes sit above centre
    assert wide[1].y_bias == 0.5


# --- the filter graph --------------------------------------------------


def test_filter_rebases_timestamps_on_every_segment():
    """Without setpts the concatenated clip's presentation times jump
    backwards, which players read as a broken file."""
    cuts = [pacing.Cut(0.0, 2.0, 1.0), pacing.Cut(2.0, 4.0, 1.3, 0.4)]
    graph = build_internal_cut_filter(cuts, 1920, 1080)
    assert graph.count("setpts=PTS-STARTPTS") == 2
    assert "concat=n=2:v=1:a=0[cut]" in graph


def test_zoomed_segments_crop_then_scale_back_to_frame_size():
    cuts = [pacing.Cut(0.0, 2.0, 1.0), pacing.Cut(2.0, 4.0, 1.25, 0.4)]
    graph = build_internal_cut_filter(cuts, 1080, 1920)
    assert "crop=864:1536" in graph  # 1080/1.25, 1920/1.25, both even
    assert "scale=1080:1920" in graph


def test_crop_geometry_is_always_even():
    """yuv420p halves both axes, so x264 refuses odd dimensions outright."""
    cuts = [pacing.Cut(0.0, 2.0, 1.0), pacing.Cut(2.0, 4.0, 1.37, 0.4)]
    graph = build_internal_cut_filter(cuts, 1907, 1073)
    crop = [part for part in graph.split(",") if part.startswith("crop=")][0]
    numbers = [int(n) for n in crop.split("=")[1].split("]")[0].split(":")]
    assert all(n % 2 == 0 for n in numbers), crop


# --- against a real encoder --------------------------------------------


def _ffmpeg() -> str:
    binary = os.environ.get("MUSEFORGE_FFMPEG_BINARY") or shutil.which("ffmpeg")
    if binary:
        return binary
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return ""


@pytest.mark.asyncio
async def test_encoded_scene_keeps_its_exact_length(tmp_path, monkeypatch):
    """The plan summing correctly and the FILE being the same length are two
    different claims, and only the second one is what the customer paid for."""
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        pytest.skip("no ffmpeg available")

    source = tmp_path / "scene.mp4"
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi",
            "-i", "testsrc=size=640x360:rate=24:duration=8",
            "-pix_fmt", "yuv420p", str(source),
        ],
        check=True,
        capture_output=True,
    )
    before = _probe_duration(str(source))
    assert before > 0

    _fast(monkeypatch)
    cuts = plan_internal_cuts(before, tension=9, pacing="fast")
    assert len(cuts) >= 2

    out = await apply_internal_cuts(str(source), str(tmp_path / "cut.mp4"), cuts)
    assert out != str(source), "the cut pass should have produced a new file"
    after = _probe_duration(out)
    # One frame of tolerance at 24fps: trimming lands on frame boundaries.
    assert after == pytest.approx(before, abs=1 / 24 + 0.01)


@pytest.mark.asyncio
async def test_a_broken_encode_ships_the_uncut_scene(tmp_path, monkeypatch):
    """Fail-open, like every other finishing stage: a pacing pass must never
    fail a paid job."""
    source = tmp_path / "not-a-video.mp4"
    source.write_bytes(b"not a video")
    cuts = [pacing.Cut(0.0, 2.0, 1.0), pacing.Cut(2.0, 4.0, 1.3, 0.4)]
    out = await apply_internal_cuts(str(source), str(tmp_path / "cut.mp4"), cuts)
    assert out == str(source)


@pytest.mark.asyncio
async def test_no_plan_means_no_re_encode(tmp_path):
    source = tmp_path / "scene.mp4"
    source.write_bytes(b"whatever")
    assert await apply_internal_cuts(str(source), str(tmp_path / "cut.mp4"), []) == str(
        source
    )


# --- long takes earn a cut whatever the style says ----------------------
#
# Measured on a delivered 30-second drama (scenes of 8, 10 and 12 seconds):
#
#     scene 1   8.0s   mean inter-frame motion 18.3
#     scene 2  10.0s                           21.1
#     scene 3  12.1s                           11.3   <- the climax
#
# The longest scene moved at half the rate of the others, and it was the one
# the story turns on.


def test_a_long_take_is_cut_even_in_a_slow_style(monkeypatch):
    _fast(monkeypatch)
    assert plan_internal_cuts(12.0, tension=5, pacing="slow")
    assert plan_internal_cuts(12.0, tension=5, pacing="medium")


def test_a_short_take_still_follows_the_director(monkeypatch):
    """The length rule is a floor under the style, not a replacement for it:
    a slow style still gets slow framings on scenes that are working."""
    _fast(monkeypatch)
    assert plan_internal_cuts(8.0, tension=5, pacing="slow") == []
    assert plan_internal_cuts(8.0, tension=5, pacing="fast")


def test_the_threshold_is_where_the_measurement_put_it(monkeypatch):
    _fast(monkeypatch)
    assert plan_internal_cuts(pacing_mod.LONG_TAKE_SECONDS - 0.1, pacing="slow") == []
    assert plan_internal_cuts(pacing_mod.LONG_TAKE_SECONDS, pacing="slow")


def test_off_still_means_off(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_INTERNAL_CUTS", "off")
    assert plan_internal_cuts(12.0, tension=10, pacing="slow") == []
