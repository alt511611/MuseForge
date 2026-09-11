"""A 16:9 master becomes 9:16 by throwing away 68% of its width.

Which 68% was never decided. It came off the middle, and the endpoint that
did it said so in its own docstring: "a *naive center crop*, not smart
subject-aware reframing. Content near the edges of the original frame may be
lost."

The same crop is what job a66acd59 is remembered for -- takes that came back
square on a 9:16 order, conformed by discarding 44% of their width, and what
lived in that 44% was the second character. Properly staged over-the-shoulder
two-shots were delivered as one woman with a stray hand at the edge of frame.

That case is caught earlier now. This one was not caught at all: it is a
button the product offers on purpose, converting into the format its market
actually watches -- two vertical apps hold roughly 70% of global short-drama
spending.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interfaces.reframe import (  # noqa: E402
    CENTRE_PULL,
    Window,
    crop_x_expression,
    interest_centre,
    is_still,
    plan_windows,
    window_x,
)


# ---------------------------------------------------------------------------
# What the measurement says
# ---------------------------------------------------------------------------

def test_a_subject_on_the_left_reads_as_being_on_the_left():
    columns = [10.0] * 64
    for x in range(6, 16):
        columns[x] = 200.0

    assert interest_centre(columns) < 0.25


def test_a_flat_frame_has_no_opinion():
    """Unknown resolves to the behaviour the product already had."""
    assert interest_centre([7.0] * 64) == pytest.approx(0.5)
    assert interest_centre([]) == 0.5
    assert interest_centre([0.0] * 64) == 0.5


def test_a_busy_background_does_not_outvote_the_subject():
    """Two thirds of the frame at half the subject's contrast.

    Without the background floor the wall wins on sheer area and the answer
    converges on the middle -- for a reason that has nothing to do with the
    middle being right.
    """
    columns = [0.0] * 64
    for x in range(0, 42):
        columns[x] = 40.0          # textured wall, right of frame it is not
    for x in range(50, 60):
        columns[x] = 100.0         # the face

    assert interest_centre(columns) > 0.7


# ---------------------------------------------------------------------------
# Where the window goes
# ---------------------------------------------------------------------------

def test_the_window_moves_most_of_the_way_and_never_all_of_it():
    """The measurement is contrast, not recognition, so it is never trusted whole."""
    hard_left = window_x(0.0, 1280, 404)
    slack = 1280 - 404

    assert hard_left > 0, "a lamp reading as a subject must not pin the crop to the edge"
    assert hard_left == pytest.approx(slack / 2 * (1 - CENTRE_PULL), abs=2)


def test_a_centred_film_exports_exactly_as_it_did_before():
    """The feature must not be able to regress the case that was already right."""
    centred = window_x(0.5, 1280, 404)
    nearly = window_x(0.51, 1280, 404)

    assert centred == 438
    assert nearly == centred, "a 1% offset is inside the noise of the measurement"


def test_the_window_stays_inside_the_picture():
    for centre in (0.0, 0.25, 0.5, 0.75, 1.0):
        x = window_x(centre, 1280, 404)
        assert 0 <= x <= 1280 - 404
        assert x % 2 == 0, "an odd offset is a filter error, not a one-pixel difference"


# ---------------------------------------------------------------------------
# How it reaches ffmpeg
# ---------------------------------------------------------------------------

def test_one_position_per_shot_held_for_the_whole_shot():
    """A reframe that drifts mid-shot is a camera move nobody directed."""
    windows = plan_windows(
        [(0.0, 4.0, 0.2), (4.0, 9.0, 0.8), (9.0, 12.0, 0.5)], 1280, 404
    )

    assert [round(w.start, 1) for w in windows] == [0.0, 4.0, 9.0]
    assert windows[0].x < windows[2].x < windows[1].x


def test_the_expression_is_stepwise_and_ends_without_a_test():
    expression = crop_x_expression(
        [Window(0.0, 4.0, 100), Window(4.0, 9.0, 700), Window(9.0, 12.0, 438)]
    )

    assert expression == "if(lt(t,4.000),100,if(lt(t,9.000),700,438))"
    # The last branch has no test of its own, which is what keeps a clip a few
    # frames longer than the measurement from running out of window.
    assert expression.rstrip(")").endswith("438")


def test_a_film_that_does_not_move_gets_a_number_not_an_expression():
    assert is_still([Window(0.0, 4.0, 438), Window(4.0, 9.0, 438)])
    assert not is_still([Window(0.0, 4.0, 438), Window(4.0, 9.0, 120)])
    assert crop_x_expression([]) == "0"


# ---------------------------------------------------------------------------
# And the whole thing, through real ffmpeg
# ---------------------------------------------------------------------------

def _has_ffmpeg() -> bool:
    from pipelines.idea2video import resolve_ffmpeg_binary

    try:
        subprocess.check_output([resolve_ffmpeg_binary(), "-version"], text=True)
        return True
    except Exception:
        return False


def _mean_luma(path: str) -> float:
    from pipelines.idea2video import resolve_ffmpeg_binary

    out = subprocess.run(
        [
            resolve_ffmpeg_binary(), "-hide_banner", "-loglevel", "error",
            "-i", path,
            "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
            "-an", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    values = [
        float(line.split("=")[1])
        for line in (out.stdout + out.stderr).splitlines()
        if "YAVG=" in line
    ]
    return sum(values) / len(values) if values else 0.0


@pytest.mark.asyncio
async def test_the_person_at_the_edge_survives_the_vertical_export(tmp_path):
    """A subject in the left third, which a centre crop cannot keep.

    The fixture is deliberately unambiguous -- a bright block on black -- so
    the assertion is about WHERE the window went, not about how well contrast
    stands in for a face.
    """
    if not _has_ffmpeg():
        pytest.skip("ffmpeg is not available")

    from pipelines.idea2video import export_alternate_format, resolve_ffmpeg_binary

    source = tmp_path / "master.mp4"
    subprocess.run(
        [
            resolve_ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=1280x720:d=2",
            "-f", "lavfi", "-i", "color=c=white:s=160x360:d=2",
            "-filter_complex", "[0][1]overlay=x=120:y=180",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
        ],
        check=True, capture_output=True,
    )

    vertical = tmp_path / "vertical.mp4"
    await export_alternate_format(str(source), str(vertical), "9:16")

    assert os.path.isfile(vertical)
    assert _mean_luma(str(vertical)) > 5.0, (
        "the white block sits at x=120-280; a centre crop keeps 438-842 and "
        "would deliver a black film"
    )
