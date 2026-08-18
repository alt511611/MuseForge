"""Re-shooting a scene must not be a one-way door.

A retake is a roll of the dice the customer paid for, and the roll being
replaced was usually 90% right -- shots fail in their last second, not their
first. Two things stood between the user and the take they preferred:

1. Every take's archive was uploaded under the SAME storage key
   (``{job}_scene_{i}``), so a retake overwrote the only copy that outlives
   the working directory. The local file survived in its own take directory
   and nothing pointed at it.
2. Nothing recorded that earlier takes had existed at all, so there was
   nowhere for the UI to offer them from.

The only route back to take 1 was to buy a take 4 and hope.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines.idea2video import (  # noqa: E402
    Idea2VideoPipeline,
    SceneRegenerationUnavailable,
    _record_take,
)


# ── the record ──────────────────────────────────────────────────────────────


def test_each_take_is_remembered_in_order():
    scene = {"index": 0}
    _record_take(scene, 1, "https://cdn/t1.mp4", "/tmp/t1.mp4")
    _record_take(scene, 3, "https://cdn/t3.mp4", "/tmp/t3.mp4")
    _record_take(scene, 2, "https://cdn/t2.mp4", "/tmp/t2.mp4")

    assert [t["take"] for t in scene["takes"]] == [1, 2, 3]


def test_re_recording_a_take_updates_it_instead_of_duplicating():
    """Re-archiving happens on every assembly pass, not only after a retake."""
    scene = {"index": 0}
    _record_take(scene, 1, "", "/tmp/local-only.mp4")
    _record_take(scene, 1, "https://cdn/t1.mp4", "/tmp/local-only.mp4")

    assert len(scene["takes"]) == 1
    assert scene["takes"][0]["clip_url"] == "https://cdn/t1.mp4"


@pytest.mark.asyncio
async def test_the_archive_key_carries_the_take(monkeypatch, tmp_path):
    """The regression: one key per scene meant take 2's upload destroyed
    take 1's, which is the copy that outlives the working directory."""
    keys = []

    async def fake_upload(path, key):
        keys.append(key)
        return f"https://cdn/{key}.mp4"

    import tools.supabase_storage as storage_mod

    monkeypatch.setattr(storage_mod, "upload_video", fake_upload)

    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"fake")
    job_dir = tmp_path / "job-abc"
    job_dir.mkdir()

    pipeline = Idea2VideoPipeline("test-key")
    scenes = [{"index": 0, "clip_index": 0, "take": 2}]
    await pipeline._archive_scene_clips(scenes, [str(clip)], str(job_dir))

    assert keys == ["job-abc_scene_0_take2"]
    assert scenes[0]["takes"][0]["take"] == 2


# ── the restore ─────────────────────────────────────────────────────────────


def _finished_job(tmp_path, current_take=2):
    take1 = tmp_path / "take1.mp4"
    take2 = tmp_path / "take2.mp4"
    take1.write_bytes(b"one")
    take2.write_bytes(b"two")
    return {
        "scenes": [
            {
                "index": 0,
                "clip_index": 0,
                "take": current_take,
                "clip_url": "https://cdn/take2.mp4",
                "clip_path": str(take2),
                "script": {"action": "She waits."},
                "takes": [
                    {"take": 1, "clip_url": "https://cdn/take1.mp4",
                     "clip_path": str(take1)},
                    {"take": 2, "clip_url": "https://cdn/take2.mp4",
                     "clip_path": str(take2)},
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_restoring_take_one_puts_its_clip_back_in_the_cut(
    tmp_path, monkeypatch
):
    from unittest.mock import AsyncMock

    result_holder = _finished_job(tmp_path)
    pipeline = Idea2VideoPipeline("test-key")

    seen = {}

    async def fake_timeline_edit(previous_result, timeline, working_dir, **kwargs):
        seen["timeline"] = timeline
        return {**previous_result, "video_url": "https://cdn/new-master.mp4"}

    pipeline.apply_timeline_edit = AsyncMock(side_effect=fake_timeline_edit)

    result = await pipeline.restore_scene_take(
        previous_result=result_holder,
        scene_index=0,
        take=1,
        working_dir=str(tmp_path / "job"),
    )

    scene = result["scenes"][0]
    assert scene["take"] == 1
    assert scene["clip_path"].endswith("take1.mp4")
    # Nothing was generated: the cut is rebuilt from clips that already exist.
    assert seen["timeline"] == [
        {"scene_index": 0, "trim_start": 0.0, "trim_end": 0.0}
    ]


@pytest.mark.asyncio
async def test_the_take_being_replaced_stays_reachable(tmp_path):
    """Restoring take 1 must not strand take 2, or the door is still one-way,
    just pointing the other direction."""
    from unittest.mock import AsyncMock

    result_holder = _finished_job(tmp_path)
    pipeline = Idea2VideoPipeline("test-key")
    pipeline.apply_timeline_edit = AsyncMock(
        side_effect=lambda previous_result, **kw: dict(previous_result)
    )

    result = await pipeline.restore_scene_take(
        previous_result=result_holder, scene_index=0, take=1,
        working_dir=str(tmp_path / "job"),
    )

    assert {t["take"] for t in result["scenes"][0]["takes"]} == {1, 2}


@pytest.mark.asyncio
async def test_an_existing_cut_is_not_undone_by_a_restore(tmp_path):
    """A user who reordered or trimmed the drama and then restored a take used
    to get their edit silently reverted along with the clip."""
    from unittest.mock import AsyncMock

    result_holder = _finished_job(tmp_path)
    result_holder["timeline"] = [
        {"scene_index": 0, "trim_start": 1.5, "trim_end": 0.0}
    ]
    pipeline = Idea2VideoPipeline("test-key")

    seen = {}

    async def fake_timeline_edit(previous_result, timeline, working_dir, **kwargs):
        seen["timeline"] = timeline
        return dict(previous_result)

    pipeline.apply_timeline_edit = AsyncMock(side_effect=fake_timeline_edit)

    await pipeline.restore_scene_take(
        previous_result=result_holder, scene_index=0, take=1,
        working_dir=str(tmp_path / "job"),
    )

    assert seen["timeline"] == [
        {"scene_index": 0, "trim_start": 1.5, "trim_end": 0.0}
    ]


@pytest.mark.asyncio
async def test_a_take_that_was_never_kept_is_refused_by_name(tmp_path):
    pipeline = Idea2VideoPipeline("test-key")

    with pytest.raises(SceneRegenerationUnavailable, match="available: 1, 2"):
        await pipeline.restore_scene_take(
            previous_result=_finished_job(tmp_path), scene_index=0, take=7,
            working_dir=str(tmp_path / "job"),
        )


@pytest.mark.asyncio
async def test_a_take_whose_clip_is_gone_is_refused_rather_than_assembled(
    tmp_path,
):
    """Storage is cleaned eventually. Assembling around a dead pointer would
    surface as an unreadable master instead of a sentence the user can act on."""
    job = _finished_job(tmp_path)
    job["scenes"][0]["takes"][0] = {"take": 1, "clip_url": "", "clip_path": "/gone.mp4"}
    pipeline = Idea2VideoPipeline("test-key")

    with pytest.raises(SceneRegenerationUnavailable, match="no longer stored"):
        await pipeline.restore_scene_take(
            previous_result=job, scene_index=0, take=1,
            working_dir=str(tmp_path / "job"),
        )


@pytest.mark.asyncio
async def test_a_scene_that_is_not_in_the_video_is_refused(tmp_path):
    pipeline = Idea2VideoPipeline("test-key")

    with pytest.raises(SceneRegenerationUnavailable, match="Scene 4"):
        await pipeline.restore_scene_take(
            previous_result=_finished_job(tmp_path), scene_index=3, take=1,
            working_dir=str(tmp_path / "job"),
        )
