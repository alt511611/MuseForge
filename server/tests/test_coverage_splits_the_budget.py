"""A scene covered in two shots is still one scene's worth of film.

interfaces/second_budget fixes each SCENE's length before any provider call,
so a job's cost is known at charge time. _clamp_durations then set every shot
in the scene to that number -- which is right for the single-shot scene the
default ships, and doubles a scene that bought coverage
(MUSEFORGE_SHOTS_PER_SCENE above 1). Measured on a delivered job, coverage of
2 against a 30-second budget:

    scene_0/scene_output.mp4   16.08s   budgeted  8
    scene_1/scene_output.mp4   20.08s   budgeted 10
    scene_2/scene_output.mp4   24.08s   budgeted 12

Exactly double, every scene, and the per-shot trim added by
test_scene_length_is_capped could not catch it: every shot WAS at its stated
length. There were simply two of them, each holding the whole scene's budget,
so the drama charged for 30 seconds ran 60 and the job's own runtime check
failed at the end of a render that had already been paid for.

The prompt had it right all along -- coverage_clause tells the model "their
duration_seconds must SUM to the scene's length" -- and the answer was being
overwritten a moment later.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from interfaces.shot_plan import split_scene_seconds  # noqa: E402


# ── dividing the budget ─────────────────────────────────────────────────────


def test_one_shot_still_carries_the_whole_scene():
    """The default and the overwhelming majority. This path must not move."""
    assert split_scene_seconds(8.0, [5.0]) == [8.0]
    assert split_scene_seconds(12.0, [3.0]) == [12.0]


def test_two_shots_divide_the_scene_rather_than_repeating_it():
    assert split_scene_seconds(8.0, [4.0, 4.0]) == [4.0, 4.0]
    assert sum(split_scene_seconds(10.0, [5.0, 5.0])) == 10.0


def test_the_designer_s_proportions_survive_the_division():
    """A wide that establishes and a close the beat plays in are not the same
    length, and the storyboard is the only party that knows which is which."""
    assert split_scene_seconds(12.0, [3.0, 7.0]) == [4.0, 8.0]


def test_a_scene_with_no_proposed_lengths_is_split_evenly():
    assert split_scene_seconds(12.0, [0.0, 0.0, 0.0]) == [4.0, 4.0, 4.0]


def test_no_shot_is_reduced_to_a_flash_frame():
    """A model that hands one shot nine tenths of the scene leaves the others
    with a few frames each, which is a glitch rather than a cut."""
    shares = split_scene_seconds(12.0, [1.0, 1.0, 20.0])
    assert min(shares) >= 2.0
    assert sum(shares) == 12.0


def test_the_shares_are_whole_seconds_and_sum_to_the_budget():
    """The endpoint is sent an INTEGER duration and the clip is trimmed to the
    same number, so a fractional share would be requested truncated and
    delivered short -- losing the drama a second per shot."""
    for budget in (6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0):
        for proposals in ([5.0, 5.0], [2.0, 9.0], [4.0, 4.0, 4.0], [1.0, 2.0, 3.0]):
            shares = split_scene_seconds(budget, proposals)
            assert all(s == int(s) for s in shares), (budget, proposals, shares)
            assert sum(shares) == int(budget), (budget, proposals, shares)


# ── what the storyboard hands the pipeline ──────────────────────────────────


def _shots(*durations):
    return [
        StoryboardShot(
            idx=i,
            visual_desc=f"shot {i}",
            motion_desc="static",
            duration_seconds=d,
        )
        for i, d in enumerate(durations)
    ]


def test_a_covered_scene_delivers_its_budget_once():
    finished = StoryboardArtist._finish_shots(
        _shots(6.0, 6.0),
        scene_emotion="dread",
        is_finale=False,
        tension=5,
        budget=8.0,
    )
    assert sum(s.duration_seconds for s in finished) == 8.0, (
        "a scene covered in two shots ran twice as long as it was costed at"
    )


def test_a_single_shot_scene_is_set_to_the_budget_exactly_as_before():
    finished = StoryboardArtist._finish_shots(
        _shots(5.0),
        scene_emotion="dread",
        is_finale=False,
        tension=5,
        budget=10.0,
    )
    assert [s.duration_seconds for s in finished] == [10.0]


def test_without_a_budget_the_old_cap_only_behaviour_is_untouched():
    """Legacy callers and single-scene tests pass no budget at all."""
    finished = StoryboardArtist._finish_shots(
        _shots(4.0, 4.0),
        scene_emotion="dread",
        is_finale=False,
        tension=5,
        budget=0.0,
    )
    assert [s.duration_seconds for s in finished] == [4.0, 4.0]


def test_the_reaction_plan_keeps_the_numbers_it_had(monkeypatch):
    """A peak scene that buys a cutaway is planned from the SCENE's budget,
    not from one coverage shot's share of it -- the cutaway replaces that
    coverage, so the master carries the whole scene again."""
    monkeypatch.setenv("MUSEFORGE_REACTION_SHOTS", "1")

    finished = StoryboardArtist._finish_shots(
        _shots(6.0, 6.0),
        scene_emotion="dread",
        is_finale=False,
        tension=9,
        budget=10.0,
    )

    assert [s.role for s in finished] == ["master", "reaction"]
    master, reaction = finished
    assert master.duration_seconds == 10.0  # generated for the whole scene
    assert master.deliver_seconds == 8.0  # and gives up two for the cutaway
    assert reaction.deliver_seconds == 2.0
    delivered = sum(
        s.deliver_seconds or s.duration_seconds for s in finished
    )
    assert delivered == 10.0


# ── and the hit lands on the join ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_impact_pass_finds_the_cut_in_a_covered_scene(monkeypatch, tmp_path):
    """_apply_impact reads the master's DELIVERED length to know where the
    scene cuts. deliver_seconds is only set where generated and delivered
    differ, so a coverage shot -- delivered whole -- reported 0, which reads as
    "no cut in this scene" and skipped the pass on every scene that had one."""
    from pipelines.script2video import Script2VideoPipeline

    planned = {}

    def fake_plan_impacts(cut_seconds, tension=0, duration=0.0):
        planned["cut_at"] = cut_seconds
        return []

    monkeypatch.setattr("pipelines.script2video.plan_impacts", fake_plan_impacts)
    monkeypatch.setattr("pipelines.script2video._probe_duration", lambda p: 8.0)

    clip = tmp_path / "scene_output.mp4"
    clip.write_bytes(b"scene")

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    await pipeline._apply_scene_pacing(
        str(clip),
        working_dir=str(tmp_path),
        director_style="cinematic_balanced",
        scene_tension=9,
        shots=_shots(4.0, 4.0),
    )

    assert planned["cut_at"] == 4.0
