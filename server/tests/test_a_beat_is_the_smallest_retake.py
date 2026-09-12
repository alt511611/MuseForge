"""The smallest thing a director could re-roll was a whole scene.

A scene is covered in several framings, and what a director says is "the
second one, again". Until this existed the two framings that were right went
back in the bin with the one that was not, and came back different.

Everything needed was already written down: every scene's record carries one
entry per beat -- its length, its framing, how many of the scene's lines it
says -- because the pacing, subtitle and lip-sync passes all read it. Read as
a timeline, that record says beat two occupies seconds 4 to 9 of the clip.
"""

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")


def _has_ffmpeg():
    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


def _take_scene(**overrides):
    """A scene shot as one take, cut into three beats."""
    scene = {
        "index": 0,
        "clip_index": 0,
        "take": 1,
        "clip_path": "/tmp/does-not-need-to-exist.mp4",
        "clip_url": "https://cdn/scene0.mp4",
        "script": {"action": "She waits.", "dialogue": []},
        "shots": [
            {
                "index": 0,
                "seconds": 4.0,
                "shot_type": "wide shot",
                "one_take": True,
                "line_count": 1,
                "description": "The harbour, empty, rain on the stone.",
            },
            {
                "index": 1,
                "seconds": 5.0,
                "shot_type": "medium shot",
                "one_take": True,
                "line_count": 1,
                "description": "Vera turns from the rail, the letter in her fist.",
            },
            {
                "index": 2,
                "seconds": 3.0,
                "shot_type": "close-up",
                "one_take": True,
                "line_count": 0,
                "description": "Her face as she reads the last line.",
            },
        ],
    }
    scene.update(overrides)
    return scene


# --- the beat as a window into a clip -------------------------------------


def test_the_beats_lay_end_to_end_across_the_clip():
    from interfaces.beat import windows_of

    windows = windows_of(_take_scene()["shots"])

    assert [(w.start, w.end) for w in windows] == [(0.0, 4.0), (4.0, 9.0), (9.0, 12.0)]
    assert windows[1].shot_type == "medium shot"
    assert windows[1].description.startswith("Vera turns")


def test_a_scene_assembled_from_separate_shots_measures_the_same_way():
    """Two renderers wrote these records: a take's beats carry `seconds`, a
    designed shot carries the storyboard's own duration."""
    from interfaces.beat import windows_of

    windows = windows_of(
        [
            {"duration_seconds": 6.0, "visual_desc": "a door", "shot_type": "wide"},
            {"duration_seconds": 8.0, "deliver_seconds": 6.0, "visual_desc": "a face"},
        ]
    )

    assert [(w.start, w.seconds) for w in windows] == [(0.0, 6.0), (6.0, 6.0)]
    # Delivered, not generated: a master is shot long and cut short (see
    # interfaces/shot_plan), and the clip on disk is the short one.
    assert windows[1].description == "a face"


# --- what cannot be re-shot on its own ------------------------------------


def test_a_scene_that_speaks_for_itself_is_refused_and_told_why():
    """The beat's voice is inside the picture being replaced."""
    from interfaces.beat import refusal

    message = refusal(_take_scene(speaks_for_itself=True), 1)

    assert message and "scene retake" in message.lower()


def test_a_lip_synced_scene_is_refused():
    """The sync drove the mouth across the clip it was given, and the new beat
    was never in that clip."""
    from interfaces.beat import refusal

    message = refusal(_take_scene(), 1, lipsynced_scenes=[0])

    assert message and "mouth" in message.lower()
    # ...and the same scene is fine when the sync did not touch it.
    assert refusal(_take_scene(), 1, lipsynced_scenes=[3]) is None


def test_a_single_shot_scene_is_told_to_use_the_scene_retake():
    from interfaces.beat import refusal

    scene = _take_scene()
    scene["shots"] = scene["shots"][:1]

    message = refusal(scene, 0)

    assert message and "single shot" in message


def test_a_beat_that_does_not_exist_is_refused_by_number():
    from interfaces.beat import refusal

    assert "shot 9" in refusal(_take_scene(), 8)


def test_a_beat_with_no_record_of_what_it_was_shot_from_is_refused():
    """It could only be re-designed, and a re-designed beat is a different
    picture in a different framing."""
    from interfaces.beat import refusal

    scene = _take_scene()
    scene["shots"][1]["description"] = ""

    assert "re-designed" in refusal(scene, 1)


def test_a_scene_whose_clip_is_gone_is_refused():
    """A beat retake keeps the rest of that clip, so it needs the clip."""
    from interfaces.beat import refusal

    scene = _take_scene()
    scene.pop("clip_path")
    scene.pop("clip_url")

    assert "no longer stored" in refusal(scene, 1)


def test_a_beat_that_can_be_re_shot_is_not_refused():
    from interfaces.beat import refusal

    assert refusal(_take_scene(), 1) is None


# --- the record the retake leaves behind ----------------------------------


def test_the_new_beat_inherits_its_place_in_the_scene():
    """Its index, its length and its share of the lines did not change: the
    same beat was shot again, into the same window. The subtitle and reframing
    passes read exactly those fields."""
    from interfaces.beat import replace

    shots = _take_scene()["shots"]
    updated = replace(shots, 1, {"video_url": "https://cdn/new.mp4", "seconds": 99})

    assert updated[1]["seconds"] == 5.0
    assert updated[1]["line_count"] == 1
    assert updated[1]["index"] == 1
    assert updated[1]["video_url"] == "https://cdn/new.mp4"
    assert updated[0] == shots[0] and updated[2] == shots[2]


def test_the_scene_stops_claiming_to_be_one_unbroken_take():
    """Whatever it started as, it has now been cut into. The passes that ask
    are deciding whether the picture can be cut again."""
    from interfaces.beat import replace

    updated = replace(_take_scene()["shots"], 1, {"video_url": "https://cdn/new.mp4"})

    assert updated[1]["one_take"] is False
    assert updated[1]["retaken"] == 1


# --- the shot that is sent back to the model ------------------------------


def test_the_retake_shoots_the_same_beat_rather_than_designing_a_new_one():
    from interfaces.beat import windows_of
    from pipelines.idea2video import _beat_storyboard

    shots = _take_scene()["shots"]
    window = windows_of(shots)[1]

    shot = _beat_storyboard(shots[1], window)

    assert shot.visual_desc == shots[1]["description"]
    assert shot.shot_type == "medium shot"
    assert shot.duration_seconds == 5.0
    assert shot.role == "master"


# --- the pipeline -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_refused_beat_never_reaches_a_generator(tmp_path):
    from unittest.mock import AsyncMock

    from pipelines.idea2video import Idea2VideoPipeline, SceneRegenerationUnavailable

    pipeline = Idea2VideoPipeline("test-key", demo=True)
    pipeline._rerender_scenes = AsyncMock()

    with pytest.raises(SceneRegenerationUnavailable) as exc:
        await pipeline.regenerate_beat(
            previous_result={"scenes": [_take_scene(speaks_for_itself=True)]},
            scene_index=0,
            beat_index=1,
            working_dir=str(tmp_path),
        )

    assert "speaks for itself" in str(exc.value)
    pipeline._rerender_scenes.assert_not_awaited()


@pytest.mark.asyncio
async def test_only_the_named_beat_is_generated(tmp_path):
    """The whole point: one generation, the beat's own brief, the beat's own
    slice of the second budget."""
    from unittest.mock import AsyncMock

    from pipelines.idea2video import Idea2VideoPipeline

    clip = tmp_path / "scene0.mp4"
    clip.write_bytes(b"not really a video")
    scene = _take_scene(clip_path=str(clip))

    previous = {
        "scenes": [scene],
        "video_url": "https://cdn/master.mp4",
        "characters": [{"name": "Vera", "description": "40s, grey coat"}],
        "_render_state": {
            "script": {
                "title": "Harbour",
                "logline": "A letter arrives.",
                "scenes": [{"action": "She waits.", "dialogue": []}],
                "characters": [{"name": "Vera", "description": "40s, grey coat"}],
            },
            "scene_durations": [12.0],
        },
    }

    pipeline = Idea2VideoPipeline("test-key", demo=True)
    seen = {}

    async def fake_run(**kwargs):
        seen.update(kwargs)
        return {"path": str(tmp_path / "beat.mp4"), "shots": [{"video_url": "https://cdn/b.mp4"}]}

    pipeline.script2video.run = AsyncMock(side_effect=fake_run)
    pipeline._splice_beat_into_scene = AsyncMock(
        side_effect=lambda scene, window, rendered, scene_dir: {
            "path": str(clip),
            "shots": scene["shots"],
        }
    )
    pipeline._assemble_final_drama = AsyncMock(return_value=str(clip))
    pipeline._publish_master = AsyncMock()

    await pipeline.regenerate_beat(
        previous_result=previous,
        scene_index=0,
        beat_index=1,
        working_dir=str(tmp_path / "job"),
        director_note="hold on her hands",
    )

    override = seen["storyboard_override"]
    assert len(override) == 1, "a beat retake buys one generation"
    assert override[0].visual_desc == scene["shots"][1]["description"]
    assert seen["scene_duration"] == 5.0
    # The note is a direction, not a redesign: it rides the binding
    # requirement line, and the beat's own brief is untouched.
    assert "hold on her hands" in seen["user_requirement"]


@pytest.mark.asyncio
async def test_the_beat_is_spliced_into_the_take_at_its_own_window(tmp_path):
    from unittest.mock import AsyncMock

    from pipelines.idea2video import Idea2VideoPipeline

    clip = tmp_path / "scene0.mp4"
    clip.write_bytes(b"x")
    scene = _take_scene(clip_path=str(clip))
    previous = {
        "scenes": [scene],
        "video_url": "https://cdn/master.mp4",
        "_render_state": {
            "script": {
                "title": "Harbour",
                "logline": "A letter arrives.",
                "scenes": [{"action": "She waits.", "dialogue": []}],
                "characters": [{"name": "Vera", "description": "40s"}],
            },
        },
    }

    pipeline = Idea2VideoPipeline("test-key", demo=True)
    pipeline.script2video.run = AsyncMock(
        return_value={"path": str(tmp_path / "beat.mp4"), "shots": [{"video_url": "u"}]}
    )
    windows = {}

    async def fake_splice(scene, window, rendered, scene_dir):
        windows["window"] = window
        return {"path": str(clip), "shots": scene["shots"]}

    pipeline._splice_beat_into_scene = AsyncMock(side_effect=fake_splice)
    pipeline._assemble_final_drama = AsyncMock(return_value=str(clip))
    pipeline._publish_master = AsyncMock()

    await pipeline.regenerate_beat(
        previous_result=previous,
        scene_index=0,
        beat_index=2,
        working_dir=str(tmp_path / "job"),
    )

    assert (windows["window"].start, windows["window"].end) == (9.0, 12.0)


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
@pytest.mark.asyncio
async def test_the_rebuilt_scene_keeps_the_length_it_was_paid_for(tmp_path):
    """End to end through the real cuts: head, new beat, tail."""
    from moviepy import ColorClip, VideoFileClip

    from interfaces.beat import windows_of
    from pipelines.idea2video import Idea2VideoPipeline

    def _clip(name, seconds, colour):
        path = str(tmp_path / name)
        made = ColorClip(size=(160, 90), color=colour, duration=seconds)
        made.write_videofile(path, fps=12, codec="libx264", audio=False, logger=None)
        made.close()
        return path

    scene_clip = _clip("scene.mp4", 12.0, (20, 20, 60))
    # The provider handed back more than it was asked for, as they do.
    new_beat = _clip("beat.mp4", 8.0, (120, 20, 20))

    scene = _take_scene(clip_path=scene_clip)
    pipeline = Idea2VideoPipeline("test-key", demo=True)

    spliced = await pipeline._splice_beat_into_scene(
        scene,
        windows_of(scene["shots"])[1],
        {"path": new_beat, "shots": [{"video_url": "https://cdn/new.mp4"}]},
        str(tmp_path / "take2"),
    )

    with VideoFileClip(spliced["path"]) as result:
        assert abs(result.duration - 12.0) < 0.75, (
            "the scene may not grow: a beat generated long is delivered at the "
            "window it replaces, or every subtitle after it drifts"
        )
    assert spliced["shots"][1]["video_url"] == "https://cdn/new.mp4"


# --- the endpoint -----------------------------------------------------------


def test_the_endpoint_refuses_with_the_reason_and_points_at_the_scene_retake():
    os.environ["MUSEFORGE_DEMO"] = "1"
    from fastapi.testclient import TestClient

    import api
    from jobs import Job, JobStatus, job_store

    job = Job(id="beat-test-1", demo=True, status=JobStatus.COMPLETED)
    job.result = {"scenes": [_take_scene(speaks_for_itself=True)], "video_url": "u"}
    job_store._jobs[job.id] = job

    client = TestClient(api.app)
    resp = client.post(
        "/api/jobs/beat-test-1/scenes/0/shots/1/retake", json={"director_note": ""}
    )

    assert resp.status_code == 400
    assert "speaks for itself" in resp.json()["detail"]
    assert resp.headers.get("X-Retake-Scope") == "scene"
