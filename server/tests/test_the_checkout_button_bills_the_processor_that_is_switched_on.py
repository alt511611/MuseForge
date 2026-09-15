"""`PAYMENT_PROVIDER` decides who takes the money, and nothing else does.

The client sends one request to `/api/create-checkout-session` and follows
whatever URL comes back. It does not know, and must not have to know, which
processor is live -- that is the whole reason MuseForge can sell through Whop
now (merchant of record, no company required) and move to Stripe later without
shipping a frontend.

Which makes the switch itself the dangerous part. The failure mode is the one
`tools/provider_choice` was written for after delivered job 1ac6d945-b53: an
operator sets a variable, believes the deployment moved, and it did not. Here
that is not a render billed to the wrong vendor -- it is a customer sent to a
checkout for an account that cannot be paid out, or a Stripe checkout raised
by a seller with no company to receive it.

So: unset means Stripe (every existing deployment is already running it, and a
payments processor must never change because a variable was missing), `whop`
means Whop, and a misspelling is loud rather than silently Stripe.
"""

import os
import sys
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api as _api  # noqa: E402
import billing  # noqa: E402
import stripe_integration as si  # noqa: E402
import whop_integration as wi  # noqa: E402
from auth import AuthUser  # noqa: E402

client = TestClient(_api.app)


@contextmanager
def _auth_as(user_id="user-1", email="buyer@example.com"):
    async def _fake_user():
        return AuthUser(user_id, email)

    _api.app.dependency_overrides[_api.get_current_user] = _fake_user
    try:
        yield
    finally:
        _api.app.dependency_overrides.pop(_api.get_current_user, None)


@pytest.fixture
def checkouts(monkeypatch):
    """Records which processor was asked to build a link, and with what."""
    calls: list = []

    async def _whop(plan_id, user_id, user_email="", success_url="", metadata=None):
        calls.append(("whop", plan_id, user_id, metadata))
        return "https://whop.com/checkout/plan_x"

    async def _stripe(price_id, user_id, user_email, success_url, cancel_url,
                      mode="subscription", metadata=None):
        calls.append(("stripe", price_id, user_id, metadata))
        return "https://checkout.stripe.com/c/pay/x"

    monkeypatch.setattr(wi, "create_checkout_session", _whop)
    monkeypatch.setattr(si, "create_checkout_session", _stripe)
    return calls


def _subscribe(plan="pro", interval="annual"):
    return client.post(
        "/api/create-checkout-session",
        json={
            "plan": plan,
            "interval": interval,
            "success_url": "https://museforge.app/pricing?success=1",
            "cancel_url": "https://museforge.app/pricing?cancelled=1",
        },
    )


def test_with_whop_switched_on_the_customer_is_sent_to_whop(monkeypatch, checkouts):
    monkeypatch.setenv("PAYMENT_PROVIDER", "whop")
    monkeypatch.setenv("WHOP_PLAN_PRO_ANNUAL", "plan_pro_annual")

    with _auth_as():
        resp = _subscribe()

    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://whop.com/")
    assert checkouts == [("whop", "plan_pro_annual", "user-1", None)]


def test_a_dashboard_paste_with_a_stray_newline_still_selects_whop(monkeypatch, checkouts):
    """The exact shape of the bug this normalisation exists for: the value is
    right, the whitespace is not, and an unnormalised compare sends the
    customer to the processor the operator was trying to leave."""
    monkeypatch.setenv("PAYMENT_PROVIDER", " Whop\n")
    monkeypatch.setenv("WHOP_PLAN_PRO_ANNUAL", "plan_pro_annual")

    with _auth_as():
        resp = _subscribe()

    assert resp.json()["url"].startswith("https://whop.com/")


def test_with_nothing_set_the_money_still_goes_where_it_always_went(monkeypatch, checkouts):
    monkeypatch.delenv("PAYMENT_PROVIDER", raising=False)
    monkeypatch.setenv("STRIPE_PRICE_PRO_ANNUAL", "price_pro_annual")

    with _auth_as():
        resp = _subscribe()

    assert checkouts == [("stripe", "price_pro_annual", "user-1", None)]


def test_a_plan_whop_has_never_heard_of_is_a_400_not_a_broken_link(monkeypatch, checkouts):
    """An unconfigured plan id must fail where the operator can see it. The
    alternative -- a checkout link built from an empty plan -- is a 404 the
    CUSTOMER discovers, at the moment they were trying to pay."""
    monkeypatch.setenv("PAYMENT_PROVIDER", "whop")
    monkeypatch.delenv("WHOP_PLAN_PRO_ANNUAL", raising=False)

    with _auth_as():
        resp = _subscribe()

    assert resp.status_code == 400
    assert "WHOP_PLAN_PRO_ANNUAL" in resp.json()["detail"]
    assert checkouts == []


def test_a_pack_bought_on_whop_carries_the_pack_key_to_the_webhook(monkeypatch, checkouts):
    """Whop has no `client_reference_id` and no line items to read back. The
    metadata written here is the only record of WHICH pack was bought, and the
    webhook grants credits from it."""
    monkeypatch.setenv("PAYMENT_PROVIDER", "whop")
    monkeypatch.setenv("WHOP_PLAN_CREDITS_LARGE", "plan_credits_large")

    with _auth_as():
        resp = client.post(
            "/api/buy-credits",
            json={
                "package": "LARGE",
                "success_url": "https://museforge.app/dashboard?success=1",
                "cancel_url": "https://museforge.app/dashboard",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["credits"] == billing.CREDIT_PACKAGES["LARGE"]["credits"]
    assert checkouts == [("whop", "plan_credits_large", "user-1", {"credit_package": "LARGE"})]


def test_the_manage_subscription_button_answers_in_the_same_shape(monkeypatch):
    """Stripe returns a signed portal session; Whop has none to create and the
    answer is the customer's own orders page. Both are `{"url": ...}`, which is
    what lets the existing dashboard button go on working unchanged."""
    monkeypatch.setenv("PAYMENT_PROVIDER", "whop")

    with _auth_as():
        resp = client.post(
            "/api/stripe-portal", json={"return_url": "https://museforge.app/dashboard"}
        )

    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://whop.com/orders")
