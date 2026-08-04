"""Credits expire 30 days after they are granted.

The balance used to be one scalar on profiles, which could not answer "when
does THIS credit die?". Two things fell out of that: a purchased pack lived
forever, and the renewal path compensated by OVERWRITING the balance with the
plan allowance -- destroying packs the user had paid for on top of their
subscription.

Credits are now issued as lots, each carrying its own expiry. The FIFO spend
and the expiry sweep live in SQL (supabase_migration.sql); these tests pin the
Python side that drives them, plus the invariants the SQL has to keep. They do
NOT execute the SQL -- there is no Postgres in this test environment.
"""

import os
import re
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import stripe_integration as si  # noqa: E402


def _migration() -> str:
    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "supabase_migration.sql"
    )
    with open(path, encoding="utf-8") as f:
        return f.read()


def _function_body(name: str) -> str:
    """Body of the LAST definition of `name` in the migration.

    The file is append-only -- it redefines objects as the schema evolves and
    is replayed top to bottom, so the final `create or replace` is the one
    that survives. Matching the first would test a superseded version.
    """
    bodies = re.findall(
        rf"create or replace function public\.{name}\b.*?\$\$(.*?)\$\$",
        _migration(),
        re.S,
    )
    assert bodies, f"{name}() not found in the migration"
    return bodies[-1]


# ── the 30 days has to mean the same thing on both sides ────────────────────


def test_python_and_sql_agree_on_the_validity_window():
    """The UI quotes CREDIT_VALIDITY_DAYS; the database is what actually
    expires the credit. If they drift, the page promises a window the
    product does not honour."""
    sql = _migration()
    match = re.search(
        r"create or replace function public\.credit_validity_days\(\)"
        r".*?select\s+(\d+)",
        sql,
        re.S,
    )
    assert match, "credit_validity_days() not found in the migration"
    assert int(match.group(1)) == si.CREDIT_VALIDITY_DAYS


def test_validity_is_thirty_days():
    assert si.CREDIT_VALIDITY_DAYS == 30


# ── grants land immediately, with an expiry attached ────────────────────────


class _FakeResponse:
    status_code = 200

    def json(self):
        return []


class _FakeClient:
    """Records the Supabase calls a webhook branch makes."""

    def __init__(self, *args, **kwargs):
        self.posts: list = []
        self.patches: list = []
        self.gets: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        self.posts.append((url, json))
        return _FakeResponse()

    async def patch(self, url, json=None, headers=None):
        self.patches.append((url, json))
        return _FakeResponse()

    async def get(self, url, params=None, headers=None):
        self.gets.append((url, params))
        return _FakeResponse()


def _install_fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(si.httpx, "AsyncClient", lambda *a, **k: client)
    monkeypatch.setattr(si, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(si, "SUPABASE_SERVICE_KEY", "service-key")
    return client


@pytest.mark.asyncio
async def test_a_purchase_is_granted_as_an_expiring_lot(monkeypatch):
    """'Hemen tanımlansın': the pack is spendable as soon as the webhook
    returns, and it carries the 30-day expiry with it."""
    client = _install_fake_client(monkeypatch)

    await si._add_credits_to_profile(
        user_id="user-1", credits_delta=12, reason="credit_purchase"
    )

    grants = [body for url, body in client.posts if url.endswith("/rpc/grant_credits")]
    assert len(grants) == 1, client.posts
    assert grants[0]["p_amount"] == 12
    assert grants[0]["p_reason"] == "credit_purchase"
    assert grants[0]["p_days"] == si.CREDIT_VALIDITY_DAYS


@pytest.mark.asyncio
async def test_grant_never_overwrites_the_balance(monkeypatch):
    """The old read-then-write set an absolute number, so a grant racing a
    spend could resurrect spent credits. Nothing may PATCH credits now."""
    client = _install_fake_client(monkeypatch)

    await si._add_credits_to_profile(
        user_id="user-1", credits_delta=16, plan="creator", reason="subscription_renewal"
    )

    for _url, body in client.patches:
        assert "credits" not in (body or {}), body


# ── renewal tops up; it no longer wipes what the user bought ────────────────


def _renewal_event(customer="cus_1"):
    return {
        "id": "evt_renewal_1",
        "type": "invoice.paid",
        "data": {"object": {"billing_reason": "subscription_cycle", "customer": customer}},
    }


@pytest.mark.asyncio
async def test_renewal_grants_a_new_lot_instead_of_resetting(monkeypatch):
    """A renewal must ADD the month's allowance. The old code overwrote the
    balance, so a user who bought a 26-credit pack mid-month lost it at the
    next invoice."""
    monkeypatch.setattr(si, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(si, "SUPABASE_SERVICE_KEY", "service-key")

    granted: list = []
    patched: list = []

    async def _fake_grant(user_id, credits_delta, **kwargs):
        granted.append((user_id, credits_delta, kwargs.get("reason")))

    class _ProfileLookupClient(_FakeClient):
        async def get(self, url, params=None, headers=None):
            self.gets.append((url, params))

            class _R:
                status_code = 200

                def json(self):
                    return [{"id": "user-1", "plan": "pro"}]

            return _R()

        async def patch(self, url, json=None, headers=None):
            patched.append((url, json))
            return _FakeResponse()

    monkeypatch.setattr(si.httpx, "AsyncClient", lambda *a, **k: _ProfileLookupClient())

    async def _fake_mark(event_id):
        return True

    with patch.object(si, "_mark_event_processed", side_effect=_fake_mark), \
         patch.object(si, "_add_credits_to_profile", side_effect=_fake_grant), \
         patch.object(si, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe_integration.stripe.Webhook.construct_event",
               return_value=_renewal_event()):
        await si.handle_webhook(b"payload", "sig")

    assert granted == [("user-1", si.PLAN_CREDITS["pro"], "subscription_renewal")]
    for _url, body in patched:
        assert "credits" not in (body or {}), body


# ── cancelling ends the rental, not the purchase ────────────────────────────


@pytest.mark.asyncio
async def test_cancellation_revokes_only_subscription_credits(monkeypatch):
    """Unused allowance is rented and goes back. A pack was bought outright
    and runs out its own 30 days. The old code set credits to a flat 3,
    which destroyed both."""
    monkeypatch.setattr(si, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(si, "SUPABASE_SERVICE_KEY", "service-key")

    client = _FakeClient()

    class _WithProfile(_FakeClient):
        async def get(self, url, params=None, headers=None):
            client.gets.append((url, params))

            class _R:
                status_code = 200

                def json(self):
                    return [{"id": "user-1"}]

            return _R()

        async def post(self, url, json=None, headers=None):
            client.posts.append((url, json))
            return _FakeResponse()

        async def patch(self, url, json=None, headers=None):
            client.patches.append((url, json))
            return _FakeResponse()

    monkeypatch.setattr(si.httpx, "AsyncClient", lambda *a, **k: _WithProfile())

    async def _fake_mark(event_id):
        return True

    event = {
        "id": "evt_cancel_1",
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_1"}},
    }

    with patch.object(si, "_mark_event_processed", side_effect=_fake_mark), \
         patch.object(si, "STRIPE_WEBHOOK_SECRET", "whsec_test"), \
         patch("stripe_integration.stripe.Webhook.construct_event", return_value=event):
        await si.handle_webhook(b"payload", "sig")

    revokes = [
        body for url, body in client.posts
        if url.endswith("/rpc/revoke_subscription_credits")
    ]
    assert revokes == [{"p_user_id": "user-1"}], client.posts

    # The plan drops to free, but the balance is not stamped with a number.
    assert client.patches, "the profile should still be downgraded to free"
    for _url, body in client.patches:
        assert body.get("plan") == "free"
        assert "credits" not in body, body


# ── the SQL keeps the invariants the feature rests on ───────────────────────


def test_balance_ignores_expired_lots():
    """Expiry must bite at read time. If it only happened in the sweep, a
    user could spend lapsed credits whenever the cron was late."""
    assert "expires_at > now()" in _function_body("credit_balance")


def test_deduction_spends_the_soonest_to_expire_first():
    """Spending a long-dated lot while a nearly-dead one sits unused would
    burn credits the user could still have used."""
    body = _function_body("deduct_credits")
    assert "order by expires_at asc" in body
    assert "expires_at > now()" in body
    # Concurrent generations must not both pass the balance check.
    assert "for update" in body


def test_deduct_credits_still_reports_insufficient_as_minus_one():
    """server/api.py:_deduct_credits treats -1 as 'not enough' and anything
    else as success. The FIFO rewrite must keep that contract."""
    assert "return -1" in _function_body("deduct_credits")


def test_revoke_leaves_purchased_packs_alone():
    body = _function_body("revoke_subscription_credits")
    assert "reason = 'subscription_renewal'" in body
    assert "credit_purchase" not in body


def test_existing_balances_are_backfilled_into_lots():
    """Without the backfill, switching the balance read over to credit_lots
    would show every existing user a balance of zero."""
    sql = _migration()
    assert re.search(
        r"insert into public\.credit_lots.*?from public\.profiles", sql, re.S
    ), "no backfill of existing profiles.credits into credit_lots"
