"""The Whop endpoint is a public URL that hands out credits.

Anyone can POST to `/api/whop-webhook`. The only thing standing between that
and free subscriptions is the signature, so this file is about the four ways
that check can be got wrong, each of which is worth exactly one fraudulent
membership to whoever finds it:

    1. Not checking at all when the secret is unset (fail-open).
    2. Checking a re-serialised body instead of the raw bytes -- which fails
       every REAL delivery while a forged one is no easier to detect.
    3. Accepting a signature forever, so one captured delivery can be replayed
       into an unlimited number of grants.
    4. Guessing wrong about how the `ws_` secret derives its key, which is the
       one mistake that looks like a Whop outage rather than a bug here: every
       payment rejected, nothing in the log but 400s.

`_signing_keys` answers (4) by accepting any of the three plausible
derivations. The last test is the argument that this is not a weakened check:
a body signed with a DIFFERENT secret is still rejected under all three.
"""

import base64
import hashlib
import hmac
import json
import time

import pytest

import whop_integration as wi

SECRET = "ws_" + base64.b64encode(b"a-real-whop-secret").decode()


def _sign(payload: bytes, secret: str, msg_id: str = "msg_1", timestamp: int = None,
          key_index: int = 0) -> dict:
    """Headers Whop would send for this body, signed the way it signs them."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    key = list(wi._signing_keys(secret))[key_index]
    signed = b"%s.%s.%s" % (msg_id.encode(), str(timestamp).encode(), payload)
    digest = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": str(timestamp),
        "webhook-signature": f"v1,{digest}",
    }


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(wi, "WHOP_WEBHOOK_SECRET", SECRET)


def test_a_signed_delivery_is_accepted_however_the_key_was_derived():
    """Whop's own SDK and the Standard Webhooks reference disagree about
    whether the `ws_` prefix is stripped and base64-decoded. Being wrong costs
    every payment for as long as it takes to notice, so all three are
    accepted."""
    body = json.dumps({"type": "payment.succeeded", "data": {}}).encode()
    for key_index in range(len(list(wi._signing_keys(SECRET)))):
        event = wi.verify_webhook(body, _sign(body, SECRET, key_index=key_index))
        assert event["type"] == "payment.succeeded"


def test_the_id_that_the_retry_is_recognised_by_travels_in_the_header():
    """Whop puts the message id in `webhook-id`, not in the body. The
    idempotency table is keyed on it, so `verify_webhook` has to move it where
    the handler looks -- otherwise every delivery is a new event and every
    retry grants the credits again."""
    body = b'{"type": "payment.succeeded", "data": {}}'
    event = wi.verify_webhook(body, _sign(body, SECRET, msg_id="msg_42"))
    assert event["id"] == "msg_42"


def test_a_body_changed_after_signing_is_rejected():
    """One byte. This is also why `api.py` passes `await request.body()` and
    never a re-serialised dict: JSON round-tripping changes whitespace, and
    the digest is over the bytes."""
    body = b'{"type": "payment.succeeded", "data": {"id": "pay_1"}}'
    headers = _sign(body, SECRET)
    with pytest.raises(ValueError, match="signature"):
        wi.verify_webhook(body.replace(b"pay_1", b"pay_2"), headers)


def test_a_signature_from_another_secret_is_rejected():
    """The three key derivations are three ways to phrase OUR secret, not
    three chances for someone else's."""
    body = b'{"type": "payment.succeeded", "data": {}}'
    forged = _sign(body, "ws_" + base64.b64encode(b"not-our-secret").decode())
    with pytest.raises(ValueError, match="signature"):
        wi.verify_webhook(body, forged)


def test_yesterdays_delivery_cannot_be_replayed_today():
    """A signature with no freshness window is a coupon: capture one delivery
    and it grants credits again every time it is resent."""
    body = b'{"type": "payment.succeeded", "data": {}}'
    stale = _sign(body, SECRET, timestamp=int(time.time()) - 86400)
    with pytest.raises(ValueError, match="replay window"):
        wi.verify_webhook(body, stale)


def test_an_unsigned_delivery_with_no_secret_configured_is_not_trusted(monkeypatch):
    """The deployment that forgot WHOP_WEBHOOK_SECRET must reject everything
    rather than credit everything -- and must say WHICH of the two reasons it
    rejected for, because a 400 in an access log cannot be told apart from a
    port scan."""
    monkeypatch.setattr(wi, "WHOP_WEBHOOK_SECRET", "")
    with pytest.raises(ValueError, match="WHOP_WEBHOOK_SECRET"):
        wi.verify_webhook(b"{}", {"webhook-id": "msg_1"})


def test_headers_are_read_however_a_proxy_capitalised_them():
    """Render terminates TLS in front of the app and normalises header case on
    the way through. Reading `Webhook-Id` as absent would reject every real
    delivery in production while every test passed."""
    body = b'{"type": "payment.succeeded", "data": {}}'
    headers = {k.title(): v for k, v in _sign(body, SECRET).items()}
    assert wi.verify_webhook(body, headers)["type"] == "payment.succeeded"
