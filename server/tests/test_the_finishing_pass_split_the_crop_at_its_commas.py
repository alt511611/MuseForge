"""Job 8d082bf7: "Finishing pass failed (exit=8) ... No such filter: '7.880)'".

The crop offset is an expression, ``if(lt(t,7.880),a,b)``, and the finishing
pass joins its filters with commas. An unescaped comma inside the expression
ends the crop filter there. The film shipped, through the slower fallback
passes, after a failed encode.
"""
import os
import subprocess
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interfaces.reframe import Anchor, crop_filter, spans_from_durations  # noqa: E402


def _plan():
    return spans_from_durations(
        [5.0, 6.0, 7.0],
        {0: Anchor(x=0.7, confidence=0.75), 1: Anchor(x=0.3, confidence=0.75), 2: Anchor(x=0.7, confidence=0.75)},
    )


def test_every_comma_inside_the_offset_is_escaped_for_the_filtergraph():
    crop = crop_filter(960, 960, 540, 960, spans=_plan())
    body = crop[len("crop=540:960:"):]
    for index, char in enumerate(body):
        if char == ",":
            assert body[index - 1] == "\\", crop


def test_spans_that_frame_the_same_way_are_one_span_and_need_no_switch():
    same = spans_from_durations(
        [5.0, 6.0], {0: Anchor(x=0.7, confidence=0.75), 1: Anchor(x=0.7, confidence=0.75)}
    )
    assert "if(" not in crop_filter(960, 960, 540, 960, spans=same)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_ffmpeg_accepts_the_crop_inside_a_comma_joined_chain():
    chain = ",".join(["scale=960:960", crop_filter(960, 960, 540, 960, spans=_plan()), "setsar=1"])
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=960x960:d=1:r=10",
         "-vf", chain, "-f", "null", "-"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
