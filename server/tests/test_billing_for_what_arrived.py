"""A paid extra that did not happen is not a thing to keep the money for.

Lip sync is charged per scene, up front, and it fails open -- correctly: a
mouth that could not be driven is not worth failing a rendered film over. Job
930f11de-4b0 was billed for lip sync on three scenes, had all three refused by
a provider account out of balance, and shipped closed mouths under a voice
track. It already told the user so in its warnings. It kept the credits.

Not a job failure, deliberately. That job's picture cost real provider money
and is exactly what was asked for; throwing it away to tidy the billing would
charge the user more, not less.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import jobs as jobs_module  # noqa: E402
from jobs import LIPSYNC_EXTRA_CREDIT_COST, Job, _refund_undelivered_extras  # noqa: E402


@pytest.fixture
def refunds(monkeypatch):
    """Every refund this module issues, as (user_id, amount, job_id)."""
    calls = []

    async def _spy(user_id, amount, job_id):
        calls.append((user_id, amount, job_id))

    monkeypatch.setattr(jobs_module, "_sb_refund_credits", _spy)
    return calls


def _job(**kwargs):
    fields = dict(
        id="930f11de-4b0",
        user_id="user-1",
        num_scenes=3,
        lipsync_enabled=True,
        demo=False,
    )
    fields.update(kwargs)
    return Job(**fields)


@pytest.mark.asyncio
async def test_lip_sync_charged_and_never_run_is_given_back(refunds):
    """The delivered job: three scenes billed, three refused, none synced."""
    await _refund_undelivered_extras(_job(), {"lipsynced_scenes": []})

    assert refunds == [("user-1", 3 * LIPSYNC_EXTRA_CREDIT_COST, "930f11de-4b0")]


@pytest.mark.asyncio
async def test_lip_sync_that_ran_is_not_refunded(refunds):
    await _refund_undelivered_extras(_job(), {"lipsynced_scenes": [0, 1, 2]})

    assert refunds == []


@pytest.mark.asyncio
async def test_one_synced_scene_is_still_a_delivered_feature(refunds):
    """Partial delivery is a judgement about quality, not about billing, and
    this refunds only what plainly did not happen at all."""
    await _refund_undelivered_extras(_job(), {"lipsynced_scenes": [1]})

    assert refunds == []


@pytest.mark.asyncio
async def test_a_job_that_was_never_charged_for_it_gets_nothing_back(refunds):
    """The condition mirrors _job_refund_amount's lip-sync term exactly, so
    this cannot hand back credits that were never taken."""
    await _refund_undelivered_extras(
        _job(lipsync_enabled=False), {"lipsynced_scenes": []}
    )

    assert refunds == []


@pytest.mark.asyncio
async def test_a_demo_job_spends_nothing_and_is_owed_nothing(refunds):
    await _refund_undelivered_extras(_job(demo=True), {"lipsynced_scenes": []})

    assert refunds == []


@pytest.mark.asyncio
async def test_an_anonymous_job_has_nobody_to_refund(refunds):
    await _refund_undelivered_extras(_job(user_id=""), {"lipsynced_scenes": []})

    assert refunds == []


@pytest.mark.asyncio
async def test_a_missing_result_is_read_as_nothing_delivered(refunds):
    """A job whose result never arrived did not sync anything either."""
    await _refund_undelivered_extras(_job(), {})

    assert refunds == [("user-1", 3 * LIPSYNC_EXTRA_CREDIT_COST, "930f11de-4b0")]


def test_the_refund_never_exceeds_what_the_job_was_charged():
    """Read off the two expressions rather than trusted to stay in step."""
    from jobs import _job_refund_amount

    job = _job()
    full = _job_refund_amount(job)
    lipsync_share = job.num_scenes * LIPSYNC_EXTRA_CREDIT_COST

    assert lipsync_share <= full
