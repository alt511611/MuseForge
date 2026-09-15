"""What a credit costs, and where a granted credit is written down -- once,
for every payment processor.

Until now this lived entirely inside `stripe_integration.py`: the plan
allowances, the pack sizes, the expiry windows, the Supabase calls that turn a
paid invoice into a spendable lot, and the idempotency table that stops a
retried webhook paying twice. That was correct while Stripe was the only way
to pay.

It stops being correct the moment a second processor exists. MuseForge is
being sold through Whop first, because Whop is the merchant of record and
takes the sale without the seller having a registered company; Stripe follows
when there is one. Two processors, one product. Whatever else differs between
them -- signatures, event names, who the customer belongs to -- these things
MUST NOT:

  * how many credits a Pro annual cycle is worth (36 x 12 = 432),
  * how long a granted credit lives (30 days rented, 365 days bought),
  * that a grant lands through `grant_credits`, which writes the lot AND the
    ledger row AND refreshes `profiles.credits` in one RPC.

A second copy of those numbers is not a style problem. The prices on the
pricing page, `PLAN_CREDITS` and `api.PLAN_MAX_SCENES` are already checked
against each other by `test_pricing_coherence`, and a Whop-flavoured duplicate
would pass that check while quietly paying Whop customers a different
allowance from Stripe customers for the same money. So the numbers live here,
and both integrations read them.

ON THE IDEMPOTENCY KEY
----------------------
`processed_stripe_events` now holds both processors' event ids. Whop's are
written with a `whop:` prefix and Stripe's stay bare. That asymmetry is
deliberate, not an oversight: Stripe has already-processed ids in that table,
and prefixing them now would make every one of them unrecognised -- a Stripe
retry of an old event would be treated as new and would grant its credits a
second time. The prefix exists because a Whop webhook id
(`msg_...`) and a Stripe event id (`evt_...`) are two namespaces in one
primary key, and nothing but a prefix guarantees they cannot collide.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not talk to any processor's API, verify any signature, or know what a
Stripe Price or a Whop Plan is. Those are the integrations' job -- this module
only knows what was bought and who bought it.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from tools.provider_choice import resolve_provider

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


# ── Which processor is taking money today ─────────────────────────────────────

#: Processors a deployment can be switched to. Stripe stays the default: it is
#: what every existing deployment is already running, and a payments provider
#: that changes because a variable was left unset is the one silent failure
#: this whole file is written to avoid.
PAYMENT_PROVIDERS = ("stripe", "whop")
DEFAULT_PAYMENT_PROVIDER = "stripe"


def resolve_payment_provider() -> str:
    """The processor this deployment sells through.

    Read through the same `resolve_provider` the six pipeline stages use, for
    the same reason: it normalises the value, so a dashboard paste with a
    trailing newline still selects what the operator typed, and it LOGS what
    it resolved to -- including when nothing was set. An unrecognised value is
    a warning naming what was asked for and what will run instead, because the
    alternative is a checkout button that silently bills through the processor
    the operator was trying to leave.
    """
    return resolve_provider(
        "PAYMENT_PROVIDER",
        PAYMENT_PROVIDERS,
        DEFAULT_PAYMENT_PROVIDER,
        stage="payments",
    )


# ── What a plan is worth ──────────────────────────────────────────────────────

# Plan definitions: plan name → credits granted per renewal cycle
# Credits included with each subscription tier.
#
# Priced against real unit economics: one credit buys SECONDS_PER_CREDIT
# seconds of finished video (see interfaces/second_budget), which costs
# ~$0.95 at the provider's linear per-second rate. These allocations put
# both tiers near a 74% gross margin. Every tier must include at least
# PLAN_MAX_SCENES credits, otherwise the plan cannot render one
# full-length drama -- api.PLAN_MAX_SCENES is the constraint to check
# when changing these.
PLAN_CREDITS = {
    "creator": 16,
    "pro": 36,
}

# One-time credit packages: env var suffix → credit amount
# One-off packs carry a premium over subscriptions -- they buy flexibility,
# not commitment -- so their per-credit price is deliberately higher.
CREDIT_PACKAGES = {
    "SMALL":  {"credits": 4,  "label": "4 Credits"},
    "MEDIUM": {"credits": 12, "label": "12 Credits"},
    "LARGE":  {"credits": 26, "label": "26 Credits"},
}

# How long a granted credit stays spendable. Every grant lands immediately and
# lapses after its own window, whether or not it was used. The DATABASE is the
# enforcer (public.grant_credits takes p_days); these constants are what the
# server passes and what the UI quotes.
#
# A monthly allowance is rented: it is sized to one month of work and lapses
# with the month, which is what stops it being hoarded across renewals.
#: Must match public.credit_validity_days() in supabase_migration.sql, which is
#: the fallback used when a caller passes no p_days.
CREDIT_VALIDITY_DAYS = 30

# A credit PACK was bought outright, not rented, and it is bought precisely by
# the people whose work is lumpy -- an agency with one shoot this quarter. A
# 30-day fuse on money already taken is the kind of term customers discover at
# renewal and leave over, so packs (and the prepaid annual allowance) live a
# year.
PACK_CREDIT_VALIDITY_DAYS = 365
ANNUAL_CREDIT_VALIDITY_DAYS = 365

#: Billing intervals a subscription can be sold on. Annual is the default
#: offer: it is cheaper for the customer and prepaid for us.
BILLING_INTERVALS = ("annual", "monthly")
DEFAULT_BILLING_INTERVAL = "annual"

#: Discount applied to the annual price, quoted to the customer on the pricing
#: page. The authoritative number is whatever the processor's annual price
#: says -- this constant only has to agree with it.
ANNUAL_DISCOUNT_PERCENT = 10

#: Months of allowance handed over when an annual subscription starts or
#: renews. The whole year lands at once (with a year to spend it) because the
#: customer has already paid for the whole year: metering it out monthly would
#: need a scheduler we do not run, and would silently expire allowance they
#: are not getting a refund for.
ANNUAL_ALLOWANCE_MONTHS = 12


def allowance_for(plan: str, annual: bool) -> tuple:
    """(credits, validity_days) granted for one billing cycle of this plan."""
    monthly = PLAN_CREDITS.get(plan, PLAN_CREDITS["creator"])
    if annual:
        return monthly * ANNUAL_ALLOWANCE_MONTHS, ANNUAL_CREDIT_VALIDITY_DAYS
    return monthly, CREDIT_VALIDITY_DAYS


def credits_in_package(package: str) -> int:
    """How many credits a one-off pack key is worth; 0 if it names no pack."""
    return CREDIT_PACKAGES.get((package or "").upper(), {}).get("credits", 0)


# ── Supabase plumbing ─────────────────────────────────────────────────────────

def sb_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


def sb_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


# NOTE: there is deliberately no ledger-writing helper here. Every credit
# movement goes through the grant_credits/deduct_credits RPCs, which write
# their own credit_ledger row -- a second writer would double-count every
# purchase in the user's history.


def _must_have_granted(resp, user_id: str, credits_delta: int) -> None:
    """Raise unless Supabase actually granted the credits.

    This used to be `await client.post(...)` with the response thrown away,
    and that silence is what makes it worth a function of its own. A database
    that has not had `supabase_migration.sql` applied answers the RPC with
    404 `Could not find the function public.grant_credits`. The old code read
    that as success: the webhook returned 200, the processor's dashboard
    showed a green delivery, the customer had paid, and nobody -- not the
    customer, not the log, not the processor -- was told the credits never
    landed. It was found on the live database on 15 Sep 2026, where every one
    of `grant_credits`, `deduct_credits`, `credit_balance` and
    `revoke_subscription_credits` was missing.

    Raising instead turns that into the failure the retry machinery is built
    for: the webhook handler releases its idempotency mark, answers 5xx, and
    the processor redelivers -- so the moment the migration IS applied, every
    payment that failed this way is credited by a retry rather than by hand.
    """
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Supabase refused to grant {credits_delta} credits to {user_id} "
            f"({resp.status_code}): {resp.text[:300]}"
        )


async def grant_credits(
    user_id: str,
    credits_delta: int,
    *,
    plan: Optional[str] = None,
    profile_fields: Optional[dict] = None,
    reason: str = "subscription_renewal",
    validity_days: int = CREDIT_VALIDITY_DAYS,
) -> None:
    """Grant credits as a new lot and update the profile's processor fields.

    The grant is spendable the moment this returns and lapses
    ``validity_days`` later -- 30 for a monthly allowance, a year for a pack or
    a prepaid annual allowance. grant_credits() also writes the ledger entry
    and refreshes profiles.credits, so this does not do the read-then-write
    dance that could lose a concurrent grant.

    ``profile_fields`` is whatever identifies this customer at the processor
    (`stripe_customer_id`, `whop_membership_id`, …). It is a plain dict rather
    than named arguments because the columns are the one part of this path
    that legitimately differs per processor.
    """
    if not sb_configured():
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        if credits_delta > 0:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/grant_credits",
                json={
                    "p_user_id": user_id,
                    "p_amount": credits_delta,
                    "p_reason": reason,
                    "p_days": validity_days,
                },
                headers=sb_headers(),
            )
            _must_have_granted(resp, user_id, credits_delta)

        # Plan / processor identifiers are profile-level, not lot-level.
        patch_body: dict = {k: v for k, v in (profile_fields or {}).items() if v}
        if plan:
            patch_body["plan"] = plan

        if patch_body:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
                json=patch_body,
                headers=sb_headers(),
            )


async def find_profile(column: str, value: str, select: str = "id,plan") -> Optional[dict]:
    """The one profile whose ``column`` equals ``value``, or None.

    Used to answer "whose subscription just renewed?" from nothing but a
    processor-side identifier.
    """
    if not sb_configured() or not value:
        return None
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            params={column: f"eq.{value}", "select": select, "limit": "1"},
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            },
        )
        rows = resp.json()
        if isinstance(rows, list) and rows:
            return rows[0]
    return None


async def end_subscription(
    user_id: Optional[str],
    column: str,
    value: str,
    clear_fields: Optional[dict] = None,
) -> None:
    """Put the profile back on the free plan and drop the rented allowance.

    Credit PACKS survive: they were paid for separately and run out their own
    year. Only lots granted as `subscription_renewal` are revoked -- the older
    code set the balance to a flat 3, which destroyed both.

    ``clear_fields`` is the processor-side subscription identifier to null out
    (`{"stripe_subscription_id": None}`), which differs per processor and is
    therefore passed in rather than guessed from the column name.
    """
    if not sb_configured():
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/profiles?{column}=eq.{value}",
            json={"plan": "free", **(clear_fields or {})},
            headers=sb_headers(),
        )
        if user_id:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/revoke_subscription_credits",
                json={"p_user_id": user_id},
                headers=sb_headers(),
            )


# ── Idempotency ───────────────────────────────────────────────────────────────

def event_key(provider: str, event_id: str) -> str:
    """The primary key this event is remembered under.

    Stripe's ids stay bare so the rows already in the table keep matching; see
    ON THE IDEMPOTENCY KEY in the module docstring.
    """
    if provider == "stripe":
        return event_id
    return f"{provider}:{event_id}"


async def mark_event_processed(provider: str, event_id: str) -> bool:
    """Claim this event. True if we claimed it, False if it was already done.

    Fails OPEN on a Supabase problem: a webhook that cannot reach the
    idempotency table is still a payment that has to be credited, and the
    duplicate it risks is recoverable in a way an uncredited purchase is not.
    """
    if not sb_configured():
        return True  # dev mode: always proceed
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/processed_stripe_events",
                json={"event_id": event_key(provider, event_id)},
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=ignore-duplicates,return=minimal",
                },
            )
            # 201 = inserted (new event); 200/204 with ignore-duplicates = already existed
            return resp.status_code == 201
    except Exception:
        return True  # fail-open on Supabase issues


async def release_event_mark(provider: str, event_id: str) -> None:
    """Undo `mark_event_processed`, so the processor's retry is allowed to work.

    The mark is taken BEFORE the event is handled, which is the right order --
    it is what stops two concurrent deliveries of the same event from granting
    the credits twice. It is also why a handler that raises must give the mark
    back.

    Fails quietly. If this delete does not land, the event stays marked and
    the credits stay ungranted, which is exactly the state we were already in;
    raising here would replace one lost event with a lost event AND a
    misleading traceback about the delete rather than the cause.
    """
    if not sb_configured():
        return
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            await client.delete(
                f"{SUPABASE_URL}/rest/v1/processed_stripe_events",
                params={"event_id": f"eq.{event_key(provider, event_id)}"},
                headers={
                    "apikey": SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                    "Prefer": "return=minimal",
                },
            )
    except Exception as exc:
        logger.error(
            "%s event %s failed AND its idempotency mark could not be "
            "released (%s). The retry will be treated as a duplicate and "
            "this payment will not be credited without manual repair.",
            provider,
            event_id,
            exc,
        )
