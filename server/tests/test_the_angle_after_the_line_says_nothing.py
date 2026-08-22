"""An angle that opens after the last word is not a dialogue shot.

A delivered job (three scenes, coverage of two) closes on ten and a half
seconds of its protagonist mouthing a speech in total silence:

    scene 2   12.08s of picture, cut 6.04 + 6.04 into two angles
              1.46s of line  ("No, no -- that's not --")
    log       "Lip-synced clip came back 1.46s against a 12.08s take
               ... the remaining 10.62s of the take was rejoined behind it"

The sync pass is not what put a performance there. The STORYBOARD did: a
dialogue scene handed every angle it bought the same direction -- "the
speaking character's mouth is fully visible ... their lips will be animated
to the dialogue" on the frame, a motion description written knowing the words
on the clip -- including the second angle, which opens four and a half
seconds after the line has stopped. The model was asked for a talking head
twice and delivered one twice; only the first had any sound to go under it.

Speech is laid down from the scene's own start
(idea2video.plan_scene_speech_anchors) and the angles divide the same budget
(shot_plan.split_scene_seconds), so which angles the words reach is arithmetic
rather than a guess.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from interfaces.shot import StoryboardShot  # noqa: E402
from interfaces.shot_plan import (  # noqa: E402
    MASTER,
    REACTION,
    POST_LINE_MARGIN_SECONDS,
    SLOWEST_SPEECH_WORDS_PER_SECOND,
    screen_seconds,
    shots_the_line_reaches,
)
from pipelines.script2video import build_motion_prompt  # noqa: E402

CLOSED = "the mouth stays closed"


def _shot(seconds, role=MASTER, deliver=0.0):
    return StoryboardShot(
        idx=0,
        visual_desc="Mara at the container door",
        motion_desc="she speaks into the handset",
        duration_seconds=seconds,
        deliver_seconds=deliver,
        role=role,
    )


def _words(count, speaker="MARA"):
    return f"{speaker}: " + " ".join(["word"] * count)


# ── which angles the words reach ────────────────────────────────────────────


def test_the_delivered_job_scene_that_broke_it():
    """12 seconds of picture, five words of line, cut 6 + 6. The second angle
    opens four and a half seconds after the last one is said."""
    assert shots_the_line_reaches([_shot(6), _shot(6)], _words(5)) == [True, False]


@pytest.mark.parametrize(
    "shots, words",
    [
        ([_shot(4), _shot(4)], 12),   # scene 0: 8s of picture, a long line
        ([_shot(4), _shot(6)], 9),    # scene 1: 10s, a line that runs to 5.21s
    ],
)
def test_the_same_job_s_other_scenes_are_left_alone(shots, words):
    """Both of these really are still under the line when they open. Marking
    them silent would be the closed-mouth delivery, reintroduced."""
    assert shots_the_line_reaches(shots, _words(words)) == [True, True]


def test_a_single_angle_scene_is_untouched():
    """The default, and the overwhelming majority. One angle opens at zero,
    and zero is under every line there has ever been."""
    assert shots_the_line_reaches([_shot(12)], _words(3)) == [True]
    assert shots_the_line_reaches([], _words(3)) == []


def test_a_scene_with_no_dialogue_decides_nothing_here():
    """`has_dialogue` at the call site already covers a silent scene; this
    must not start second-guessing it from an empty string."""
    assert shots_the_line_reaches([_shot(6), _shot(6)], "") == [True, True]
    assert shots_the_line_reaches([_shot(6), _shot(6)], "   ") == [True, True]


def test_a_reaction_cutaway_is_never_reached_whatever_the_clock():
    """A reaction shot is the other character listening (plan_scene_shots).
    There is no mouth in it to drive even when it opens mid-sentence."""
    reached = shots_the_line_reaches(
        [_shot(8, deliver=6.0), _shot(8, REACTION, deliver=2.0)], _words(40)
    )
    assert reached == [True, False]


def test_the_floor_is_slow_enough_to_protect_a_slow_line():
    """The rate only ever REMOVES the speaking direction, so it is set below
    every line the delivered job measured (1.73 w/s at slowest)."""
    assert SLOWEST_SPEECH_WORDS_PER_SECOND < 1.73
    assert POST_LINE_MARGIN_SECONDS > 0
    # Ten words at the floor is 6.7s of speech plus a second of air; an angle
    # opening at 7s is inside it and keeps its direction.
    assert shots_the_line_reaches([_shot(7), _shot(5)], _words(10))[1] is True


def test_the_length_read_is_the_length_on_screen():
    """A coverage angle carries its length in duration_seconds; a master that
    made room for a cutaway carries it in deliver_seconds."""
    assert screen_seconds(_shot(6)) == 6.0
    assert screen_seconds(_shot(8, deliver=6.0)) == 6.0
    assert screen_seconds(_shot(0)) == 0.0


# ── what the silent angle is actually told ──────────────────────────────────


def test_the_silent_angle_is_told_to_stop_talking():
    prompt = build_motion_prompt(_shot(6), speaking=False)
    assert CLOSED in prompt


def test_speaking_is_the_default_and_changes_nothing():
    """Every existing caller, and every single-angle scene, must produce the
    prompt it produced before this existed."""
    shot = _shot(6)
    assert build_motion_prompt(shot) == build_motion_prompt(shot, speaking=True)
    assert CLOSED not in build_motion_prompt(shot)


def test_the_silence_is_named_on_the_character_when_one_is_matched():
    class Char:
        name = "Mara Voss"

    prompt = build_motion_prompt(_shot(6), Char(), speaking=False)
    assert "Mara Voss has finished speaking" in prompt


def test_the_silence_is_stated_as_performance_not_prohibition():
    """Kling declares no negative_prompt, so "do not speak" is just the word
    "speak" in the positive one."""
    prompt = build_motion_prompt(_shot(6), speaking=False)
    assert "not speak" not in prompt
    assert "in the eyes and the body" in prompt
