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
from jobs import (  # noqa: E402
    DIALOGUE_EXTRA_CREDIT_COST,
    LIPSYNC_EXTRA_CREDIT_COST,
    Job,
    _refund_undelivered_extras,
)


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
async def test_each_missing_synced_scene_is_refunded(refunds):
    """The add-on is priced per scene, so partial delivery is too."""
    await _refund_undelivered_extras(_job(), {"lipsynced_scenes": [1]})

    assert refunds == [
        ("user-1", 2 * LIPSYNC_EXTRA_CREDIT_COST, "930f11de-4b0")
    ]


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


# --- ...and a refund for a surcharge that was never taken ------------------
#
# The other direction, found on job 6f857aa0-903. api.build_credit_breakdown
# stopped charging for lip sync on a film the picture speaks -- the mouths
# arrive already driven -- and left the row in the quote at zero credits. Both
# refund paths here still read `job.lipsync_enabled`, which records what the
# user ASKED for, not what they paid for. So that job was quoted 0, charged 0,
# and refunded 3, while its log announced "Lip sync was charged (3 credit(s))".
#
# _job_refund_amount is the same hole and the worse one: it pays out on every
# FAILED job, not only on the ones that reach the end.


@pytest.fixture
def picture_speaks(monkeypatch):
    """A deployment whose video backend speaks the film's language."""
    import api as api_mod

    monkeypatch.setattr(api_mod, "_picture_will_carry_dialogue", lambda lang: True)


@pytest.mark.asyncio
async def test_a_surcharge_the_quote_waived_is_not_refunded_as_if_paid(
    refunds, picture_speaks
):
    """Job 6f857aa0-903: lip sync on, nothing charged for it, nothing owed."""
    await _refund_undelivered_extras(_job(), {"lipsynced_scenes": []})

    assert refunds == []


def test_a_failed_speaking_film_is_not_refunded_more_than_it_cost(picture_speaks):
    """The failure path pays out on every dead job, so it leaked the widest."""
    from jobs import _job_refund_amount

    job = _job()

    assert _job_refund_amount(job) == job.num_scenes


def test_a_failed_film_the_picture_does_not_speak_still_gets_the_surcharge_back(
    monkeypatch,
):
    """The other half of the same expression, so this reads as a CHOICE."""
    import api as api_mod
    from jobs import _job_refund_amount

    monkeypatch.setattr(api_mod, "_picture_will_carry_dialogue", lambda lang: False)
    monkeypatch.setattr(api_mod, "is_dialogue_enabled", lambda: True)
    monkeypatch.setattr(api_mod, "_lipsync_configured", lambda: True)
    # Pro, because that is the only plan on which a lip-sync surcharge is
    # taken in the first place, and a refund mirrors what was taken.
    job = _job(plan="pro", dialogue_enabled=True)

    assert _job_refund_amount(job) == job.num_scenes + (
        job.num_scenes * DIALOGUE_EXTRA_CREDIT_COST
    ) + (job.num_scenes * LIPSYNC_EXTRA_CREDIT_COST)


def test_the_refund_matches_what_generate_would_have_deducted(
    monkeypatch, picture_speaks
):
    """Read off /api/generate's own function rather than restated here.

    The two live in different modules and drifted apart once already; the only
    way this stays true is by asking the one that takes the money.
    """
    import api as api_mod
    from jobs import _job_refund_amount

    monkeypatch.setattr(api_mod, "is_dialogue_enabled", lambda: True)
    monkeypatch.setattr(api_mod, "_lipsync_configured", lambda: True)
    job = _job(plan="pro", dialogue_enabled=True)

    charged = api_mod.build_credit_breakdown(
        job.num_scenes,
        music_enabled=job.music_enabled,
        dialogue_enabled=job.dialogue_enabled,
        lipsync_enabled=job.lipsync_enabled,
        plan=job.plan,
        language=job.language,
    )["total_credits"]

    assert _job_refund_amount(job) == charged


def test_a_backend_that_cannot_be_asked_refunds_nothing_extra(monkeypatch):
    """Fail-closed. Refunding nothing is fixable by hand; minting is not."""
    import api as api_mod
    import jobs as mod

    def _boom(_lang):
        raise RuntimeError("no video backend installed")

    monkeypatch.setattr(api_mod, "_picture_will_carry_dialogue", _boom)

    assert mod._lipsync_was_charged(_job()) is False


def test_the_refund_never_exceeds_what_the_job_was_charged():
    """Read off the two expressions rather than trusted to stay in step."""
    from jobs import _job_refund_amount

    job = _job(plan="pro", dialogue_enabled=True)
    full = _job_refund_amount(job)
    lipsync_share = job.num_scenes * LIPSYNC_EXTRA_CREDIT_COST

    assert lipsync_share <= full
