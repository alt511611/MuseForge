"""A scene's angles have to differ from each other, not just from the scene before.

plan_shot_scales decides one framing per SCENE so that no two consecutive
scenes repeat a setup. On a deployment that buys coverage
(MUSEFORGE_SHOTS_PER_SCENE > 1) that single scale was then handed to the shot
designer as "Set shot_type to exactly this" -- applied to every angle in the
scene -- while coverage_clause, in the SYSTEM prompt of the very same call,
asked for angles that differ:

    coverage_clause:     "Make them DIFFERENT shots: change the shot_type and
                          the angle between them ... Two shots of the same
                          size from the same angle are one shot with a join
                          in it."
    _format_scale_line:  "FRAMING FOR THIS SCENE — BINDING: {scale}. ... Set
                          shot_type to exactly this, and compose for it."

Two binding instructions, opposite answers, and only one of them said BINDING.

Delivered job 82e03154-12c, brief "A dock worker on a rain-soaked cargo
harbour ...": three scenes, two angles each, and all six frames are the same
frontal medium of the same woman. The between-scene plan had asked for
wide → medium → close-up and none of it reached the screen; the climax cuts
from her standing in a corridor to her standing in a corridor.

The watchdog could not see it either. _note_scale_drift read shots[0] and
nothing else, so a scene whose every angle had collapsed onto the planned
scale looked like perfect compliance.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import (  # noqa: E402
    StoryboardArtist,
    coverage_clause,
)
from interfaces.shot import StoryboardShot  # noqa: E402
from interfaces.shot_plan import (  # noqa: E402
    SCALE_LADDER,
    coverage_scales,
    plan_shot_scales,
)


#: The delivered job's three scenes, as the screenwriter wrote them.
DELIVERED_SCENES = [
    {"dramatic_function": "setup", "tension": 4},
    {"dramatic_function": "turning_point", "tension": 7},
    {"dramatic_function": "climax", "tension": 9},
]


# ── the ladder inside one scene ─────────────────────────────────────────────


def test_a_second_angle_is_never_the_same_size_as_the_first():
    for opening in SCALE_LADDER:
        first, second = coverage_scales(opening, 2)
        assert first == opening
        assert second != first, opening


def test_coverage_steps_tighter_the_way_the_instruction_describes():
    """"A wide that establishes, then the closer framing the beat actually
    plays in" -- coverage_clause's own words, now computed."""
    assert coverage_scales("wide shot", 2) == ["wide shot", "medium shot"]
    assert coverage_scales("medium shot", 2) == ["medium shot", "close-up"]
    assert coverage_scales("medium shot", 3) == [
        "medium shot", "close-up", "extreme close-up",
    ]


def test_at_the_tight_end_it_turns_round_instead_of_running_out():
    assert coverage_scales("extreme close-up", 2) == [
        "extreme close-up", "close-up",
    ]


def test_no_two_angles_in_a_row_repeat_however_deep_the_coverage():
    for opening in SCALE_LADDER:
        for count in range(1, 7):
            scales = coverage_scales(opening, count)
            assert len(scales) <= count
            pairs = list(zip(scales, scales[1:]))
            assert all(a != b for a, b in pairs), (opening, count, scales)


def test_a_single_angle_scene_is_left_exactly_as_it_was():
    """The default and the overwhelming majority: one shot, the planned
    scale, nothing to vary."""
    assert coverage_scales("medium shot", 1) == ["medium shot"]


def test_a_framing_the_ladder_does_not_name_is_not_guessed_at():
    assert coverage_scales("dutch angle", 2) == []
    assert coverage_scales("", 2) == []
    assert coverage_scales("medium shot", 0) == []


def test_the_delivered_job_would_have_had_six_framings_not_one():
    """The whole point, measured on the film that prompted this: an
    escalation the audience can see, ending on the tightest frame of the
    drama rather than a sixth medium."""
    planned = plan_shot_scales(DELIVERED_SCENES)
    assert planned == ["wide shot", "medium shot", "close-up"]

    covered = [coverage_scales(scale, 2) for scale in planned]
    assert covered == [
        ["wide shot", "medium shot"],
        ["medium shot", "close-up"],
        ["close-up", "extreme close-up"],
    ]
    # Six framings where the delivered film had one size six times.
    flat = [scale for scene in covered for scale in scene]
    assert len(set(flat)) == 4


def test_the_repeat_that_is_left_is_the_one_across_a_scene_cut():
    """Stated rather than left to be discovered. plan_shot_scales guarantees
    consecutive scenes do not OPEN on the same size, and coverage now steps
    tighter from there -- so a scene can end on the size the next one opens
    with (medium | medium, close-up | close-up above).

    Not the same fault, and deliberately not chased. Inside a scene the place,
    the light and the staging are identical, so the size is the only thing a
    cut can change and repeating it is literally "one shot with a join in it".
    Across a scene cut everything else has already changed; a matched size
    there is a match cut, which is a technique.
    """
    covered = [
        coverage_scales(scale, 2) for scale in plan_shot_scales(DELIVERED_SCENES)
    ]
    for scene in covered:
        assert scene[0] != scene[1]

    joins = [(a[-1], b[0]) for a, b in zip(covered, covered[1:])]
    assert joins == [("medium shot", "medium shot"), ("close-up", "close-up")]


# ── what the designer is actually told ──────────────────────────────────────


@pytest.fixture
def coverage_on(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_SHOTS_PER_SCENE", "2")


@pytest.fixture
def coverage_off(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_SHOTS_PER_SCENE", "1")


def test_the_two_clauses_no_longer_contradict_each_other(coverage_on):
    """coverage_clause asks for angles that differ. The framing line used to
    answer "set shot_type to exactly this" to all of them."""
    system = coverage_clause(2)
    user = StoryboardArtist._format_scale_line("medium shot")

    assert "DIFFERENT shots" in system
    assert 'shot 1: "medium shot"' in user
    assert 'shot 2: "close-up"' in user
    assert "exactly this" not in user


def test_the_scene_still_opens_on_the_scale_the_drama_planned(coverage_on):
    """The between-scene guarantee is the part that cannot be decided locally,
    so it is the part that still binds."""
    user = StoryboardArtist._format_scale_line("close-up")
    assert "OPENS on close-up" in user
    assert 'shot 2: "extreme close-up"' in user


def test_a_single_shot_deployment_gets_the_wording_it_always_got(coverage_off):
    user = StoryboardArtist._format_scale_line("medium shot")
    assert "FRAMING FOR THIS SCENE — BINDING: medium shot." in user
    assert 'Set "shot_type" to exactly this' in user
    assert "shot 2" not in user


def test_no_plan_means_no_clause(coverage_on):
    assert StoryboardArtist._format_scale_line("") == ""


# ── the watchdog that could not see it ──────────────────────────────────────


def _shots(*sizes):
    return [
        StoryboardShot(
            idx=i, visual_desc="v", motion_desc="m", shot_type=size,
        )
        for i, size in enumerate(sizes)
    ]


def test_a_scene_whose_angles_all_collapsed_is_reported(caplog):
    """The delivered shape. Every angle matches the planned scale, which is
    precisely the collapse -- so it cannot be caught by comparing against the
    plan, and shots[0] alone can never see it."""
    with caplog.at_level("WARNING"):
        StoryboardArtist._note_scale_drift(
            _shots("medium shot", "medium shot"), "medium shot"
        )
    assert any(
        "one shot with a join in it" in r.getMessage() for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


def test_a_scene_that_was_actually_covered_is_not_reported(caplog):
    with caplog.at_level("WARNING"):
        StoryboardArtist._note_scale_drift(
            _shots("medium shot", "close-up"), "medium shot"
        )
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_wording_is_not_mistaken_for_a_second_size(caplog):
    """"medium" and "medium shot" are the same framing -- the same reason
    _normalised_scale exists for the drift check below it."""
    with caplog.at_level("WARNING"):
        StoryboardArtist._note_scale_drift(
            _shots("medium", "medium shot"), "medium shot"
        )
    assert any(
        "one shot with a join in it" in r.getMessage() for r in caplog.records
    )


def test_a_single_angle_scene_is_never_reported(caplog):
    with caplog.at_level("WARNING"):
        StoryboardArtist._note_scale_drift(_shots("medium shot"), "medium shot")
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_the_original_drift_notice_still_fires(caplog):
    with caplog.at_level("INFO"):
        StoryboardArtist._note_scale_drift(
            _shots("wide shot", "medium shot"), "close-up"
        )
    assert any(
        "over the planned" in r.getMessage() for r in caplog.records
    ), [r.getMessage() for r in caplog.records]
