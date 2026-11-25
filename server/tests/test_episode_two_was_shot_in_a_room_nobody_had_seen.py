"""Episode two was told the room's name and drew a different room.

A series carried its cast forward as pictures (every member keeps a
``portrait_url``) and its setting forward as WORDS. The setting's picture --
the empty-set plate every frame of an episode is conditioned on -- died with
the job that drew it. So "stone-walled harbour office" came back as a new room
each episode, behind faces that were the same: the half of continuity a viewer
of a series notices first, because they have seen the room before.

The plate is now locked onto the series the way the setting is (once, by the
first confirmed episode that has one, and only if that episode was set in the
series' own place), and every later episode is commissioned with it.
"""

import asyncio
import os
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["MUSEFORGE_DEMO"] = "1"
os.environ.pop("MUAPI_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

import api as _api  # noqa: E402
import series_store  # noqa: E402
from auth import AuthUser  # noqa: E402
from interfaces.series import Series, absorb, from_dict, mark_delivered, confirm  # noqa: E402

client = TestClient(_api.app)

PLATE = "https://cdn/harbour_office_plate.png"


@contextmanager
def _auth_as(user_id="user-pro-1", email="pro@example.com"):
    async def _fake_user():
        return AuthUser(user_id, email)

    _api.app.dependency_overrides[_api.get_current_user] = _fake_user
    try:
        yield
    finally:
        _api.app.dependency_overrides.pop(_api.get_current_user, None)


@pytest.fixture(autouse=True)
def _clear_series_mem():
    series_store._memory.clear()
    yield
    series_store._memory.clear()


def _result(number=1, location="a harbour office", plate=PLATE):
    return {
        "video_url": f"https://cdn/ep{number}.mp4",
        "location_plate": plate,
        "script": {
            "title": f"Episode {number}",
            "setting_location": location,
            "scenes": [{"action": "She opens the letter.", "turn": "the boat was sold"}],
        },
    }


def test_the_first_confirmed_episode_locks_the_picture_of_the_room():
    series = Series(title="Harbour")

    absorb(series, 1, "job-1", _result())

    assert series.location_plate_url == PLATE


def test_a_later_episode_cannot_repaint_the_room():
    series = Series(title="Harbour")

    absorb(series, 1, "job-1", _result())
    absorb(series, 2, "job-2", _result(2, plate="https://cdn/a_new_room.png"))

    assert series.location_plate_url == PLATE


def test_an_episode_set_somewhere_else_does_not_become_the_room():
    """The screenwriter can still move an episode despite the brief. Its plate
    is a picture of somewhere else, and locking it would condition every later
    episode on the wrong set."""
    series = Series(title="Harbour")

    absorb(series, 1, "job-1", _result(plate=""))
    absorb(series, 2, "job-2", _result(2, location="a hospital ward", plate="https://cdn/ward.png"))

    assert series.setting_location == "a harbour office"
    assert series.location_plate_url == ""


def test_an_unconfirmed_episode_locks_nothing():
    """The plate is continuity, and continuity only reaches the series from a
    take somebody approved -- the same gate the cast and setting go through."""
    series = Series(title="Harbour")

    mark_delivered(series, 1, "job-1", _result())
    assert series.location_plate_url == ""

    confirm(series, 1, _result())
    assert series.location_plate_url == PLATE


def test_the_picture_survives_the_round_trip_through_storage():
    series = Series(title="Harbour")
    absorb(series, 1, "job-1", _result())

    assert from_dict(series.as_dict()).location_plate_url == PLATE
    # A row written before the field existed still loads.
    assert from_dict({"title": "Old"}).location_plate_url == ""


def _create_series():
    return client.post(
        "/api/series", json={"title": "Harbour", "premise": "A letter arrives."}
    ).json()


def test_the_next_episode_is_commissioned_with_the_series_room():
    with _auth_as(), patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")):
        series = _create_series()
        first = client.post(f"/api/series/{series['id']}/episodes", json={}).json()
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            series_store.record_episode(
                "user-pro-1", series["id"], first["episode_number"], first["job_id"], _result()
            )
        )
        second = client.post(f"/api/series/{series['id']}/episodes", json={}).json()

    from jobs import job_store

    assert job_store.get(first["job_id"]).location_url == ""
    assert job_store.get(second["job_id"]).location_url == PLATE


@pytest.mark.asyncio
async def test_the_room_reaches_the_pipeline_as_the_set_and_is_not_redrawn(monkeypatch):
    import jobs as jobs_mod

    monkeypatch.setattr(jobs_mod.job_store, "persist", AsyncMock())
    monkeypatch.setattr(jobs_mod.job_store, "emit", AsyncMock())

    job = jobs_mod.Job(
        id="episode-2",
        idea="Who was in the doorway",
        status=jobs_mod.JobStatus.QUEUED,
        demo=True,
        num_scenes=2,
        location_url=PLATE,
    )
    pipeline = MagicMock()
    pipeline.run = AsyncMock(side_effect=RuntimeError("stop here"))

    with patch("pipelines.idea2video.Idea2VideoPipeline", return_value=pipeline):
        await jobs_mod.run_generation_job(job, api_key="test-key")

    assert pipeline.run.await_args.kwargs["location_image_override"] == PLATE
    # ...and where the approve-script path and a restored job look for it.
    assert job.result["_location_override"] == PLATE


@pytest.mark.asyncio
async def test_a_restored_episode_still_knows_its_room(monkeypatch):
    """A retry of an evicted episode is built from the restored job. Losing
    the room there is the original bug again, one restart later."""
    import jobs as jobs_mod

    async def fake_get(job_id):
        return {
            "id": job_id,
            "status": "failed",
            "idea": "Who was in the doorway",
            "result": {"_location_override": PLATE, "series_id": "s1"},
        }

    monkeypatch.setattr(jobs_mod, "_sb_get", fake_get)

    job = await jobs_mod.JobStore().get_or_restore("episode-2")

    assert job.location_url == PLATE
