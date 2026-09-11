"""Three files say what a plan's monthly credits are, and one of them was wrong.

The grant is made in two places and displayed in a third:

    server/stripe_integration.py   PLAN_CREDITS        -- what Stripe's webhook grants
    supabase_migration.sql         public.plan_limits  -- what the database advertises
    client/lib/credits.js          PLAN_MONTHLY_CREDITS -- what the banner measures against

When the allowances moved from 25/55 to 16/36, the first two were updated --
the SQL view even carries a comment saying the old numbers were retired -- and
the client was not. Nothing broke loudly. The low-credit banner simply started
measuring a creator's balance against an allowance half again as large as the
one they get, so the warning fired at the wrong moment, in a UI nobody
cross-checks against a Python constant.

This is the check that would have caught it. It does not care what the numbers
ARE; it cares that the three agree.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from stripe_integration import PLAN_CREDITS  # noqa: E402

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def _client_allowances():
    """PLAN_MONTHLY_CREDITS out of client/lib/credits.js."""
    path = os.path.join(_ROOT, "client", "lib", "credits.js")
    source = open(path, encoding="utf-8").read()
    body = re.search(
        r"PLAN_MONTHLY_CREDITS\s*=\s*\{(.*?)\}", source, re.S
    )
    assert body, "client/lib/credits.js no longer declares PLAN_MONTHLY_CREDITS"
    return {
        name: int(amount)
        for name, amount in re.findall(r"(\w+)\s*:\s*(\d+)", body.group(1))
    }


def _view_allowances():
    """monthly_credits out of the public.plan_limits view, as last defined."""
    path = os.path.join(_ROOT, "supabase_migration.sql")
    source = open(path, encoding="utf-8").read()
    # The migration is a script: the view is redefined as the ladder changes,
    # so the LAST definition is the one the database ends up with.
    blocks = re.findall(
        r"create or replace view public\.plan_limits as(.*?);", source, re.S
    )
    assert blocks, "supabase_migration.sql no longer defines public.plan_limits"
    last = blocks[-1]
    named = dict(
        (plan, int(credits))
        for plan, credits in re.findall(
            r"'(\w+)'\s*(?:as plan)?\s*,\s*(\d+)", last
        )
    )
    # Rows after the first are written positionally: `select 'creator', 16, ...`
    return named


@pytest.mark.parametrize("plan", sorted(PLAN_CREDITS))
def test_the_paid_allowance_is_the_same_number_everywhere(plan):
    granted = PLAN_CREDITS[plan]

    assert _client_allowances().get(plan) == granted, (
        f"client/lib/credits.js says {_client_allowances().get(plan)} credits for "
        f"{plan}; Stripe grants {granted}. The low-credit banner measures "
        "against the client's number, so a stale copy warns at the wrong balance."
    )
    assert _view_allowances().get(plan) == granted, (
        f"public.plan_limits advertises {_view_allowances().get(plan)} credits "
        f"for {plan}; Stripe grants {granted}."
    )


def test_the_free_plan_agrees_with_itself():
    """Free is granted by the database, not by Stripe, so the SQL view leads."""
    free = _view_allowances().get("free")

    assert free is not None, "public.plan_limits no longer carries the free plan"
    assert _client_allowances().get("free") == free
    assert "free" not in PLAN_CREDITS, (
        "PLAN_CREDITS is what a Stripe renewal grants; a free plan has no "
        "renewal, and putting it here is how a free account gets billed for"
    )


def test_every_plan_the_client_knows_about_is_a_plan():
    """No fourth tier surviving in the UI after it left the product."""
    known = set(_view_allowances())

    assert set(_client_allowances()) <= known, (
        "the client offers a plan the database has never heard of"
    )
