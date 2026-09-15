"""One idempotency table, two processors, and the two ways that goes wrong.

`processed_stripe_events` has a single-column primary key. It now holds
Stripe's event ids and Whop's message ids, and both of those are opaque
strings chosen by somebody else. That leaves exactly two failure modes, and
they fail in opposite directions:

    COLLISION -- if the two namespaces were stored raw and ever produced the
    same string, whichever processor delivered second would be told "already
    processed" and a paid customer would be credited nothing.

    ORPHANING -- if Stripe's ids were prefixed to prevent that, every id
    already in the table would stop matching. A Stripe retry of an event that
    WAS handled would be treated as new and would grant its credits a second
    time.

So Whop's are prefixed and Stripe's stay bare, and this file pins that
asymmetry down, because it looks like an inconsistency somebody will
helpfully tidy up.

The last two tests cover the failure the Stripe handler was already fixed for
(`test_a_failed_webhook_is_retryable.py`), re-asked of the Whop handler: a
handler that raises must give its mark back, or the processor's retry is
answered "already processed" and the payment is lost with a green delivery in
the dashboard.
"""

import base64
import hashlib
import hmac
import json
import time

import pytest

import billing
import whop_integration as wi

SECRET = "ws_" + base64.b64encode(b"secret").decode()


def _headers(payload: bytes, msg_id: str) -> dict:
    timestamp = str(int(time.time()))
    key = list(wi._signing_keys(SECRET))[0]
    signed = b"%s.%s.%s" % (msg_id.encode(), timestamp.encode(), payload)
    digest = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": f"v1,{digest}",
    }


def test_a_stripe_event_id_is_stored_exactly_as_it_always_was():
    """Every id written before Whop existed was written bare. Prefixing them
    now would make each one unrecognised on its next retry."""
    assert billing.event_key("stripe", "evt_1") == "evt_1"


def test_a_whop_message_id_is_stored_in_its_own_namespace():
    """Two processors, one primary key. Nothing but the prefix guarantees that
    a Whop id can never be mistaken for a Stripe one."""
    assert billing.event_key("whop", "msg_1") == "whop:msg_1"
    assert billing.event_key("whop", "evt_1") != billing.event_key("stripe", "evt_1")


@pytest.mark.asyncio
async def test_a_redelivery_of_the_same_whop_event_grants_nothing_twice(monkeypatch):
    """Whop retries for about three days. The second delivery has to be a
    no-op, not a second Pro allowance."""
    monkeypatch.setattr(wi, "WHOP_WEBHOOK_SECRET", SECRET)
    seen: set = set()
    granted: list = []

    async def _mark(provider, event_id):
        key = billing.event_key(provider, event_id)
        if key in seen:
            return False
        seen.add(key)
        return True

    async def _grant(user_id, credits_delta, **kwargs):
        granted.append(credits_delta)

    monkeypatch.setattr(billing, "mark_event_processed", _mark)
    monkeypatch.setattr(billing, "grant_credits", _grant)
    monkeypatch.setenv("WHOP_PLAN_PRO", "plan_pro")

    body = json.dumps(
        {
            "type": "payment.succeeded",
            "data": {
                "id": "pay_1",
                "billing_reason": "subscription_cycle",
                "metadata": {"user_id": "user-1"},
                "plan": {"id": "plan_pro"},
                "membership": {"id": "mem_1"},
            },
        }
    ).encode()

    first = await wi.handle_webhook(body, _headers(body, "msg_1"))
    second = await wi.handle_webhook(body, _headers(body, "msg_1"))

    assert granted == [billing.PLAN_CREDITS["pro"]]
    assert first.get("credits") == billing.PLAN_CREDITS["pro"]
    assert second["status"] == "already_processed"


@pytest.mark.asyncio
async def test_a_whop_event_that_failed_halfway_is_retryable(monkeypatch):
    """The mark is taken before the work. When the work then raises, the mark
    must be released -- otherwise Whop's retry is answered 'already processed'
    and the customer who paid is never credited."""
    monkeypatch.setattr(wi, "WHOP_WEBHOOK_SECRET", SECRET)
    released: list = []

    async def _mark(provider, event_id):
        return True

    async def _release(provider, event_id):
        released.append((provider, event_id))

    async def _explode(*args, **kwargs):
        raise RuntimeError("Supabase timed out")

    monkeypatch.setattr(billing, "mark_event_processed", _mark)
    monkeypatch.setattr(billing, "release_event_mark", _release)
    monkeypatch.setattr(billing, "grant_credits", _explode)
    monkeypatch.setenv("WHOP_PLAN_PRO", "plan_pro")

    body = json.dumps(
        {
            "type": "payment.succeeded",
            "data": {
                "billing_reason": "subscription_cycle",
                "metadata": {"user_id": "user-1"},
                "plan": {"id": "plan_pro"},
            },
        }
    ).encode()

    with pytest.raises(RuntimeError):
        await wi.handle_webhook(body, _headers(body, "msg_7"))

    assert released == [("whop", "msg_7")]
