"""Two ways a job can lose facts it still needs, and one way a customer can.

A job that leaves memory and comes back from storage has to come back as the
SAME job: the tier it was ordered at, the shape it was written in, the series
it belongs to. Those are not columns on the jobs table -- they ride on the
result -- and the restore path read only some of them, so an evicted Pro 4K
micro-drama came back a 1080p cinematic standalone and every post-production
button acted on that.

The customer's version of the same problem is the plan lookup: a Supabase blip
answered "free" for a Pro account, and free is not a smaller answer, it is a
different product -- fewer scenes, no music, no dialogue, 1080p -- delivered
and charged for without an error anywhere.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import api as _api  # noqa: E402
import jobs as jobs_mod  # noqa: E402
from jobs import JobStatus  # noqa: E402


# ── what a restored job knows ────────────────────────────────────────────────

_ROW = {
    "id": "job-restored",
    "status": "completed",
    "idea": "a harbour goodbye",
    "num_scenes": 4,
    "plan": "pro",
    "user_id": "user-1",
    "result": {
        "language": "tr",
        "narrative_mode": "micro_drama",
        "delivery_tier": "4k",
        "series_id": "series-7",
        "episode_number": 3,
        "video_url": "https://example.com/v.mp4",
    },
}


@pytest.fixture
def restored(monkeypatch):
    async def _fake_get(job_id):
        return dict(_ROW, id=job_id)

    monkeypatch.setattr(jobs_mod, "_sb_get", _fake_get)
    jobs_mod.job_store._jobs.pop("job-restored", None)
    return jobs_mod.job_store


@pytest.mark.asyncio
async def test_a_restored_job_comes_back_as_the_film_it_was(restored):
    job = await restored.get_or_restore("job-restored")

    assert job is not None
    assert job.delivery_tier == "4k"
    assert job.narrative_mode == "micro_drama"
    assert job.series_id == "series-7"
    assert job.episode_number == 3
    assert job.language == "tr"


@pytest.mark.asyncio
async def test_a_restored_job_and_its_dict_agree(restored):
    """The client reads one of these and the retake path reads the other."""
    job = await restored.get_or_restore("job-restored")
    as_dict = jobs_mod._sb_row_to_dict(dict(_ROW))

    for field in ("delivery_tier", "narrative_mode", "series_id", "episode_number"):
        assert getattr(job, field) == as_dict[field], field


def test_a_job_that_was_approved_still_knows_it_required_approval():
    """Once approved the status is RUNNING like any other job, so inferring
    the flag from the status said no -- about the one job for which it is the
    difference between being charged up front and at approval time."""
    row = dict(_ROW, status="running", result={"_require_script_approval": True})

    assert jobs_mod._sb_row_to_dict(row)["require_script_approval"] is True


def test_a_job_still_waiting_for_its_human_does_too():
    row = dict(_ROW, status=JobStatus.AWAITING_SCRIPT_APPROVAL.value, result={})

    assert jobs_mod._sb_row_to_dict(row)["require_script_approval"] is True


def test_an_ordinary_job_does_not():
    assert jobs_mod._sb_row_to_dict(dict(_ROW))["require_script_approval"] is False


# ── what a job id is worth ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_job_id_is_not_a_short_number():
    """It addresses endpoints a browser reaches without a token, so it is the
    secret, and twelve hex characters is a space worth walking."""
    job = await jobs_mod.job_store.create(idea="x")
    try:
        assert len(job.id) >= 32
    finally:
        jobs_mod.job_store._jobs.pop(job.id, None)


# ── what a storage URL is ────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "url",
    [
        "https://abc.supabase.co/storage/v1/object/sign/videos/x.mp4",
        "https://abc.supabase.co/anything",
        "https://cdn.example.com/storage/v1/object/x.mp4",
    ],
)
def test_a_hosted_video_is_recognised(url):
    assert jobs_mod._is_remote_storage_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/videos/supabase-tutorial.mp4",
        "https://notsupabase.evil.com/x.mp4",
        "https://example.com/x.mp4?ref=supabase",
        "",
        None,
    ],
)
def test_something_that_merely_says_supabase_is_not(url):
    """A false positive deletes the working directory of a job whose video
    was never uploaded anywhere."""
    assert jobs_mod._is_remote_storage_url(url) is False


# ── what an outage may not do to a plan ──────────────────────────────────────

@pytest.mark.asyncio
async def test_a_blip_does_not_downgrade_a_pro_customer(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock, patch

    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = [{"plan": "pro"}]

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(return_value=ok)

    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "key"), \
         patch("api.httpx.AsyncClient", return_value=client):
        assert await _api._get_user_plan("user-pro") == "pro"

    client.get = AsyncMock(side_effect=RuntimeError("connection reset"))
    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "key"), \
         patch("api.httpx.AsyncClient", return_value=client):
        assert await _api._get_user_plan("user-pro") == "pro"


@pytest.mark.asyncio
async def test_a_user_nobody_has_ever_looked_up_is_still_free(monkeypatch):
    """The cache survives an outage; it does not invent a plan."""
    from unittest.mock import AsyncMock, patch

    _api._plan_cache.pop("user-unknown", None)

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.get = AsyncMock(side_effect=RuntimeError("connection reset"))

    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "key"), \
         patch("api.httpx.AsyncClient", return_value=client):
        assert await _api._get_user_plan("user-unknown") == "free"


def test_a_remembered_plan_goes_stale(monkeypatch):
    _api._remember_plan("user-old", "pro")
    monkeypatch.setattr(_api, "_PLAN_CACHE_TTL", -1.0)

    assert _api._remembered_plan("user-old") == ""


# ── what HSTS is for ─────────────────────────────────────────────────────────

def test_a_developer_machine_is_not_pinned_to_https(monkeypatch):
    """Sent from localhost it pins that port to https for two years, for every
    project on it, with no way back but clearing the browser's HSTS store."""
    monkeypatch.setenv("MUSEFORGE_ENV", "development")
    monkeypatch.delenv("MUSEFORGE_HSTS", raising=False)

    assert _api._hsts_enabled() is False


def test_production_still_is(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_ENV", raising=False)
    monkeypatch.delenv("MUSEFORGE_HSTS", raising=False)

    assert _api._hsts_enabled() is True


def test_a_deployment_can_say_so_either_way(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_ENV", "development")
    monkeypatch.setenv("MUSEFORGE_HSTS", "1")
    assert _api._hsts_enabled() is True

    monkeypatch.setenv("MUSEFORGE_ENV", "production")
    monkeypatch.setenv("MUSEFORGE_HSTS", "0")
    assert _api._hsts_enabled() is False
