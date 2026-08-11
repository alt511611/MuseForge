"""Annual billing: its own Stripe Price, its own allowance, its own expiry.

Annual is the offer the pricing page leads with, which puts three things on the
money path that monthly never exercised: a second Price per plan, a renewal
event that fires once a year instead of twelve times, and an allowance the
customer has already paid for in full.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import stripe_integration as si  # noqa: E402


@pytest.fixture
def prices(monkeypatch):
    monkeypatch.setenv("STRIPE_PRICE_CREATOR", "price_creator_monthly")
    monkeypatch.setenv("STRIPE_PRICE_CREATOR_ANNUAL", "price_creator_annual")
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_monthly")
    monkeypatch.setenv("STRIPE_PRICE_PRO_ANNUAL", "price_pro_annual")


# ── choosing a price ────────────────────────────────────────────────────────


def test_annual_is_the_default_interval(prices):
    assert si.get_price_id("pro") == "price_pro_annual"
    assert si.get_price_id("pro", "monthly") == "price_pro_monthly"


def test_missing_annual_price_does_not_silently_bill_monthly(monkeypatch):
    """Falling back would put a customer who chose "billed yearly" on a
    monthly cycle at a monthly amount. That is a billing error, not a
    degraded experience -- the API turns the None into a visible 400."""
    monkeypatch.setenv("STRIPE_PRICE_PRO", "price_pro_monthly")
    monkeypatch.delenv("STRIPE_PRICE_PRO_ANNUAL", raising=False)
    assert si.get_price_id("pro", "annual") is None


# ── recognising a price on the way back in ──────────────────────────────────


def test_annual_pro_is_provisioned_as_pro_not_creator(prices):
    """The webhook used to compare against STRIPE_PRICE_PRO alone, so an
    annual Pro subscriber matched nothing and fell through to Creator --
    the more expensive plan granting the smaller allowance."""
    assert si.plan_for_price_id("price_pro_annual") == "pro"
    assert si.plan_for_price_id("price_pro_monthly") == "pro"
    assert si.plan_for_price_id("price_creator_annual") == "creator"
    assert si.plan_for_price_id("price_unknown") is None


def test_only_annual_prices_read_as_annual(prices):
    assert si.is_annual_price("price_pro_annual") is True
    assert si.is_annual_price("price_pro_monthly") is False
    assert si.is_annual_price("") is False


# ── what a cycle actually grants ────────────────────────────────────────────


def test_annual_grants_the_whole_year_with_a_year_to_spend_it():
    credits, days = si.allowance_for("pro", annual=True)
    assert credits == si.PLAN_CREDITS["pro"] * 12
    assert days == si.ANNUAL_CREDIT_VALIDITY_DAYS


def test_monthly_is_unchanged():
    assert si.allowance_for("pro", annual=False) == (
        si.PLAN_CREDITS["pro"],
        si.CREDIT_VALIDITY_DAYS,
    )


# ── the renewal path ────────────────────────────────────────────────────────


class _Response:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _ProfileClient:
    def __init__(self, plan="pro"):
        self.plan = plan
        self.posts: list = []
        self.patches: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None, headers=None):
        return _Response([{"id": "user-1", "plan": self.plan}])

    async def post(self, url, json=None, headers=None):
        self.posts.append((url, json))
        return _Response([])

    async def patch(self, url, json=None, headers=None):
        self.patches.append((url, json))
        return _Response([])


def _renewal_event(price_id):
    return {
        "id": f"evt_renewal_{price_id}",
        "type": "invoice.paid",
        "data": {
            "object": {
                "billing_reason": "subscription_cycle",
                "customer": "cus_1",
                "lines": {"data": [{"price": {"id": price_id}}]},
            }
        },
    }


async def _run_renewal(monkeypatch, price_id):
    monkeypatch.setattr(si, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(si, "SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(si.httpx, "AsyncClient", lambda *a, **k: _ProfileClient())

    granted: list = []

    async def _fake_grant(user_id, credits_delta, **kwargs):
        granted.append((credits_delta, kwargs.get("validity_days")))

    async def _fake_mark(event_id):
        return True

    with patch.object(si, "_mark_event_processed", side_effect=_fake_mark), \
         patch.object(si, "_add_credits_to_profile", side_effect=_fake_grant), \
         patch.object(si, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe_integration.stripe.Webhook.construct_event",
               return_value=_renewal_event(price_id)):
        await si.handle_webhook(b"payload", "sig")
    return granted


@pytest.mark.asyncio
async def test_annual_renewal_pays_the_year_not_a_month(prices, monkeypatch):
    """An annual invoice fires once a year. Paying it a single month's
    allowance on a 30-day fuse would strand eleven twelfths of a year the
    customer has already been charged for."""
    granted = await _run_renewal(monkeypatch, "price_pro_annual")
    assert granted == [(si.PLAN_CREDITS["pro"] * 12, si.ANNUAL_CREDIT_VALIDITY_DAYS)]


@pytest.mark.asyncio
async def test_monthly_renewal_is_untouched(prices, monkeypatch):
    granted = await _run_renewal(monkeypatch, "price_pro_monthly")
    assert granted == [(si.PLAN_CREDITS["pro"], si.CREDIT_VALIDITY_DAYS)]


@pytest.mark.asyncio
async def test_renewal_without_a_recognisable_price_falls_back_to_the_profile(
    prices, monkeypatch
):
    """Stripe's invoice shape has changed before. An unrecognised line must
    still renew the customer on their recorded plan rather than granting
    nothing."""
    granted = await _run_renewal(monkeypatch, "price_from_the_future")
    assert granted == [(si.PLAN_CREDITS["pro"], si.CREDIT_VALIDITY_DAYS)]


# ── checkout ────────────────────────────────────────────────────────────────


def test_checkout_defaults_to_annual():
    from api import CheckoutRequest

    req = CheckoutRequest(plan="pro", success_url="https://x/s", cancel_url="https://x/c")
    assert req.interval == "annual"


def test_checkout_rejects_an_unknown_interval():
    from pydantic import ValidationError

    from api import CheckoutRequest

    with pytest.raises(ValidationError):
        CheckoutRequest(
            plan="pro",
            success_url="https://x/s",
            cancel_url="https://x/c",
            interval="weekly",
        )
