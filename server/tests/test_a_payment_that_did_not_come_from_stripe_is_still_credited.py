"""Money that arrives through Whop buys exactly what money through Stripe buys.

MuseForge sells through Whop first, because Whop is the merchant of record and
Stripe needs a registered company that does not exist yet. That is a change of
PROCESSOR, and it must not become a change of PRODUCT: a Pro annual customer
who paid Whop has bought 36 x 12 = 432 credits with a year to spend them, the
same as a Pro annual customer who paid Stripe, because both allowances are read
from the one table in `billing.py`.

The failure this file is written against is not a crash. It is a Whop customer
being quietly provisioned as Creator -- or being paid a single month's
allowance on an annual plan, which is the exact bug that
`test_annual_billing.py` was written for on the Stripe side, reintroduced by a
second integration that computes the same numbers its own way.

The last two tests cover the thing Whop has and Stripe does not: there is no
`client_reference_id`. The only thread from the click to the webhook is the
checkout metadata, so a payment that lost it has to be recoverable from the
membership id on the profile -- and a payment that cannot be tied to anybody
must refuse to look like a success.
"""

import pytest

import billing
import whop_integration as wi


@pytest.fixture(autouse=True)
def _plans(monkeypatch):
    monkeypatch.setenv("WHOP_PLAN_CREATOR", "plan_creator")
    monkeypatch.setenv("WHOP_PLAN_PRO", "plan_pro")
    monkeypatch.setenv("WHOP_PLAN_CREATOR_ANNUAL", "plan_creator_annual")
    monkeypatch.setenv("WHOP_PLAN_PRO_ANNUAL", "plan_pro_annual")
    monkeypatch.setenv("WHOP_PLAN_CREDITS_MEDIUM", "plan_credits_medium")


@pytest.fixture
def granted(monkeypatch):
    """Every grant this test makes, as (user_id, credits, reason, days)."""
    calls: list = []

    async def _grant(user_id, credits_delta, **kwargs):
        calls.append(
            (
                user_id,
                credits_delta,
                kwargs.get("reason"),
                kwargs.get("validity_days"),
                kwargs.get("plan"),
            )
        )

    monkeypatch.setattr(billing, "grant_credits", _grant)
    return calls


def _payment(billing_reason: str, plan_id: str = "", metadata: dict = None) -> dict:
    """A Whop payment.succeeded `data` object, shaped as Whop nests it."""
    return {
        "id": "pay_1",
        "billing_reason": billing_reason,
        "metadata": metadata if metadata is not None else {"user_id": "user-1"},
        "plan": {"id": plan_id} if plan_id else None,
        "membership": {"id": "mem_1"},
        "user": {"id": "user_whop_1"},
    }


@pytest.mark.asyncio
async def test_an_annual_whop_subscription_pays_the_whole_year(granted):
    """The allowance and the expiry both come from `billing.allowance_for`, so
    an annual Whop plan lands twelve months with a year to spend them -- not a
    month on a thirty-day fuse."""
    await wi._dispatch_event(
        "payment.succeeded", _payment("subscription_create", "plan_pro_annual")
    )
    assert granted == [
        (
            "user-1",
            billing.PLAN_CREDITS["pro"] * 12,
            "subscription_renewal",
            billing.ANNUAL_CREDIT_VALIDITY_DAYS,
            "pro",
        )
    ]


@pytest.mark.asyncio
async def test_a_monthly_whop_renewal_pays_a_month(granted):
    """A renewal is the same grant as the first cycle; Whop sends both as
    payment.succeeded and only `billing_reason` tells them apart."""
    await wi._dispatch_event(
        "payment.succeeded", _payment("subscription_cycle", "plan_creator")
    )
    assert granted == [
        (
            "user-1",
            billing.PLAN_CREDITS["creator"],
            "subscription_renewal",
            billing.CREDIT_VALIDITY_DAYS,
            "creator",
        )
    ]


@pytest.mark.asyncio
async def test_a_pack_bought_on_whop_still_lives_a_year(granted):
    """A pack was bought outright, not rented. Whop calls this `one_time`; the
    365-day window is the same promise the pricing page makes."""
    await wi._dispatch_event(
        "payment.succeeded",
        _payment(
            "one_time",
            "plan_credits_medium",
            metadata={"user_id": "user-1", "credit_package": "MEDIUM"},
        ),
    )
    assert granted == [
        (
            "user-1",
            billing.CREDIT_PACKAGES["MEDIUM"]["credits"],
            "credit_purchase",
            billing.PACK_CREDIT_VALIDITY_DAYS,
            None,
        )
    ]


@pytest.mark.asyncio
async def test_a_pack_that_lost_its_metadata_is_read_off_its_plan(granted):
    """A sale made from a link pasted into Whop's own storefront carries no
    metadata we wrote. The plan id still says which pack it was, and 12
    credits is the right answer for a $49 payment -- granting a subscription
    allowance instead would hand out 16 for it."""
    data = _payment("one_time", "plan_credits_medium", metadata={"user_id": "user-1"})
    await wi._dispatch_event("payment.succeeded", data)
    assert granted[0][1] == billing.CREDIT_PACKAGES["MEDIUM"]["credits"]
    assert granted[0][2] == "credit_purchase"


@pytest.mark.asyncio
async def test_a_renewal_with_no_metadata_is_found_by_its_membership(granted, monkeypatch):
    """Metadata is copied onto the membership at purchase, but the renewal two
    years later is only guaranteed to carry the membership id. The first
    payment wrote that id onto the profile precisely so this lookup can work."""
    async def _find(column, value, select="id,plan"):
        assert (column, value) == ("whop_membership_id", "mem_1")
        return {"id": "user-7", "plan": "pro"}

    monkeypatch.setattr(billing, "find_profile", _find)

    await wi._dispatch_event(
        "payment.succeeded",
        _payment("subscription_cycle", "plan_pro", metadata={}),
    )
    assert granted[0][0] == "user-7"
    assert granted[0][1] == billing.PLAN_CREDITS["pro"]


@pytest.mark.asyncio
async def test_a_payment_belonging_to_nobody_is_not_reported_as_credited(granted, monkeypatch):
    """There is no account to credit and the money has already moved. The one
    thing this must not do is grant credits to a guessed user, and the second
    thing is look like a success -- the operator has to be able to find this
    payment and fix it by hand."""
    async def _find(column, value, select="id,plan"):
        return None

    monkeypatch.setattr(billing, "find_profile", _find)

    result = await wi._dispatch_event(
        "payment.succeeded", _payment("subscription_cycle", "plan_pro", metadata={})
    )
    assert granted == []
    assert result["credited"] is False


@pytest.mark.asyncio
async def test_a_cancelled_whop_membership_keeps_the_packs_it_bought(monkeypatch):
    """Cancellation revokes the RENTED allowance and nothing else -- the same
    rule as Stripe, reached through the same `billing.end_subscription`, which
    is what leaves `credit_purchase` lots alone."""
    ended: list = []

    async def _find(column, value, select="id,plan"):
        return {"id": "user-9"}

    async def _end(user_id, column, value, clear_fields=None):
        ended.append((user_id, column, value))

    monkeypatch.setattr(billing, "find_profile", _find)
    monkeypatch.setattr(billing, "end_subscription", _end)

    await wi._dispatch_event("membership.went_invalid", {"id": "mem_1"})
    assert ended == [("user-9", "whop_membership_id", "mem_1")]


def test_the_two_processors_quote_the_same_allowances():
    """The point of `billing.py`. If these ever disagree, one set of customers
    is being paid a different allowance for the same money, and no test that
    looks at only one processor can see it."""
    import stripe_integration as si

    assert si.PLAN_CREDITS is billing.PLAN_CREDITS
    assert si.CREDIT_PACKAGES is billing.CREDIT_PACKAGES
    assert si.allowance_for("pro", annual=True) == wi.allowance_for("pro", annual=True)
