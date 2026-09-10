"""A payment that fails halfway must still be credited on Stripe's retry.

`handle_webhook` takes the idempotency mark BEFORE it does the work, which is
correct -- it is what stops two concurrent deliveries of one event granting the
credits twice. What it used to do was keep the mark when the work then failed.

The consequence is the quietest kind of money bug there is:

    1. Stripe delivers checkout.session.completed.
    2. The mark is written.
    3. Supabase times out granting the credits, and the handler raises.
    4. Stripe sees a 5xx and retries, exactly as designed.
    5. The retry finds the event already marked and returns 200
       "already_processed".
    6. Stripe's dashboard shows a delivered webhook. The customer paid and has
       nothing, and no log line anywhere says so.

Delivered logs show `POST /api/stripe-webhook 400` with no accompanying line
at all, which is what sent us looking at this path.
"""

import pytest
import stripe
from unittest.mock import patch

import stripe_integration as si


def _checkout_event(event_id: str) -> dict:
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "payment",
                "client_reference_id": "user-retry",
                "customer": "cus_retry",
                "subscription": None,
                "metadata": {"credit_package": "SMALL"},
            }
        },
    }


@pytest.mark.asyncio
async def test_a_handler_that_fails_gives_its_idempotency_mark_back():
    """The retry has to be allowed to do the work the first delivery did not."""
    marked = set()
    released = []
    attempts = {"n": 0}
    credited = []

    async def _mark(event_id):
        if event_id in marked:
            return False
        marked.add(event_id)
        return True

    async def _release(event_id):
        released.append(event_id)
        marked.discard(event_id)

    async def _add_credits(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("Supabase timed out")
        credited.append(kwargs.get("credits") or (args[1] if len(args) > 1 else None))

    event = _checkout_event("evt_retryable_001")

    with patch.object(si, "_mark_event_processed", side_effect=_mark), \
         patch.object(si, "_release_event_mark", side_effect=_release), \
         patch.object(si, "_add_credits_to_profile", side_effect=_add_credits), \
         patch.object(si, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret"), \
         patch("stripe_integration.stripe.Webhook.construct_event", return_value=event):

        # First delivery: the grant fails, so the caller must see the failure
        # (a 5xx is what makes Stripe retry at all).
        with pytest.raises(RuntimeError):
            await si.handle_webhook(b"payload", "sig")

        assert released == ["evt_retryable_001"], (
            "A failed handler kept its mark; Stripe's retry would be answered "
            "'already_processed' and the payment would never be credited."
        )

        # Second delivery: Stripe's retry, which now gets to do the work.
        result = await si.handle_webhook(b"payload", "sig")

    assert result.get("status") != "already_processed"
    assert len(credited) == 1, "The retry did not grant the credits."


@pytest.mark.asyncio
async def test_a_successful_handler_keeps_its_mark():
    """The fix must not reopen the duplicate-grant hole it sits on top of."""
    marked = set()
    released = []
    credited = []

    async def _mark(event_id):
        if event_id in marked:
            return False
        marked.add(event_id)
        return True

    async def _release(event_id):
        released.append(event_id)
        marked.discard(event_id)

    async def _add_credits(*args, **kwargs):
        credited.append(1)

    event = _checkout_event("evt_retryable_002")

    with patch.object(si, "_mark_event_processed", side_effect=_mark), \
         patch.object(si, "_release_event_mark", side_effect=_release), \
         patch.object(si, "_add_credits_to_profile", side_effect=_add_credits), \
         patch.object(si, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret"), \
         patch("stripe_integration.stripe.Webhook.construct_event", return_value=event):

        await si.handle_webhook(b"payload", "sig")
        second = await si.handle_webhook(b"payload", "sig")

    assert released == []
    assert second["status"] == "already_processed"
    assert len(credited) == 1


@pytest.mark.asyncio
async def test_an_unconfigured_secret_says_so_in_the_log(caplog):
    """The delivered access log showed a bare 400 and nothing else."""
    with patch.object(si, "STRIPE_WEBHOOK_SECRET", ""):
        with caplog.at_level("ERROR"):
            with pytest.raises(ValueError):
                await si.handle_webhook(b"payload", "sig")

    assert any(
        "STRIPE_WEBHOOK_SECRET" in record.message % record.args
        if record.args else "STRIPE_WEBHOOK_SECRET" in record.message
        for record in caplog.records
    ), "A rejected webhook must name its cause in the log, not only in the response body."


@pytest.mark.asyncio
async def test_a_bad_signature_says_so_in_the_log(caplog):
    """The other cause of a 400, and it needs a different action."""
    error = stripe.error.SignatureVerificationError("no match", "sig")

    with patch.object(si, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret"), \
         patch("stripe_integration.stripe.Webhook.construct_event", side_effect=error):
        with caplog.at_level("ERROR"):
            with pytest.raises(ValueError):
                await si.handle_webhook(b"payload", "sig")

    assert any("signature" in record.getMessage().lower() for record in caplog.records)
