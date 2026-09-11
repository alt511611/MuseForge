"""Thirty seconds of rising tension, scored at one level from end to end.

The screenwriter gives every scene a tension from 1 to 10 and the number is
read everywhere -- scene length, shot scale, acting beats, transitions. It
stopped at the soundtrack. Delivered drama 10e143bb measures a loudness range
of 5.4 LU across its whole film, which is what a mix with no shape measures.

Nothing here generates a second piece of music. The bed is the bed; what was
missing was somebody riding the fader under it, which is a number, not a
render.
"""

import subprocess
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interfaces.score import (  # noqa: E402
    LOUDEST,
    gain_at,
    MIN_TENSION_SPREAD,
    QUIETEST,
    Level,
    gain_for,
    level_expression,
    plan_score_levels,
)

#: A three-scene drama that builds, at the lengths a 30-second film gets.
RISING = ([(0.0, 8.0), (8.0, 18.0), (18.0, 30.0)], [3, 6, 9])


def test_a_tense_scene_is_louder_than_a_quiet_one():
    assert gain_for(1) == pytest.approx(QUIETEST)
    assert gain_for(10) == pytest.approx(LOUDEST)
    assert gain_for(3) < gain_for(6) < gain_for(9)


def test_the_curve_is_pinned_to_both_ends_of_the_film():
    """Otherwise the ride runs off its own control points and extrapolates."""
    levels = plan_score_levels(*RISING)

    assert levels[0].at == 0.0
    assert levels[-1].at == 30.0
    assert levels[0].gain == levels[1].gain, "it holds until the first scene's middle"
    assert levels[-1].gain == levels[-2].gain, "and holds again after the last one's"


def test_the_control_points_sit_in_the_middle_of_their_scenes():
    """A score that steps at a cut reads as an edit error, not as drama."""
    levels = plan_score_levels(*RISING)
    middles = [level.at for level in levels]

    assert 4.0 in middles and 13.0 in middles and 24.0 in middles


def test_a_film_with_no_curve_is_given_no_ride():
    """An automation that moves for nothing is worse than a flat bed."""
    flat = plan_score_levels([(0.0, 10.0), (10.0, 20.0)], [5, 5])
    nearly_flat = plan_score_levels([(0.0, 10.0), (10.0, 20.0)], [5, 5 + MIN_TENSION_SPREAD - 1])
    untensioned = plan_score_levels([(0.0, 10.0), (10.0, 20.0)], [0, 0])
    one_scene = plan_score_levels([(0.0, 10.0)], [9])

    assert flat == [] and nearly_flat == [] and untensioned == [] and one_scene == []


def test_a_film_with_no_ride_keeps_the_mixer_s_own_level():
    assert level_expression([], 0.55) == "0.5500"
    assert level_expression([Level(0.0, 1.0)], 0.55) == "0.5500"


def test_the_ride_reaches_each_scene_s_level_at_its_middle():
    levels = plan_score_levels(*RISING)

    quiet, middle, loud = (gain_at(levels, t) for t in (4.0, 13.0, 24.0))

    assert quiet == pytest.approx(gain_for(3))
    assert middle == pytest.approx(gain_for(6))
    assert loud == pytest.approx(gain_for(9))


def test_between_two_scenes_the_ride_is_on_its_way_there():
    """Continuous, which is what makes it a swell rather than a step."""
    levels = plan_score_levels(*RISING)

    assert gain_at(levels, 8.5) == pytest.approx(
        (gain_for(3) + gain_for(6)) / 2
    )
    # ...and it holds outside the control points rather than extrapolating.
    assert gain_at(levels, 0.0) == pytest.approx(gain_for(3))
    assert gain_at(levels, 30.0) == pytest.approx(gain_for(9))
    assert gain_at([], 5.0) == 1.0


def test_the_expression_is_the_same_curve_ffmpeg_reads():
    """Pinned literally, because this string is the only copy ffmpeg sees."""
    expression = level_expression(
        [Level(0.0, 1.0), Level(10.0, 2.0)], 0.5
    )

    assert expression == "if(lt(t,0.000),0.5000,if(lt(t,10.000),0.5000+0.050000*(t-0.000),1.0000))"


def test_ffmpeg_accepts_the_expression_it_is_given():
    """The one failure mode that would be silent.

    A malformed volume expression does not raise here; it fails the whole
    ffmpeg mix, and mix_audio_layers answers None and falls back to the
    moviepy mixer -- which drops the foley and re-encodes the picture. The
    film still ships. It just quietly stops being the film this pipeline
    makes.
    """
    from pipelines.idea2video import resolve_ffmpeg_binary

    expression = level_expression(plan_score_levels(*RISING), 0.55)
    result = subprocess.run(
        [
            resolve_ffmpeg_binary(), "-hide_banner", "-v", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-af", f"volume='{expression}':eval=frame",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )

    assert result.returncode == 0, result.stderr[-400:]
