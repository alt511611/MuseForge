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
    """The plan table lives in the client component, not the route's server
    page.js -- the latter only carries the JSON-LD mirror (checked below)."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "client", "app", "[locale]", "pricing", "PricingContent.js",
    )
    with open(path, encoding="utf-8") as f:
        return f.read()


def _pricing_route():
    path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "client", "app", "[locale]", "pricing", "page.js",
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
    # Plans carry the undiscounted monthly figure; the card derives both the
    # annual rate and the yearly total from it.
    for price in PLAN_PRICES.values():
        assert re.search(rf"monthly:\s*{price}\b", page), price
    for price in PACK_PRICES.values():
        assert f'"${price}"' in page, price


# --- annual billing -----------------------------------------------------


def test_page_and_server_agree_on_the_annual_discount():
    """The page quotes the discount; Stripe's annual Price is what actually
    charges. The constant on each side is the only thing keeping the quote
    and the charge in step."""
    from stripe_integration import ANNUAL_DISCOUNT_PERCENT

    assert ANNUAL_DISCOUNT_PERCENT == 10
    assert re.search(
        rf"ANNUAL_DISCOUNT_PERCENT\s*=\s*{ANNUAL_DISCOUNT_PERCENT}\b", _pricing_page()
    )


def test_annual_is_the_option_on_screen_first():
    """The cheaper offer should be the one a visitor sees before touching
    anything -- and the interval sent to checkout must match it."""
    page = _pricing_page()
    assert re.search(r'useState\("annual"\)', page)
    assert "interval={interval}" in page


def test_page_states_what_a_credit_buys():
    """Competitors meter raw model compute, so their credit counts are an
    order of magnitude larger for the same money. Without the seconds figure
    on the page, "36 credits" vs "800 credits" is a comparison we lose on a
    misunderstanding."""
    page = _pricing_page()
    assert re.search(rf"SECONDS_PER_CREDIT\s*=\s*{int(SECONDS_PER_CREDIT)}\b", page), (
        "the pricing page must state the same seconds-per-credit the pipeline uses"
    )


def test_annual_totals_in_env_example_match_the_discount():
    """Stripe's annual Prices are created by hand from these numbers."""
    from stripe_integration import ANNUAL_DISCOUNT_PERCENT

    path = os.path.join(os.path.dirname(__file__), "..", "..", ".env.example")
    with open(path, encoding="utf-8") as f:
        env = f.read()
    for plan, monthly in PLAN_PRICES.items():
        total = round(monthly * 12 * (1 - ANNUAL_DISCOUNT_PERCENT / 100))
        assert f"${total}/yıl" in env, f"{plan}: expected ${total}/yıl in .env.example"


def test_pricing_jsonld_mirrors_the_plan_table():
    """PLAN_OFFERS is hand-kept in sync with the component. When it drifts,
    search engines quote a price the checkout will not honour."""
    route = _pricing_route()
    for plan in PLAN_CREDITS:
        assert f'price: "{PLAN_PRICES[plan]}"' in route, plan
        assert f'{PLAN_CREDITS[plan]} credits per month' in route, plan


def _solution_pages():
    root = os.path.join(
        os.path.dirname(__file__), "..", "..", "client", "app", "[locale]", "solutions"
    )
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, "page.js")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                yield name, f.read()


def test_solution_pages_quote_real_plans():
    """The /solutions/* landing pages each pitch a plan card. Every price and
    credit figure on them has to be one the checkout actually sells."""
    prices = {f"${p}" for p in PLAN_PRICES.values()} | {
        f"${p}" for p in PACK_PRICES.values()
    }
    credits = set(PLAN_CREDITS.values())

    for name, page in _solution_pages():
        for quoted in re.findall(r'price:\s*"(?:From )?(\$\d+)"', page):
            assert quoted in prices, f"{name}: {quoted} is not a price we charge"
        for quoted in re.findall(r"credits:\s*(\d+)", page):
            assert int(quoted) in credits, f"{name}: no plan grants {quoted} credits"
        for quoted in re.findall(r"(\d+) credits/mo", page):
            assert int(quoted) in credits, f"{name}: no plan grants {quoted} credits"


def test_dashboard_buy_modal_charges_the_advertised_price():
    """The in-app top-up modal builds its own package list. It quoted $9/$19/
    $39 against real Stripe prices of $19/$49/$99 -- the user clicked a $9
    button and was charged $19."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "client", "app", "[locale]", "dashboard", "page.js",
    )
    with open(path, encoding="utf-8") as f:
        page = f.read()

    for pack, price in PACK_PRICES.items():
        assert re.search(
            rf'key:\s*"{pack}".*?price:\s*"\${price}"', page
        ), f"{pack} should be ${price}"


def test_plan_feature_strings_match_granted_credits():
    """The pricing page renders its bullet list from these translations, so a
    stale string contradicts the credit count printed right above it."""
    path = os.path.join(
        os.path.dirname(__file__), "..", "..", "client", "lib", "i18n", "t-a.js"
    )
    with open(path, encoding="utf-8") as f:
        strings = f.read()

    for plan in PLAN_CREDITS:
        for quoted in re.findall(rf"plan_{plan}_features:\s*\"(\d+) [^,]*?/", strings):
            assert int(quoted) == PLAN_CREDITS[plan], f"{plan}: {quoted}"
    for pack in ("small", "medium", "large"):
        expected = CREDIT_PACKAGES[pack.upper()]["credits"]
        for quoted in re.findall(rf"pricing_credits_{pack}:\s*\"(\d+) ", strings):
            assert int(quoted) == expected, f"{pack}: {quoted}"


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
