"""A shot that shows nobody must not describe, or direct, anybody.

Job 5b886720 (five castaways, a boat, a fire) delivered strangers in places the
storyboard wrote empty. Its Nano Banana frame for the opening "deserted
shoreline" contained all five castaways, because ``characters_in_frame`` answered
a shot naming nobody with the scene's whole cast ("the right answer for an
establishing plate") and the prompt then carried "Appearance is FIXED" and
"Cast is closed: ... appear" for each of them. And the video prompt for the
flames shot asked an empty plate to land on "eyes closing for a beat, a long
breath leaving through parted lips", and came back with three strangers whose
eyes were closed.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    EMPTY_SHOT_CLAUSE,
    build_frame_prompt,
    build_motion_prompt,
    characters_in_frame,
    shot_is_unpeopled,
)

CAST = [
    CharacterInScene(idx=i, name=n, static_features=f"a {a} sailor, weathered face", wardrobe="a wet oilskin")
    for i, (n, a) in enumerate(
        [("Yusuf", "grizzled"), ("Deniz", "young"), ("Kemal", "stocky"), ("Ayse", "tall"), ("Selim", "lean")]
    )
]


def _shot(visual, motion="slow push in", expression="", peak="", shot_type="wide shot"):
    return StoryboardShot(
        idx=0, visual_desc=visual, motion_desc=motion, shot_type=shot_type, lens="35mm",
        expression_desc=expression, expression_peak_desc=peak,
    )


SHORE = _shot("A rocky, deserted shoreline at dawn, grey surf folding onto black stones")
FLAMES = _shot(
    "A driftwood fire on the sand, flames leaning in the wind",
    expression="no human presence",
    peak="the brace letting go: eyes closing for a beat, a long breath leaving through parted lips",
)
CREW = _shot("Three sailors haul the lifeboat over the shingle")
HAND = _shot("A hand closes around the rope")


def _frame(shot, matched=None):
    return build_frame_prompt(
        "Cinematic", shot, setting_location="a bleak shore", setting_time_of_day="dawn",
        setting_era="present day", characters=CAST, matched_char=matched,
    )


def test_a_deserted_shoreline_is_recognised_as_empty():
    assert shot_is_unpeopled(SHORE, CAST)
    assert shot_is_unpeopled(FLAMES, CAST)


def test_a_shot_that_shows_people_is_not_empty_even_when_it_names_nobody():
    assert not shot_is_unpeopled(CREW, CAST)
    assert not shot_is_unpeopled(HAND, CAST)


def test_a_shot_that_names_a_character_is_not_empty():
    assert not shot_is_unpeopled(_shot("Yusuf stares at the horizon"), CAST)


def test_an_anchored_shot_is_not_empty():
    assert not shot_is_unpeopled(SHORE, CAST, matched_char=CAST[0])


def test_the_empty_shot_describes_nobody_to_the_frame():
    assert characters_in_frame(SHORE, CAST) == []


def test_a_shot_of_sailors_still_falls_back_to_the_whole_cast():
    assert len(characters_in_frame(CREW, CAST)) == 5


def test_the_empty_frame_names_no_one_and_says_it_is_empty():
    prompt = _frame(SHORE)
    for name in ("Yusuf", "Deniz", "Kemal", "Ayse", "Selim"):
        assert name not in prompt
    assert "Appearance is FIXED" not in prompt
    assert "Cast is closed" not in prompt
    assert EMPTY_SHOT_CLAUSE.strip() in prompt


def test_the_empty_frame_carries_no_axis_rule():
    two = CAST[:2]
    prompt = build_frame_prompt("Cinematic", SHORE, characters=two)
    assert "180-degree" not in prompt


def test_a_populated_frame_is_unchanged():
    prompt = _frame(CREW)
    assert "Cast is closed" in prompt
    assert EMPTY_SHOT_CLAUSE.strip() not in prompt


def test_the_flames_are_not_told_to_close_their_eyes():
    prompt = build_motion_prompt(FLAMES, None, unpeopled=True)
    for phrase in ("eyes closing", "parted lips", "Performance arc", "facial identity", "characters keep"):
        assert phrase not in prompt
    assert EMPTY_SHOT_CLAUSE.strip() in prompt
    assert "slow push in" in prompt


def test_a_world_that_has_changed_still_reaches_the_empty_shot():
    prompt = build_motion_prompt(FLAMES, None, world_state="the power is out", unpeopled=True)
    assert "the power is out" in prompt


def test_a_populated_shot_is_directed_exactly_as_before():
    shot = _shot("Yusuf grips the rail", expression="fear", peak="resolve")
    prompt = build_motion_prompt(shot, CAST[0])
    assert "Performance arc" in prompt and "facial identity" in prompt
    assert prompt == build_motion_prompt(shot, CAST[0], unpeopled=False)


def test_the_empty_frame_is_not_asked_for_a_readable_face():
    # The storyboard artist writes an emotion into every shot and the acting
    # pass fills the field unconditionally, so the empty shot arrives with one.
    shot = _shot("A driftwood fire on the sand", expression="grief, trembling chin")
    prompt = _frame(shot)
    assert "Facial expression" not in prompt
    assert "readable" not in prompt


def test_a_populated_frame_still_asks_for_the_face():
    prompt = _frame(_shot("Yusuf grips the rail", expression="fear"), matched=CAST[0])
    assert "Facial expression and body language: fear" in prompt
