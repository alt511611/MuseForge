"""Repo-audit fixes: approval billing, disk cleanup, job eviction.

Three defects found by reading the job/billing paths rather than the
generation pipeline:
- the approval step billed the job's ORIGINAL scene count while rendering
  the caller's edited script;
- failed and cancelled jobs left their working directory on disk;
- the in-memory job store evicted purely by age, dropping live jobs.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import jobs as jobs_mod  # noqa: E402
from jobs import JobStatus, JobStore  # noqa: E402


# --- billing follows the approved script --------------------------------


def _approve(tc, job_id, scenes):
    return tc.post(
        f"/api/jobs/{job_id}/approve-script",
        json={
            "script": {
                "title": "t",
                "logline": "l",
                "scenes": [{"action": f"scene {i}", "dialogue": []} for i in range(scenes)],
            }
        },
    )


@pytest.mark.asyncio
async def test_approval_bills_the_edited_scene_count(monkeypatch):
    """A 2-scene job whose script is edited to 8 scenes must be charged for
    8 -- otherwise the caller renders 8 scenes for the price of 2."""
    import api as _api
    from fastapi.testclient import TestClient

    job = await _api.job_store.create(
        idea="x", style="Cinematic", director_style="cinematic_balanced",
        user_requirement="", num_scenes=2, aspect_ratio="16:9",
        demo=False, plan="pro", user_id="u1",
    )
    job.status = JobStatus.AWAITING_SCRIPT_APPROVAL

    deduct = AsyncMock(return_value=True)
    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real"}), \
         patch.object(_api, "_deduct_credits", deduct), \
         patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")):
        _api.app.dependency_overrides[_api.get_optional_user] = (
            lambda: _api.AuthUser(user_id="u1", email="e")
        )
        try:
            tc = TestClient(_api.app, raise_server_exceptions=False)
            resp = _approve(tc, job.id, scenes=8)
            assert resp.status_code == 200, resp.text
        finally:
            _api.app.dependency_overrides.clear()

    charged = deduct.await_args.args[1]
    assert charged == 8, f"billed {charged} credits for an 8-scene script"
    # Refunds and estimates must agree with what was actually charged.
    assert job.num_scenes == 8


@pytest.mark.asyncio
async def test_approval_enforces_plan_limit_on_edited_script(monkeypatch):
    """The plan ceiling must apply to the script actually rendered."""
    import api as _api
    from fastapi.testclient import TestClient

    job = await _api.job_store.create(
        idea="x", style="Cinematic", director_style="cinematic_balanced",
        user_requirement="", num_scenes=2, aspect_ratio="16:9",
        demo=False, plan="free", user_id="u2",
    )
    job.status = JobStatus.AWAITING_SCRIPT_APPROVAL

    over_limit = _api.PLAN_MAX_SCENES["free"] + 5
    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real"}), \
         patch.object(_api, "_deduct_credits", AsyncMock(return_value=True)), \
         patch.object(_api, "_get_user_plan", AsyncMock(return_value="free")):
        _api.app.dependency_overrides[_api.get_optional_user] = (
            lambda: _api.AuthUser(user_id="u2", email="e")
        )
        try:
            tc = TestClient(_api.app, raise_server_exceptions=False)
            resp = _approve(tc, job.id, scenes=over_limit)
        finally:
            _api.app.dependency_overrides.clear()

    assert resp.status_code == 400
    assert "scenes" in resp.json()["detail"].lower()


# --- working dir cleanup ------------------------------------------------


def _branch_bodies(fn_name):
    import re

    src = open(os.path.join(os.path.dirname(__file__), "..", "jobs.py")).read()
    i = src.index(f"async def {fn_name}")
    j = src.find("\nasync def ", i + 10)
    body = src[i : j if j > 0 else len(src)]
    return [m.group(0) for m in re.finditer(r"except (\w+)[^\n]*:\n((?:[ ]{8}.*\n|\n)*)", body)]


@pytest.mark.parametrize(
    "fn", ["run_generation_job", "run_continue_from_script_job"]
)
def test_every_failure_branch_cleans_the_working_dir(fn):
    """A failed job's partial renders are never served; leaving them on disk
    fills a fixed-size container long before the 24h orphan sweep."""
    for branch in _branch_bodies(fn):
        assert "cleanup_working_dir" in branch, (
            f"{fn} has a failure branch that leaks its working dir:\n{branch}"
        )


@pytest.mark.parametrize(
    "fn", ["run_generation_job", "run_continue_from_script_job"]
)
def test_every_failure_branch_refunds(fn):
    for branch in _branch_bodies(fn):
        assert "_sb_refund_credits" in branch, (
            f"{fn} has a failure branch that keeps the caller's credits:\n{branch}"
        )


# --- job eviction -------------------------------------------------------


async def _fill(store, count, status):
    made = []
    for _ in range(count):
        job = await store.create(
            idea="x", style="s", director_style="d", user_requirement="",
            num_scenes=1, aspect_ratio="16:9", demo=True,
        )
        job.status = status
        made.append(job)
        await asyncio.sleep(0)
    return made


@pytest.mark.asyncio
async def test_eviction_prefers_finished_over_running(monkeypatch):
    """Evicting purely by age drops the oldest job even while it runs -- its
    SSE stream and cancel endpoint then 404 while the spend carries on."""
    monkeypatch.setattr(jobs_mod, "_sb_upsert", AsyncMock(return_value=None))
    store = JobStore(max_jobs=3)

    running = await _fill(store, 2, JobStatus.RUNNING)  # oldest two
    finished = await _fill(store, 1, JobStatus.COMPLETED)

    await store.create(
        idea="new", style="s", director_style="d", user_requirement="",
        num_scenes=1, aspect_ratio="16:9", demo=True,
    )

    assert store.get(finished[0].id) is None, "finished job should be evicted first"
    for job in running:
        assert store.get(job.id) is not None, "a running job was evicted"


@pytest.mark.asyncio
async def test_eviction_falls_back_when_all_are_live(monkeypatch):
    """With nothing finished, the store must still bound its memory."""
    monkeypatch.setattr(jobs_mod, "_sb_upsert", AsyncMock(return_value=None))
    store = JobStore(max_jobs=2)

    live = await _fill(store, 2, JobStatus.RUNNING)
    await store.create(
        idea="new", style="s", director_style="d", user_requirement="",
        num_scenes=1, aspect_ratio="16:9", demo=True,
    )

    assert len(store._jobs) == 2
    assert store.get(live[0].id) is None  # oldest live job evicted
    assert store.get(live[1].id) is not None
