"""Two angles on the scene that earns one: allocation, trimming, routing.

The rule this file exists to protect is arithmetic, and it is the same rule
the whole product rests on: **the scene delivers exactly the seconds the
credit bought**. Buying a second angle changes what those seconds contain, not
how many there are. A plan whose parts do not add back up to the budget either
short-changes the customer or bills the operator for film nobody sees.

The second rule is economic and less obvious: under MuAPI's flat
per-generation billing, asking for a SHORTER master saves nothing. So the
master's request never shrinks -- only its delivered length does.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces import shot_plan  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from interfaces.shot_plan import (  # noqa: E402
    MASTER,
    REACTION,
    REACTION_SECONDS,
    REACTION_TENSION,
    delivered_seconds,
    plan_scene_shots,
)
from tools import video_model_router as router  # noqa: E402


@pytest.fixture
def reactions_on(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_REACTION_SHOTS", "1")


def _shot(**overrides):
    base = dict(
        idx=0,
        visual_desc="Ayse faces Kemal across the table",
        motion_desc="slow push-in",
        expression_desc="jaw tight",
        expression_peak_desc="the jaw setting hard",
        shot_type="medium shot",
        camera_movement="static",
        lens="35mm",
        duration_seconds=10.0,
    )
    base.update(overrides)
    return StoryboardShot(**base)


def _cast():
    return [
        CharacterInScene(idx=0, name="Ayse", static_features="50s woman"),
        CharacterInScene(idx=1, name="Kemal", static_features="30s man"),
    ]


# --- when a scene earns a second angle ---------------------------------


def test_reaction_shots_are_off_by_default(monkeypatch):
    """It is a business decision, not a default: ~$0.34 a scene."""
    monkeypatch.delenv("MUSEFORGE_REACTION_SHOTS", raising=False)
    plan = plan_scene_shots(10.0, tension=10)
    assert [p.role for p in plan] == [MASTER]
    assert plan[0].deliver_seconds == 0.0  # nothing trimmed, nothing changed


def test_only_peak_scenes_get_one(reactions_on):
    assert [p.role for p in plan_scene_shots(10.0, tension=REACTION_TENSION - 1)] == [
        MASTER
    ]
    assert [p.role for p in plan_scene_shots(10.0, tension=REACTION_TENSION)] == [
        MASTER,
        REACTION,
    ]


def test_lipsync_scenes_keep_a_single_take(reactions_on):
    """The lip-sync pass drives a mouth across the whole scene clip and cannot
    see a cut inside it. A desynced mouth is worse than a missing angle."""
    plan = plan_scene_shots(10.0, tension=10, lipsync_enabled=True)
    assert [p.role for p in plan] == [MASTER]


def test_a_scene_too_short_for_two_beats_keeps_one(reactions_on):
    """A guard rather than a live path: interfaces/second_budget floors a
    scene at 6 seconds, which still leaves a 4-second master. Below that the
    master would stop being a shot."""
    plan = plan_scene_shots(5.0, tension=10)
    assert [p.role for p in plan] == [MASTER]

    # And at the real floor it does buy the angle: 6s = 4s master + 2s cutaway.
    at_floor = plan_scene_shots(6.0, tension=10)
    assert [p.role for p in at_floor] == [MASTER, REACTION]
    assert at_floor[0].deliver_seconds == 4.0


# --- the arithmetic ----------------------------------------------------


@pytest.mark.parametrize("budget", [6.0, 7.0, 8.0, 10.0, 12.0])
@pytest.mark.parametrize("tension", [1, 5, 8, 10])
def test_the_plan_always_delivers_the_whole_budget(reactions_on, budget, tension):
    """Whatever it decides, the scene is the length the credit bought."""
    plan = plan_scene_shots(budget, tension=tension)
    assert delivered_seconds(plan) == pytest.approx(budget)


def test_the_master_is_never_asked_for_less(reactions_on):
    """Flat billing: a shorter request costs the same and buys less film.

    This is the mistake the design review caught -- shortening the master to
    'make room' declines video already paid for.
    """
    budget = 10.0
    solo = plan_scene_shots(budget, tension=1)[0]
    master = plan_scene_shots(budget, tension=10)[0]
    assert master.generate_seconds == solo.generate_seconds == budget
    # Only what reaches the timeline moves.
    assert master.deliver_seconds == budget - REACTION_SECONDS


def test_the_master_keeps_its_ending(reactions_on):
    """The last frame is where the acted peak lands, so the head is dropped."""
    master, reaction = plan_scene_shots(10.0, tension=10)
    assert master.trim_from_head is True
    assert reaction.trim_from_head is True


def test_the_cutaway_asks_for_what_its_endpoint_actually_returns(reactions_on):
    """veo3.1-lite's duration is the enum [8]; the clip is trimmed, not asked
    to be short."""
    _, reaction = plan_scene_shots(10.0, tension=10)
    assert reaction.generate_seconds == 8.0
    assert reaction.deliver_seconds == REACTION_SECONDS
    assert router.fixed_duration(router.DEFAULT_REACTION_MODEL) == 8


# --- routing -----------------------------------------------------------


def test_the_cutaway_is_not_bought_at_the_masters_price():
    """Routing a 2-second face to Kling costs $0.72 -- the price of the whole
    scene, for a fraction of the film."""
    from tools.muapi_video_generator import STANDARD_ENDPOINT

    assert router.configured_model(router.REACTION) == "veo3.1-lite-image-to-video"
    assert router.DEFAULT_REACTION_MODEL != STANDARD_ENDPOINT


def test_an_operator_can_still_override_the_reaction_model(monkeypatch):
    monkeypatch.setenv("MUAPI_VIDEO_MODEL_REACTION", "ovi-image-to-video")
    assert router.configured_model(router.REACTION) == "ovi-image-to-video"


def test_the_reaction_endpoint_can_carry_the_acted_peak():
    """The other cheap option (turbo) takes neither a flat price nor an end
    frame; this one takes both."""
    assert "last_image" in router.optional_fields(router.DEFAULT_REACTION_MODEL)
    assert "last_image" not in router.optional_fields(
        "kling-v3-turbo-standard-image-to-video"
    )


def test_the_chain_still_ends_somewhere_that_always_exists():
    chain = router.model_chain(router.REACTION, plan="free")
    assert chain[0] == router.DEFAULT_REACTION_MODEL
    from tools.muapi_video_generator import STANDARD_ENDPOINT

    assert chain[-1] == STANDARD_ENDPOINT


def test_no_routing_env_still_reads_as_unconfigured(monkeypatch):
    """The reaction default is a built-in, not an operator's choice, and the
    log line that distinguishes them must not start lying."""
    for env in (
        "MUAPI_VIDEO_MODEL_ACTION",
        "MUAPI_VIDEO_MODEL_DIALOGUE",
        "MUAPI_VIDEO_MODEL_ESTABLISHING",
        "MUAPI_VIDEO_MODEL_REACTION",
    ):
        monkeypatch.delenv(env, raising=False)
    assert router.is_routing_active() is False


# --- what the cutaway actually shows -----------------------------------


def test_the_cutaway_is_on_the_other_face(reactions_on):
    """A reaction shot is the person LISTENING. Naming them in visual_desc is
    also what makes the frame step reach for the right locked portrait."""
    shots = StoryboardArtist._apply_shot_plan(
        [_shot(visual_desc="Ayse leans across the table at Kemal")],
        "cold rage",
        tension=10,
        characters=_cast(),
    )
    assert len(shots) == 2
    assert "Kemal" in shots[1].visual_desc
    assert shots[1].role == REACTION


def test_a_one_hander_cuts_tighter_on_the_same_face(reactions_on):
    shots = StoryboardArtist._apply_shot_plan(
        [_shot(visual_desc="Ayse alone at the table")],
        "cold rage",
        tension=10,
        characters=[CharacterInScene(idx=0, name="Ayse", static_features="50s woman")],
    )
    assert len(shots) == 2
    assert "Ayse" in shots[1].visual_desc
    assert "close-up" in shots[1].shot_type


def test_the_cutaway_holds_still_and_carries_the_beat(reactions_on):
    shots = StoryboardArtist._apply_shot_plan(
        [_shot()], "cold rage", tension=10, characters=_cast()
    )
    reaction = shots[1]
    assert reaction.camera_movement == "static"
    assert reaction.lens != shots[0].lens  # a different lens, visibly
    assert reaction.expression_peak_desc == shots[0].expression_peak_desc


def test_the_cutaway_is_deterministic(reactions_on):
    """Same scene, same second angle -- a retake must not re-cut the film."""
    first = StoryboardArtist._apply_shot_plan(
        [_shot()], "cold rage", tension=10, characters=_cast()
    )
    second = StoryboardArtist._apply_shot_plan(
        [_shot()], "cold rage", tension=10, characters=_cast()
    )
    assert first[1].visual_desc == second[1].visual_desc


def test_a_quiet_scene_is_left_exactly_as_it_was(reactions_on):
    shots = StoryboardArtist._apply_shot_plan(
        [_shot()], "quiet resignation", tension=3, characters=_cast()
    )
    assert len(shots) == 1
    assert shots[0].deliver_seconds == 0.0


# --- against a real encoder --------------------------------------------


def _has_ffmpeg():
    import shutil

    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.asyncio
@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
async def test_master_plus_cutaway_assembles_to_the_budget(tmp_path):
    """The whole point, measured on real files: a 10-second scene generated as
    a 10s master and an 8s cutaway comes out as a 10-second scene."""
    import subprocess

    from pipelines.script2video import (
        _probe_duration,
        _resolve_ffmpeg_binary,
        concatenate_videos,
        trim_to_duration,
    )

    ff = _resolve_ffmpeg_binary()

    def _clip(name, seconds, pattern):
        path = str(tmp_path / name)
        subprocess.run(
            [ff, "-y", "-f", "lavfi", "-i",
             f"{pattern}=size=320x180:rate=24:duration={seconds}",
             "-pix_fmt", "yuv420p", path],
            check=True, capture_output=True,
        )
        return path

    master = _clip("master.mp4", 10, "testsrc")
    cutaway = _clip("cutaway.mp4", 8, "smptebars")

    plan = shot_plan.plan_scene_shots(10.0, tension=10)
    # Force the plan regardless of the env flag: this test is about the
    # arithmetic of assembly, not about whether the feature is switched on.
    if len(plan) < 2:
        plan = [
            shot_plan.PlannedShot(shot_plan.MASTER, 10.0, 8.0),
            shot_plan.PlannedShot(shot_plan.REACTION, 8.0, 2.0),
        ]

    trimmed = []
    for source, planned in zip((master, cutaway), plan):
        out = await trim_to_duration(
            source, str(tmp_path / f"{planned.role}_cut.mp4"), planned.deliver_seconds
        )
        trimmed.append(out)
        assert _probe_duration(out) == pytest.approx(
            planned.deliver_seconds, abs=1 / 24 + 0.05
        )

    scene = str(tmp_path / "scene.mp4")
    await concatenate_videos(trimmed, scene)
    assert _probe_duration(scene) == pytest.approx(10.0, abs=0.2)


@pytest.mark.asyncio
@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
async def test_trimming_keeps_the_end_where_the_performance_lands(tmp_path):
    """Head-trimming is a directing decision: the peak is in the final frame.

    Proved by RELATIVE brightness rather than by an absolute tolerance. The
    source ramps from black to white over eight seconds, so "which two seconds
    survived" is not a judgement call: a kept tail is much brighter than the
    head it replaced, by a margin no encoder rounding can cross.
    """
    import subprocess

    from moviepy import VideoFileClip

    from pipelines.script2video import _resolve_ffmpeg_binary, trim_to_duration

    ff = _resolve_ffmpeg_binary()
    source = str(tmp_path / "ramp.mp4")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "color=c=white:s=320x180:r=24:d=8",
         "-vf", "fade=t=in:st=0:d=8", "-pix_fmt", "yuv420p", source],
        check=True, capture_output=True,
    )

    def _mean(clip, start, end):
        frames = [clip.get_frame(t).mean() for t in (start, (start + end) / 2, end)]
        return sum(frames) / len(frames)

    with VideoFileClip(source) as clip:
        head = _mean(clip, 0.1, 1.9)
        tail = _mean(clip, 6.1, 7.9)
    assert tail > head + 50, "fixture is not a ramp; the test proves nothing"

    out = await trim_to_duration(source, str(tmp_path / "tail.mp4"), 2.0)
    with VideoFileClip(out) as trimmed:
        assert trimmed.duration == pytest.approx(2.0, abs=0.15)
        kept = _mean(trimmed, 0.1, trimmed.duration - 0.1)

    # Nearer the source's ending than its opening, and not marginally.
    assert abs(kept - tail) < abs(kept - head)
    assert kept > (head + tail) / 2


# --- framing across the drama, not inside one scene ---------------------
#
# Measured on a delivered 30-second drama: its first two scenes were the same
# framing of the same two people -- eighteen seconds of one setup. Neither
# shot was wrong on its own, which is the point. Repetition is only visible
# from OUTSIDE a scene, and scenes are designed independently and in parallel,
# so no part of the pipeline was standing there.


def _scenes(*pairs):
    return [{"dramatic_function": f, "tension": t} for f, t in pairs]


def test_no_two_scenes_in_a_row_share_a_setup():
    scales = shot_plan.plan_shot_scales(
        _scenes(("setup", 3), ("setup", 2), ("rising_action", 6),
                ("climax", 10), ("resolution", 3))
    )
    assert all(a != b for a, b in zip(scales, scales[1:])), scales


def test_the_climax_is_where_the_face_is():
    scales = shot_plan.plan_shot_scales(
        _scenes(("setup", 3), ("rising_action", 6), ("climax", 10))
    )
    assert scales == ["wide shot", "medium shot", "close-up"]


def test_a_collision_tightens_when_the_drama_escalates():
    """Cutting tighter as it escalates is what escalation looks like -- the
    tie-break is grammar, not a coin toss."""
    scales = shot_plan.plan_shot_scales(_scenes(("climax", 9), ("climax", 10)))
    assert scales == ["close-up", "extreme close-up"]


def test_a_collision_widens_when_it_settles():
    scales = shot_plan.plan_shot_scales(_scenes(("setup", 4), ("resolution", 2)))
    assert scales[0] == "wide shot"
    assert scales[1] == "medium shot"  # nowhere wider to go, so it steps in


def test_every_scale_is_on_the_ladder():
    scales = shot_plan.plan_shot_scales(
        _scenes(*[("rising_action", t) for t in range(1, 11)])
    )
    assert all(s in shot_plan.SCALE_LADDER for s in scales)


def test_a_script_with_no_scenes_plans_nothing():
    assert shot_plan.plan_shot_scales([]) == []
    assert shot_plan.plan_shot_scales(None) == []


def test_it_reads_pydantic_scenes_too():
    from interfaces.character import ScriptScene

    scales = shot_plan.plan_shot_scales(
        [
            ScriptScene(action="a", dialogue=[], dramatic_function="setup", tension=3),
            ScriptScene(action="b", dialogue=[], dramatic_function="climax", tension=10),
        ]
    )
    assert scales == ["wide shot", "close-up"]


# --- and it reaches the shot designer -----------------------------------


def test_the_framing_reaches_the_prompt_as_binding():
    line = StoryboardArtist._format_scale_line("extreme close-up")
    assert "BINDING" in line
    assert "extreme close-up" in line
    assert "consecutive" in line


def test_no_plan_adds_nothing_to_the_prompt():
    assert StoryboardArtist._format_scale_line("") == ""


@pytest.mark.asyncio
async def test_the_deterministic_fallback_honours_the_plan_too():
    """Demo mode and every key-less run go through the template. One that
    hardcodes "medium shot" puts the defect back in the only mode where no
    model can be blamed for it."""
    artist = StoryboardArtist(api_key="", demo=True)
    shots = await artist.design_storyboard(
        script="She opens it.",
        characters=[CharacterInScene(idx=0, name="Mira", static_features="30s woman")],
        scene_shot_scale="extreme close-up",
    )
    assert shots[0].shot_type == "extreme close-up"


def test_a_designer_that_ignores_the_plan_is_logged_not_overridden(caplog):
    """The brief outranks the plan and only the agent has read it, so drift is
    made visible rather than silently rewritten."""
    import logging

    shots = [_shot(shot_type="wide shot")]
    with caplog.at_level(logging.INFO):
        StoryboardArtist._note_scale_drift(shots, "close-up")
    assert shots[0].shot_type == "wide shot"
    assert "over the planned" in caplog.text
