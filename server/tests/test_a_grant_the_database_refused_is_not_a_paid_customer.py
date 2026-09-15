"""A credit grant that Supabase rejected must not be reported as a sale served.

Found on the live database on 15 September 2026, while wiring Whop up: the
project had `profiles`, `credit_ledger` and `processed_stripe_events`, but
`credit_lots` and every one of the credit RPCs -- `grant_credits`,
`deduct_credits`, `credit_balance`, `revoke_subscription_credits` -- were
missing. `supabase_migration.sql` had never been applied in full.

On that database the grant call answers:

    404 {"code":"PGRST202","message":"Could not find the function
         public.grant_credits(...) in the schema cache"}

and the code did `await client.post(...)` without looking at the response. So
the webhook handler returned 200, the processor recorded a successful
delivery, and the customer's money was taken with nothing to show for it. No
exception, no log line, no retry -- the only way to discover it is a customer
complaining.

The fix is small and the argument for it is not: an uncredited payment has to
be LOUD, because the retry machinery already knows how to fix a loud one. The
handler releases its idempotency mark and answers 5xx, the processor
redelivers for days, and the payment is credited the moment the migration
lands. The test below is therefore about what happens after the failure as
much as at it.
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


def _signed_headers(payload: bytes, msg_id: str = "msg_1") -> dict:
    timestamp = str(int(time.time()))
    key = list(wi._signing_keys(SECRET))[0]
    signed = b"%s.%s.%s" % (msg_id.encode(), timestamp.encode(), payload)
    digest = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {
        "webhook-id": msg_id,
        "webhook-timestamp": timestamp,
        "webhook-signature": f"v1,{digest}",
    }


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text

    def json(self):
        return []


class _RefusingClient:
    """Supabase as it answers on a database missing the migration."""

    def __init__(self):
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        self.posts.append(url)
        return _Resp(
            404,
            '{"code":"PGRST202","message":"Could not find the function '
            'public.grant_credits(p_amount, p_days, p_reason, p_user_id) '
            'in the schema cache"}',
        )

    async def patch(self, url, json=None, headers=None):
        return _Resp(204)

    async def get(self, url, params=None, headers=None):
        return _Resp(200)


@pytest.fixture
def refusing(monkeypatch):
    client = _RefusingClient()
    monkeypatch.setattr(billing, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(billing.httpx, "AsyncClient", lambda *a, **k: client)
    return client


@pytest.mark.asyncio
async def test_a_grant_that_did_not_happen_raises(refusing):
    """The 404 names the missing function; the error carries it through so the
    operator reads the cause rather than 'webhook failed'."""
    with pytest.raises(RuntimeError, match="grant_credits"):
        await billing.grant_credits("user-1", 36, reason="subscription_renewal")


@pytest.mark.asyncio
async def test_the_profile_is_not_upgraded_on_credits_that_never_landed(refusing):
    """Order matters. If the plan were written before the grant was checked,
    a customer on a database missing the migration would show as Pro with a
    zero balance -- paid, upgraded, and unable to render anything."""
    with pytest.raises(RuntimeError):
        await billing.grant_credits("user-1", 36, plan="pro")

    assert not any("profiles" in url for url in refusing.posts)


@pytest.mark.asyncio
async def test_the_payment_stays_retryable(refusing, monkeypatch):
    """The whole point of raising. The mark is released and the exception
    reaches the endpoint, which answers 5xx -- so the processor redelivers and
    the payment is credited by a retry once the migration is applied, instead
    of by hand from a spreadsheet."""
    released: list = []

    async def _mark(provider, event_id):
        return True

    async def _release(provider, event_id):
        released.append(event_id)

    monkeypatch.setattr(billing, "mark_event_processed", _mark)
    monkeypatch.setattr(billing, "release_event_mark", _release)
    monkeypatch.setattr(wi, "WHOP_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("WHOP_PLAN_PRO", "plan_pro")

    body = json.dumps(
        {
            "type": "payment.succeeded",
            "data": {
                "id": "pay_1",
                "billing_reason": "subscription_cycle",
                "metadata": {"user_id": "user-1"},
                "plan": {"id": "plan_pro"},
            },
        }
    ).encode()

    with pytest.raises(RuntimeError, match="grant_credits"):
        await wi.handle_webhook(body, _signed_headers(body))

    assert released == ["msg_1"]
