"""Fixed second budget: flat margin, kept promise, preserved pacing.

The provider bills per second; the product sells credits per scene. Left
unlinked, an identical 1-credit charge bought 5-9 seconds depending on what
the storyboard agent chose -- a 24-point gross-margin swing decided by the
customer. A drama now gets SECONDS_PER_CREDIT x scenes seconds, fixed before
any credit is charged, with tension deciding only how that total is split.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.second_budget import (  # noqa: E402
    MAX_SCENE_SECONDS,
    MIN_SCENE_SECONDS,
    SECONDS_PER_CREDIT,
    billable_seconds,
    distribute_budget,
    total_budget_seconds,
)
from interfaces.shot import StoryboardShot  # noqa: E402

#: Real provider rate: Kling bills $0.11 per generated second, linearly.
KLING_PER_SECOND = 0.11
#: Per-scene costs that do NOT scale with duration (frame + storyboard call).
FIXED_PER_SCENE = 0.048


def _margin(price_per_credit, tensions):
    durations = distribute_budget(tensions)
    cost = billable_seconds(durations) * KLING_PER_SECOND + len(tensions) * FIXED_PER_SCENE
    revenue = len(tensions) * price_per_credit
    return (revenue - cost) / revenue * 100


# --- the budget is exact, in the unit that gets billed ------------------


@pytest.mark.parametrize(
    "tensions",
    [
        [3, 6, 8, 10, 4],       # the template's dramatic arc
        [1, 1, 1, 1, 1],        # all quiet
        [10, 10, 10, 10, 10],   # all peak
        [1, 10, 1, 10, 1],      # extreme spread -- clamps on both ends
        [0, 0, 0],              # legacy script, no tension at all
        [7],                    # single scene
        [1, 10],                # two scenes, opposite ends
        [2, 4, 6, 8, 10, 7, 5, 3],
        [5] * 24,               # Pro's scene ceiling
    ],
)
def test_budget_is_spent_exactly(tensions):
    """Whole seconds, summing to the budget. The pipeline sends an INTEGER
    duration, so a fractional split would silently under-deliver: truncating
    4.3 -> 4 across five scenes loses video the customer paid for."""
    durations = distribute_budget(tensions)
    assert len(durations) == len(tensions)
    assert billable_seconds(durations) == int(total_budget_seconds(len(tensions)))
    assert all(d == int(d) for d in durations), durations


@pytest.mark.parametrize(
    "tensions", [[3, 6, 8, 10, 4], [1, 10, 1, 10, 1], [1] * 5, [10] * 5, [5] * 24]
)
def test_every_scene_stays_within_bounds(tensions):
    for d in distribute_budget(tensions):
        assert MIN_SCENE_SECONDS <= d <= MAX_SCENE_SECONDS, d


def test_empty_script_does_not_crash():
    assert distribute_budget([]) == []


# --- the point: margin no longer depends on the story -------------------


def test_margin_is_flat_across_wildly_different_stories():
    """The whole reason this exists. Before, a 5-scene job cost anywhere from
    5x$0.617 to 5x$1.057 depending on what the storyboard chose."""
    stories = [
        [3, 6, 8, 10, 4],
        [1, 1, 1, 1, 1],
        [10, 10, 10, 10, 10],
        [1, 10, 1, 10, 1],
        [0, 0, 0, 0, 0],
    ]
    margins = [_margin(1.80, s) for s in stories]
    assert max(margins) - min(margins) < 0.5, (
        f"margin still swings with the story: {[round(m, 1) for m in margins]}"
    )


def test_margin_no_longer_set_by_the_customer():
    """Concretely: the worst-case story can no longer be materially cheaper
    to serve than the best-case one."""
    quiet = _margin(1.80, [1] * 5)
    peak = _margin(1.80, [10] * 5)
    assert abs(quiet - peak) < 0.5, (quiet, peak)


# --- pacing survives ----------------------------------------------------


def test_tension_still_shapes_the_rhythm():
    """Flattening cost must not flatten the film: a climax still runs long
    and a quiet setup still runs short, inside the same fixed total."""
    durations = distribute_budget([3, 6, 8, 10, 4])
    climax = durations[3]          # tension 10
    setup = durations[0]           # tension 3
    assert climax > setup, durations
    assert climax >= 1.5 * setup, durations


def test_uniform_tension_gives_uniform_scenes():
    durations = distribute_budget([5, 5, 5, 5])
    assert len(set(durations)) == 1, durations


def test_legacy_scripts_distribute_evenly():
    """No tension anywhere -> even split, not a collapse to the floor."""
    durations = distribute_budget([0, 0, 0, 0])
    assert durations == [SECONDS_PER_CREDIT] * 4


# --- the storyboard agent honours the budget ----------------------------


def _shot(duration):
    return StoryboardShot(
        idx=0, visual_desc="x", motion_desc="y", duration_seconds=duration
    )


@pytest.mark.parametrize("model_pick", [3.0, 5.0, 12.0, 15.0])
def test_budget_overrides_whatever_the_model_picked(model_pick):
    """The budget is SET, not capped. Letting the model come in under budget
    would make the job's cost unpredictable at the moment credits are
    charged, which is exactly the variance being removed."""
    shots = [_shot(model_pick)]
    StoryboardArtist._clamp_durations(shots, is_finale=False, tension=5, budget=9.0)
    assert shots[0].duration_seconds == 9.0


def test_without_a_budget_the_old_cap_behaviour_survives():
    """Legacy callers and single-scene tests keep cap-only semantics."""
    shots = [_shot(15.0)]
    StoryboardArtist._clamp_durations(shots, is_finale=False, tension=5, budget=0.0)
    assert shots[0].duration_seconds == StoryboardArtist.duration_cap(False, 5)


@pytest.mark.asyncio
async def test_budget_reaches_the_shot_through_design_storyboard():
    from interfaces.character import CharacterInScene

    artist = StoryboardArtist(api_key="")
    artist.muapi_key = ""  # force the deterministic template path
    shots = await artist.design_storyboard(
        script="They finally speak.",
        characters=[CharacterInScene(idx=0, name="Ayse", static_features="52")],
        scene_duration=11.0,
    )
    assert shots[0].duration_seconds == 11.0


# --- the quote states the promise ---------------------------------------


def test_credit_breakdown_states_the_seconds():
    from api import build_credit_breakdown

    result = build_credit_breakdown(5, plan="pro")
    assert result["video_seconds"] == int(5 * SECONDS_PER_CREDIT)
    assert result["seconds_per_credit"] == SECONDS_PER_CREDIT
    assert "sn video" in result["breakdown"][0]["label"]


def test_quoted_seconds_match_what_the_pipeline_will_request():
    """The quote and the provider call must agree, or the margin promise is
    fiction."""
    from api import build_credit_breakdown

    for scenes, tensions in ((5, [3, 6, 8, 10, 4]), (3, [5, 5, 5]), (8, [1] * 8)):
        quoted = build_credit_breakdown(scenes, plan="pro")["video_seconds"]
        actual = billable_seconds(distribute_budget(tensions))
        assert quoted == actual, (scenes, quoted, actual)


# --- the split also has to know what there is to say ---------------------
#
# Tension decides how the total is spread, and tension does not know how long
# the line is. Delivered job 1ac6d945-b53: three scenes, rising tension, split
# 8/10/12 -- and the 12 went to the scene with the SHORTEST line in the
# script. Its climax spoke for 1.38 seconds and held for 10.7 more in silence,
# while the scene carrying 4.5 seconds of dialogue was cut at 10. The film
# ends on ten seconds of someone standing still.


#: Speech the voice provider actually measured on that job, per scene.
DELIVERED_SPEECH = [1.76, 4.50, 1.38]
#: Its tensions, recovered from the 8/10/12 the run logged.
DELIVERED_TENSIONS = [4, 5, 6]


def test_the_ceiling_goes_to_the_scene_with_something_to_say():
    """Not to the tensest scene regardless. The longest line gets the most
    room; the 1.38-second line stops being handed the ceiling."""
    before = distribute_budget(DELIVERED_TENSIONS)
    after = distribute_budget(DELIVERED_TENSIONS, speech_seconds=DELIVERED_SPEECH)

    assert before == [8.0, 10.0, 12.0], "the delivered split, for the record"

    longest_line = DELIVERED_SPEECH.index(max(DELIVERED_SPEECH))
    assert after[longest_line] == max(after), (
        "the scene with the most to say gets the most screen time", after
    )
    assert after[2] < before[2], (
        "the 1.38-second climax gives back some of the silence", after
    )
    assert after[1] > before[1], (
        "and the 4.5-second scene is what it is given to", after
    )


def test_the_total_is_untouched_by_what_the_script_says():
    """The billing invariant. Distribution is open; the total is the number
    the credit was charged against and may not move."""
    for tensions, speech in (
        (DELIVERED_TENSIONS, DELIVERED_SPEECH),
        ([3, 6, 8, 10, 4], [9.0, 0.4, 0.4, 0.4, 0.4]),
        ([5] * 8, [0.0] * 7 + [30.0]),
        ([1, 10], [12.0, 0.5]),
        ([5] * 24, [i * 0.5 for i in range(24)]),
    ):
        without = billable_seconds(distribute_budget(tensions))
        with_speech = billable_seconds(
            distribute_budget(tensions, speech_seconds=speech)
        )
        assert with_speech == without, (tensions, without, with_speech)


def test_every_scene_stays_inside_the_clamps():
    durations = distribute_budget([1, 10, 1, 10, 1], speech_seconds=[11, 0.2, 9, 0.2, 8])
    for seconds in durations:
        assert MIN_SCENE_SECONDS <= seconds <= MAX_SCENE_SECONDS, durations


@pytest.mark.parametrize(
    "speech",
    [(), [], [0.0, 0.0, 0.0], None],
)
def test_a_job_with_no_measured_speech_splits_exactly_as_before(speech):
    """A silent drama, a caption-only fallback, a provider that failed, or a
    caller that never passed speech at all. Every one of them keeps the
    tension-only split byte for byte."""
    kwargs = {} if speech is None else {"speech_seconds": speech}
    assert distribute_budget([3, 6, 8, 10, 4], **kwargs) == distribute_budget(
        [3, 6, 8, 10, 4]
    )


def test_a_quiet_scene_is_still_allowed_to_breathe():
    """The rule only RAISES a scene that cannot fit its line. A short line
    does not shrink a scene to the length of its speech -- pacing is not
    dictation, and a beat with two words in it is still a beat."""
    durations = distribute_budget([5, 5, 5], speech_seconds=[0.5, 0.5, 0.5])
    assert durations == distribute_budget([5, 5, 5]), durations
