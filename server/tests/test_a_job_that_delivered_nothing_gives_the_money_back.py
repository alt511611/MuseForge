"""Every way a paid job can end without a film, and what it owes.

The failure paths already refunded. Three did not:

- The stale-job reaper, which fails jobs nothing has touched in an hour, kept
  the credits. Those are exactly the jobs a customer cannot see failing.
- The approve-script branch never gave back a lip-sync pass that was charged
  for and then refused by the provider, though the ordinary branch did.
- The refund amount was a second copy of the price list, and a copy that did
  not know about plans: a free-plan job carrying a music flag was refunded a
  surcharge that was never taken.

The reaper's rule is the careful one: it pays back what the job RECORDS being
charged, not what it recomputes. A job still writing its free script before
approval looks, from the row, exactly like a paid job that is rendering --
and recomputing would mint credits for it.
"""

import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import jobs as jobs_mod  # noqa: E402
from jobs import Job, JobStatus, _refund_reaped_job  # noqa: E402


@pytest.fixture
def refunds(monkeypatch):
    calls = []

    async def _spy(user_id, amount, job_id):
        calls.append((user_id, amount, job_id))

    monkeypatch.setattr(jobs_mod, "_sb_refund_credits", _spy)
    return calls


def _row(**kwargs):
    row = {
        "id": "job-1",
        "status": "running",
        "user_id": "user-1",
        "demo": False,
        "result": {"_credits_charged": 7},
    }
    row.update(kwargs)
    return row


# ── the reaper ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_reaped_job_gives_back_what_it_took(refunds):
    await _refund_reaped_job(_row())

    assert refunds == [("user-1", 7, "job-1")]


@pytest.mark.asyncio
async def test_a_job_that_was_never_charged_is_not_paid_out(refunds):
    """A run parked before approval writes a script and takes nothing. From
    the row it is indistinguishable from a paid render, which is why the
    amount is read rather than recomputed."""
    await _refund_reaped_job(_row(result={"script": {"title": "Harbor"}}))
    await _refund_reaped_job(_row(result=None))

    assert refunds == []


@pytest.mark.asyncio
async def test_a_demo_or_anonymous_run_is_not_paid_out(refunds):
    await _refund_reaped_job(_row(demo=True))
    await _refund_reaped_job(_row(user_id=None))

    assert refunds == []


@pytest.mark.asyncio
async def test_a_charge_that_is_not_a_number_is_not_paid_out(refunds):
    """Including `True`, which is an int in Python and is not 1 credit."""
    for bad in (True, "7", -3, 0, None, {"amount": 7}):
        await _refund_reaped_job(_row(result={"_credits_charged": bad}))

    assert refunds == []


def test_the_reaper_asks_for_the_columns_it_needs_to_refund():
    """Selecting only id/status/updated_at is how this stayed unnoticed: the
    reaper never had the owner in front of it."""
    import inspect

    source = inspect.getsource(jobs_mod.reap_stale_jobs)

    assert "user_id" in source and "result" in source
    assert "_refund_reaped_job" in source


def test_what_a_job_was_charged_is_kept_off_the_wire():
    """It lives on the result, so it has to be underscore-prefixed or the
    browser gets it on every status poll."""
    from jobs import public_result

    assert "_credits_charged" not in public_result({"_credits_charged": 7, "a": 1})


# ── the refund amount ────────────────────────────────────────────────────────

def test_a_free_plan_job_is_not_refunded_surcharges_it_never_paid(monkeypatch):
    """Music is billed on Creator and Pro, dialogue on Pro. A free-plan job can
    still carry both flags -- /api/generate drops them silently rather than
    erroring -- so a refund that reads the flags and not the plan hands back
    credits that were never taken."""
    import api as api_mod
    from jobs import _job_refund_amount

    monkeypatch.setattr(api_mod, "is_dialogue_enabled", lambda: True)
    monkeypatch.setattr(api_mod, "_lipsync_configured", lambda: True)

    job = Job(
        id="job-free",
        num_scenes=3,
        plan="free",
        music_enabled=True,
        dialogue_enabled=True,
        lipsync_enabled=True,
    )

    assert _job_refund_amount(job) == 3


def test_the_refund_is_read_off_the_function_that_takes_the_money():
    import inspect

    from jobs import _job_refund_amount

    assert "build_credit_breakdown" in inspect.getsource(_job_refund_amount)


# ── the approve-script branch ────────────────────────────────────────────────

def test_the_approved_script_branch_refunds_undelivered_extras_too():
    """Charged per scene up front, fails open, and on this branch alone was
    never given back."""
    import inspect

    source = inspect.getsource(jobs_mod.run_continue_from_script_job)

    assert "_refund_undelivered_extras" in source


@pytest.mark.asyncio
async def test_a_lip_sync_pass_nobody_ran_comes_back_on_the_approved_path(
    monkeypatch, tmp_path, refunds
):
    """End to end on that branch: three scenes billed for lip sync, the
    provider refuses all three, the film ships and the surcharge comes back."""
    import api as api_mod
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(jobs_mod, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(jobs_mod, "cleanup_working_dir", lambda *_a, **_k: None)
    monkeypatch.setattr(jobs_mod.job_store, "persist", AsyncMock())
    monkeypatch.setattr(jobs_mod.job_store, "emit", AsyncMock())
    monkeypatch.setattr(api_mod, "_picture_will_carry_dialogue", lambda lang: False)

    pipeline = MagicMock()
    pipeline.continue_from_script = AsyncMock(
        return_value={
            "title": "Harbor",
            "video_url": "https://example.com/v.mp4",
            "lipsynced_scenes": [],
        }
    )

    job = Job(
        id="job-approved",
        user_id="user-1",
        num_scenes=3,
        plan="pro",
        lipsync_enabled=True,
        dialogue_enabled=True,
        status=JobStatus.RUNNING,
    )
    script_data = {
        "title": "Harbor",
        "logline": "A goodbye",
        "mood": "melancholy",
        "scenes": ["a", "b", "c"],
        "characters": [],
        "setting_location": "pier",
        "setting_time_of_day": "sunset",
        "setting_era": "present day",
    }

    with patch("pipelines.idea2video.Idea2VideoPipeline", return_value=pipeline):
        await jobs_mod.run_continue_from_script_job(job, "k", script_data)

    assert job.status == JobStatus.COMPLETED
    assert refunds and refunds[0][0] == "user-1"
    assert refunds[0][1] == 3 * jobs_mod.LIPSYNC_EXTRA_CREDIT_COST
