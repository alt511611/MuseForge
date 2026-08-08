"""Single-scene retakes.

Re-running a whole job to fix one bad scene re-rolls the scenes the user was
happy with and charges for all of them. A retake re-renders exactly one scene
and splices it back into the finished master.

The invariants that matter:
  * only the chosen scene hits a generator
  * the retake gets the SAME slice of the second budget (a retake must not
    quietly change the runtime the customer paid for)
  * the director's note actually reaches the shot brief
  * a failed retake leaves the customer with the video they already had
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as idea2video_mod  # noqa: E402
from pipelines.idea2video import SceneRegenerationUnavailable  # noqa: E402


def _script_dict():
    return {
        "title": "Meridyen",
        "logline": "A coffee master hands down his craft.",
        "mood": "warm",
        "estimated_duration_seconds": 24,
        "setting_location": "stone-walled coffeehouse",
        "setting_time_of_day": "early morning",
        "characters": [
            {"name": "Kemal", "description": "70s man, white moustache", "role": "protagonist"}
        ],
        "scenes": [
            {"action": "Kemal lights the stove.", "tension": 3},
            {"action": "Kemal pours the coffee.", "tension": 7},
            {"action": "Deniz takes the first sip.", "tension": 5},
        ],
    }


def _previous_result(tmp_path, with_state=True):
    clips = []
    for i in range(3):
        p = str(tmp_path / f"orig_scene_{i}.mp4")
        with open(p, "wb") as f:
            f.write(f"original scene {i}".encode())
        clips.append(p)

    result = {
        "title": "Meridyen",
        "style": "Cinematic",
        "director_style": "intimate_closeup",
        "aspect_ratio": "16:9",
        "plan": "pro",
        "portraits": {"Kemal": "https://cdn/kemal.png"},
        "location_plate": "https://cdn/set_plate.png",
        "video_url": "https://cdn/original_master.mp4",
        "duration_estimate": 24,
        "scenes": [
            {"index": i, "script": _script_dict()["scenes"][i], "shots": [], "clip_index": i,
             "clip_path": clips[i]}
            for i in range(3)
        ],
    }
    if with_state:
        result["_render_state"] = {
            "script": _script_dict(),
            "scene_durations": [6.0, 10.0, 8.0],
            "music_url": "https://cdn/music.mp3",
            "user_requirement": "Keep it warm and unhurried.",
            "dialogue_tracks": [],
        }
    return result


async def _regenerate(monkeypatch, tmp_path, scene_index=1, note="", run_fails=False,
                      with_state=True, previous=None):
    run_calls = []
    assembled = {}

    async def fake_run(self, **kwargs):
        run_calls.append(kwargs)
        if run_fails:
            raise RuntimeError("provider exploded")
        path = os.path.join(kwargs["working_dir"], "scene.mp4")
        os.makedirs(kwargs["working_dir"], exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"brand new take")
        return {"path": path, "shots": [{"idx": 0, "video_url": "https://cdn/new.mp4"}]}

    async def fake_assemble(self, scene_paths, working_dir, *a, **kw):
        assembled["scene_paths"] = list(scene_paths)
        out = os.path.join(working_dir, "master.mp4")
        with open(out, "wb") as f:
            f.write(b"new master")
        return out

    import pipelines.script2video as script2video_mod

    monkeypatch.setattr(script2video_mod.Script2VideoPipeline, "run", fake_run)
    monkeypatch.setattr(idea2video_mod.Idea2VideoPipeline, "_assemble_final_drama", fake_assemble)

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    result = await pipeline.regenerate_scene(
        previous_result=previous or _previous_result(tmp_path, with_state=with_state),
        scene_index=scene_index,
        working_dir=str(tmp_path / "job"),
        director_note=note,
    )
    return result, run_calls, assembled


@pytest.mark.asyncio
async def test_only_the_chosen_scene_is_regenerated(monkeypatch, tmp_path):
    result, run_calls, assembled = await _regenerate(monkeypatch, tmp_path, scene_index=1)

    assert len(run_calls) == 1, "A retake must generate ONE scene, not the whole drama"
    assert run_calls[0]["scene_idx"] == 1

    # The master is rebuilt from the untouched originals plus the new take,
    # still in scene order.
    paths = assembled["scene_paths"]
    assert len(paths) == 3
    assert paths[0].endswith("orig_scene_0.mp4")
    assert paths[2].endswith("orig_scene_2.mp4")
    assert b"brand new take" == open(paths[1], "rb").read()

    assert result["scenes"][1]["take"] == 2
    assert "take" not in result["scenes"][0], "Untouched scenes must not be re-marked"


@pytest.mark.asyncio
async def test_retake_reuses_the_same_second_budget(monkeypatch, tmp_path):
    """Scene 1's slice is 10.0s. A retake that picked its own length would let
    a customer buy extra runtime one retake at a time."""
    _, run_calls, _ = await _regenerate(monkeypatch, tmp_path, scene_index=1)
    assert run_calls[0]["scene_duration"] == 10.0


@pytest.mark.asyncio
async def test_director_note_reaches_the_shot_brief(monkeypatch, tmp_path):
    _, run_calls, _ = await _regenerate(
        monkeypatch, tmp_path, scene_index=0, note="Too dark — open the shutters."
    )
    requirement = run_calls[0]["user_requirement"]
    assert "Keep it warm and unhurried." in requirement, "The original brief must survive"
    assert "Too dark — open the shutters." in requirement
    assert "binding" in requirement.lower(), (
        "An advisory note gets ignored by the model; the retake has to be directed"
    )


@pytest.mark.asyncio
async def test_locked_portraits_and_set_plate_are_reused_not_regenerated(monkeypatch, tmp_path):
    _, run_calls, _ = await _regenerate(monkeypatch, tmp_path, scene_index=2)
    assert run_calls[0]["character_portraits"] == {"Kemal": "https://cdn/kemal.png"}
    assert run_calls[0]["location_plate_url"] == "https://cdn/set_plate.png", (
        "Re-rolling the set would make the retake not match the scenes around it"
    )


@pytest.mark.asyncio
async def test_job_without_render_state_is_refused_before_spending_anything(monkeypatch, tmp_path):
    with pytest.raises(SceneRegenerationUnavailable):
        await _regenerate(monkeypatch, tmp_path, scene_index=1, with_state=False)


@pytest.mark.asyncio
async def test_missing_sibling_clip_is_refused_before_generating(monkeypatch, tmp_path):
    """If scene 0's clip is gone there is nothing to splice into — say so
    BEFORE running a paid generation, not after."""
    previous = _previous_result(tmp_path)
    os.unlink(previous["scenes"][0]["clip_path"])

    run_calls = []

    async def fake_run(self, **kwargs):
        run_calls.append(kwargs)
        raise AssertionError("must not generate when the splice cannot succeed")

    import pipelines.script2video as script2video_mod

    monkeypatch.setattr(script2video_mod.Script2VideoPipeline, "run", fake_run)

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    with pytest.raises(SceneRegenerationUnavailable) as exc:
        await pipeline.regenerate_scene(
            previous_result=previous,
            scene_index=1,
            working_dir=str(tmp_path / "job"),
        )
    assert "scene 1" in str(exc.value)
    assert run_calls == []


@pytest.mark.asyncio
async def test_each_take_writes_to_its_own_directory(monkeypatch, tmp_path):
    """Overwriting the previous take in place would corrupt the clip the
    still-live master points at, losing both versions if this take fails."""
    previous = _previous_result(tmp_path)
    previous["scenes"][1]["take"] = 2
    _, run_calls, _ = await _regenerate(
        monkeypatch, tmp_path, scene_index=1, previous=previous
    )
    assert run_calls[0]["working_dir"].endswith("scene_1_take3")


@pytest.mark.asyncio
async def test_failed_retake_leaves_the_customer_with_the_video_they_had(monkeypatch, tmp_path):
    """The retake runs against a job that is already COMPLETED and playable.
    If it fails, the job must go back to holding the original result -- not a
    half-updated one, and not a failed status on a video that still exists."""
    import jobs as jobs_mod

    monkeypatch.setattr(jobs_mod, "JOBS_DIR", str(tmp_path))

    previous = _previous_result(tmp_path)
    job = jobs_mod.Job(
        id="retake-job",
        status=jobs_mod.JobStatus.COMPLETED,
        result=previous,
        user_id=None,
        demo=False,
    )

    async def boom(self, **kwargs):
        raise RuntimeError("provider exploded mid-retake")

    monkeypatch.setattr(jobs_mod.job_store, "persist", _noop_persist)
    monkeypatch.setattr(idea2video_mod.Idea2VideoPipeline, "regenerate_scene", boom)

    await jobs_mod.run_regenerate_scene_job(job, "test-key-not-real", 1)

    assert job.status == jobs_mod.JobStatus.COMPLETED, (
        "A failed retake must not mark a job with a working video as failed"
    )
    assert job.result["video_url"] == "https://cdn/original_master.mp4"
    assert job.result is previous or job.result == previous
    assert "unchanged" in (job.error or "")


async def _noop_persist(job):
    return None
