"""Pricing ladder coherence and unit economics.

Prices and credit allocations live in three places that must agree: the
Stripe-facing constants here, the pricing page the customer reads, and the
Stripe dashboard itself (outside the repo). These tests pin the two that ARE
in the repo, plus the structural rules a ladder has to satisfy to make sense.

The margin figures use the provider's real, linear rate: $0.11 per generated
second, and one credit buys SECONDS_PER_CREDIT seconds.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.second_budget import SECONDS_PER_CREDIT  # noqa: E402
from stripe_integration import CREDIT_PACKAGES, PLAN_CREDITS  # noqa: E402

KLING_PER_SECOND = 0.11
FIXED_PER_SCENE = 0.067  # frame + storyboard call + amortised portraits
CREDIT_COST = SECONDS_PER_CREDIT * KLING_PER_SECOND + FIXED_PER_SCENE

#: What the pricing page shows. Kept here so a change on one side without the
#: other fails loudly instead of shipping a page that lies about the product.
PLAN_PRICES = {"creator": 59, "pro": 129}
PACK_PRICES = {"SMALL": 19, "MEDIUM": 49, "LARGE": 99}

#: Healthy band for generative-AI SaaS. Below this, scale hurts; above it,
#: the price stops being defensible against running the models directly.
MIN_MARGIN = 65.0
MAX_MARGIN = 85.0


def _margin(price, credits):
    rate = price / credits
    return (rate - CREDIT_COST) / rate * 100


# --- every product clears the margin floor ------------------------------


@pytest.mark.parametrize("plan", sorted(PLAN_CREDITS))
def test_subscription_margin_is_healthy(plan):
    margin = _margin(PLAN_PRICES[plan], PLAN_CREDITS[plan])
    assert MIN_MARGIN <= margin <= MAX_MARGIN, f"{plan}: {margin:.1f}%"


@pytest.mark.parametrize("pack", sorted(CREDIT_PACKAGES))
def test_pack_margin_is_healthy(pack):
    margin = _margin(PACK_PRICES[pack], CREDIT_PACKAGES[pack]["credits"])
    assert MIN_MARGIN <= margin <= MAX_MARGIN, f"{pack}: {margin:.1f}%"


# --- the ladder has to make sense ---------------------------------------


def test_every_plan_can_render_one_full_length_drama():
    """A plan whose monthly credits fall below its own scene ceiling sells a
    maximum length the customer cannot actually reach."""
    from api import PLAN_MAX_SCENES

    for plan, credits in PLAN_CREDITS.items():
        assert credits >= PLAN_MAX_SCENES[plan], (
            f"{plan} includes {credits} credits but allows "
            f"{PLAN_MAX_SCENES[plan]}-scene dramas"
        )


def test_higher_tier_is_better_value_per_credit():
    creator = PLAN_PRICES["creator"] / PLAN_CREDITS["creator"]
    pro = PLAN_PRICES["pro"] / PLAN_CREDITS["pro"]
    assert pro < creator, f"Pro ${pro:.2f}/credit is worse than Creator ${creator:.2f}"


def test_packs_cost_more_per_credit_than_subscribing():
    """One-off packs buy flexibility, not commitment -- if they were cheaper
    per credit, the subscription would have no reason to exist."""
    best_subscription = min(
        PLAN_PRICES[p] / PLAN_CREDITS[p] for p in PLAN_CREDITS
    )
    for pack, price in PACK_PRICES.items():
        rate = price / CREDIT_PACKAGES[pack]["credits"]
        assert rate > best_subscription, f"{pack} ${rate:.2f} <= sub ${best_subscription:.2f}"


def test_bigger_packs_are_better_value():
    rates = [
        PACK_PRICES[p] / CREDIT_PACKAGES[p]["credits"]
        for p in ("SMALL", "MEDIUM", "LARGE")
    ]
    assert rates == sorted(rates, reverse=True), rates


# --- the page and the code must agree -----------------------------------


def _pricing_page():
    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "client", "app", "pricing", "page.js"
    )
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_pricing_page_shows_the_credits_the_code_grants():
    """The page is the promise; stripe_integration is what actually lands in
    the account. A mismatch charges someone for credits they never receive."""
    page = _pricing_page()
    for credits in (PLAN_CREDITS["creator"], PLAN_CREDITS["pro"]):
        assert re.search(rf"credits:\s*{credits}\b", page), credits
    for pack in CREDIT_PACKAGES:
        assert re.search(
            rf'key:\s*"{pack}".*?credits:\s*{CREDIT_PACKAGES[pack]["credits"]}\b',
            page,
        ), pack


def test_pricing_page_shows_the_expected_prices():
    page = _pricing_page()
    for price in list(PLAN_PRICES.values()) + list(PACK_PRICES.values()):
        assert f'"${price}"' in page, price


def test_env_example_documents_the_same_numbers():
    """Stripe itself is outside the repo, so .env.example is the operator's
    checklist -- it drifting is how the dashboard and the code diverge."""
    path = os.path.join(os.path.dirname(__file__), "..", "..", ".env.example")
    with open(path, encoding="utf-8") as f:
        env = f.read()
    assert f'${PLAN_PRICES["creator"]}/mo — {PLAN_CREDITS["creator"]} credits' in env
    assert f'${PLAN_PRICES["pro"]}/mo — {PLAN_CREDITS["pro"]} credits' in env
    for pack, price in PACK_PRICES.items():
        assert f'${price} — {CREDIT_PACKAGES[pack]["credits"]} credits' in env, pack


# --- what a credit actually buys ----------------------------------------


def test_a_credit_buys_enough_video_for_tension_to_matter():
    """Margin can also be raised by shrinking the product, but below ~5s per
    credit every scene pins to the floor and the tension-based pacing stops
    doing anything -- so the constant must stay clear of it."""
    from interfaces.second_budget import MIN_SCENE_SECONDS, distribute_budget

    assert SECONDS_PER_CREDIT >= MIN_SCENE_SECONDS + 2
    durations = distribute_budget([3, 6, 8, 10, 4])
    assert max(durations) >= 2 * min(durations), durations
