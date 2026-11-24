"""Job b054c5a8 ended with the supplier's own billing instruction on screen.

`Internal error: User is locked. Reason: Exhausted balance. Top up your balance
at fal.ai/dashboard/billing.` is addressed to us. The customer cannot act on it,
should not learn who the supplier is, and was already refunded.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from jobs import provider_balance_exhausted, user_facing_failure  # noqa: E402

LOCKED = RuntimeError(
    "User is locked. Reason: Exhausted balance. Top up your balance at "
    "fal.ai/dashboard/billing."
)


def test_the_customer_is_not_sent_to_our_suppliers_billing_page():
    message = user_facing_failure(LOCKED)
    assert "fal.ai" not in message and "balance" not in message.lower()
    assert "credits are back" in message


def test_the_operator_still_gets_the_real_cause_at_error(caplog):
    with caplog.at_level(logging.ERROR):
        user_facing_failure(LOCKED)
    assert "PROVIDER BALANCE EXHAUSTED" in caplog.text


def test_any_other_failure_is_reported_as_before():
    assert user_facing_failure(ValueError("boom")) == "Internal error: boom"
    assert not provider_balance_exhausted(ValueError("boom"))
