"""Stripe payment integration for MuseForge subscriptions + credit packages."""

import asyncio
import os
from typing import Optional

import httpx
import stripe

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

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
#: page. The authoritative number is whatever the Stripe annual Price says --
#: this constant only has to agree with it.
ANNUAL_DISCOUNT_PERCENT = 10

#: Months of allowance handed over when an annual subscription starts or
#: renews. The whole year lands at once (with a year to spend it) because the
#: customer has already paid for the whole year: metering it out monthly would
#: need a scheduler we do not run, and would silently expire allowance they
#: are not getting a refund for.
ANNUAL_ALLOWANCE_MONTHS = 12

stripe.api_key = STRIPE_SECRET_KEY


def get_price_id(plan: str, interval: str = DEFAULT_BILLING_INTERVAL) -> Optional[str]:
    """Stripe Price for a plan on a billing interval.

    Annual has its own Price (STRIPE_PRICE_PRO_ANNUAL). It deliberately does
    NOT fall back to the monthly Price when unset: falling back would charge a
    customer who chose "billed yearly" a monthly amount and put them on a
    monthly cycle, which is a billing error, not a degraded experience. An
    unconfigured annual Price is a 400 the operator can see.
    """
    plan = (plan or "").upper()
    if (interval or DEFAULT_BILLING_INTERVAL).lower() == "annual":
        return os.environ.get(f"STRIPE_PRICE_{plan}_ANNUAL")
    return os.environ.get(f"STRIPE_PRICE_{plan}")


def plan_for_price_id(price_id: str) -> Optional[str]:
    """Which plan a Stripe Price belongs to, on either interval.

    The webhook used to compare against STRIPE_PRICE_PRO alone, so an ANNUAL
    Pro subscriber matched nothing and was silently provisioned as Creator --
    the more expensive plan granting the smaller allowance.
    """
    if not price_id:
        return None
    for plan in PLAN_CREDITS:
        for interval in BILLING_INTERVALS:
            if get_price_id(plan, interval) == price_id:
                return plan
    return None


def is_annual_price(price_id: str) -> bool:
    """True when this Price is one of the configured annual Prices."""
    if not price_id:
        return False
    return any(get_price_id(plan, "annual") == price_id for plan in PLAN_CREDITS)


def allowance_for(plan: str, annual: bool) -> tuple:
    """(credits, validity_days) granted for one billing cycle of this plan."""
    monthly = PLAN_CREDITS.get(plan, PLAN_CREDITS["creator"])
    if annual:
        return monthly * ANNUAL_ALLOWANCE_MONTHS, ANNUAL_CREDIT_VALIDITY_DAYS
    return monthly, CREDIT_VALIDITY_DAYS


def get_credit_price_id(package: str) -> Optional[str]:
    """Return Stripe price ID for a one-time credit package (SMALL/MEDIUM/LARGE)."""
    return os.environ.get(f"STRIPE_PRICE_CREDITS_{package.upper()}")


# ── Supabase helpers ──────────────────────────────────────────────────────────

def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }


# NOTE: there is deliberately no _add_ledger_entry helper here. Every credit
# movement in this file goes through the grant_credits/deduct_credits RPCs,
# which write their own credit_ledger row -- a second writer would double-count
# every purchase in the user's history.


async def _add_credits_to_profile(
    user_id: str,
    credits_delta: int,
    plan: Optional[str] = None,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    reason: str = "subscription_renewal",
    validity_days: int = CREDIT_VALIDITY_DAYS,
):
    """Grant credits as a new lot and update the profile's Stripe fields.

    The grant is spendable the moment this returns and lapses
    ``validity_days`` later -- 30 for a monthly allowance, a year for a pack or
    a prepaid annual allowance. grant_credits() also writes the ledger entry
    and refreshes profiles.credits, so this no longer does the read-then-write
    dance that could lose a concurrent grant.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        if credits_delta > 0:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/rpc/grant_credits",
                json={
                    "p_user_id": user_id,
                    "p_amount": credits_delta,
                    "p_reason": reason,
                    "p_days": validity_days,
                },
                headers=_sb_headers(),
            )

        # Plan / Stripe identifiers are profile-level, not lot-level.
        patch_body: dict = {}
        if plan:
            patch_body["plan"] = plan
        if stripe_customer_id:
            patch_body["stripe_customer_id"] = stripe_customer_id
        if stripe_subscription_id:
            patch_body["stripe_subscription_id"] = stripe_subscription_id

        if patch_body:
            await client.patch(
                f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
                json=patch_body,
                headers=_sb_headers(),
            )


async def create_portal_session(customer_id: str, return_url: str) -> str:
    """Create a Stripe Billing Portal session and return the session URL."""
    if not STRIPE_SECRET_KEY:
        raise ValueError("STRIPE_SECRET_KEY is not configured")
    session = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        customer=customer_id,
        return_url=return_url,
    )
    return session.url


async def create_checkout_session(
    price_id: str,
    user_id: str,
    user_email: str,
    success_url: str,
    cancel_url: str,
    mode: str = "subscription",
    metadata: Optional[dict] = None,
) -> str:
    """Create a Stripe Checkout session and return the session URL."""
    if not STRIPE_SECRET_KEY:
        raise ValueError("STRIPE_SECRET_KEY is not configured")

    kwargs = dict(
        payment_method_types=["card"],
        mode=mode,
        line_items=[{"price": price_id, "quantity": 1}],
        client_reference_id=user_id,
        customer_email=user_email,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": user_id, **(metadata or {})},
    )
    session = await asyncio.to_thread(stripe.checkout.Session.create, **kwargs)
    return session.url


async def _mark_event_processed(event_id: str) -> bool:
    """Insert event_id into processed_stripe_events. Returns True if newly inserted,
    False if it already existed (duplicate event — skip processing)."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return True  # dev mode: always proceed
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(
                f"{SUPABASE_URL}/rest/v1/processed_stripe_events",
                json={"event_id": event_id},
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


async def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify Stripe webhook signature and process supported events."""
    if not STRIPE_WEBHOOK_SECRET:
        raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError as exc:
        raise ValueError(f"Invalid webhook signature: {exc}") from exc

    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]["object"]

    # Idempotency guard: skip already-processed events
    is_new = await _mark_event_processed(event_id)
    if not is_new:
        return {"status": "already_processed", "event_id": event_id}

    # ── Subscription checkout completed ──────────────────────────────────────
    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id") or data.get("metadata", {}).get("user_id")
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        payment_mode = data.get("mode", "subscription")

        if payment_mode == "payment":
            # One-time credit package purchase
            pkg_key = (data.get("metadata") or {}).get("credit_package", "")
            pkg = CREDIT_PACKAGES.get(pkg_key.upper(), {})
            credits = pkg.get("credits", 0)
            if user_id and credits:
                await _add_credits_to_profile(
                    user_id,
                    credits,
                    reason="credit_purchase",
                    validity_days=PACK_CREDIT_VALIDITY_DAYS,
                )

        else:
            # Subscription: grant the cycle's credits + set plan
            plan = "creator"
            annual = False
            if subscription_id:
                sub = await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)
                price_id = sub["items"]["data"][0]["price"]["id"]
                plan = plan_for_price_id(price_id) or "creator"
                annual = is_annual_price(price_id)
            credits, validity_days = allowance_for(plan, annual)
            if user_id:
                await _add_credits_to_profile(
                    user_id=user_id,
                    credits_delta=credits,
                    plan=plan,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                    reason="subscription_renewal",
                    validity_days=validity_days,
                )

    # ── Invoice paid (subscription renewal, monthly or yearly) ────────────────
    elif event_type == "invoice.paid":
        billing_reason = data.get("billing_reason", "")
        # Only handle renewal invoices (not the first subscription creation, handled above)
        if billing_reason == "subscription_cycle":
            customer_id = data.get("customer")
            # Resolve user_id via Supabase profiles
            user_id = None
            if customer_id and SUPABASE_URL and SUPABASE_SERVICE_KEY:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(
                        f"{SUPABASE_URL}/rest/v1/profiles",
                        params={"stripe_customer_id": f"eq.{customer_id}", "select": "id,plan", "limit": "1"},
                        headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                    )
                    rows = resp.json()
                    if isinstance(rows, list) and rows:
                        user_id = rows[0].get("id")
                        plan = rows[0].get("plan", "creator")

            if user_id:
                # Which interval renewed decides both the size of the grant and
                # how long it lives. Read it off the invoice line rather than
                # the profile: the profile records the PLAN, not the cycle, so
                # an annual renewal would otherwise be paid a single month's
                # allowance and expire it in 30 days -- eleven twelfths of a
                # year the customer had already paid for.
                renewed_price = ""
                try:
                    renewed_price = (
                        ((data.get("lines") or {}).get("data") or [{}])[0]
                        .get("price", {})
                        .get("id", "")
                    ) or ""
                except (AttributeError, IndexError, TypeError):
                    renewed_price = ""
                plan = plan_for_price_id(renewed_price) or plan
                credits, validity_days = allowance_for(plan, is_annual_price(renewed_price))
                # Grant the cycle's allowance as a fresh lot. This used to
                # OVERWRITE the balance with the allowance to stop hoarding,
                # which also wiped credit packs the user had paid for on top of
                # the subscription. Expiry handles hoarding now: last cycle's
                # unused allowance lapses on its own.
                await _add_credits_to_profile(
                    user_id=user_id,
                    credits_delta=credits,
                    reason="subscription_renewal",
                    validity_days=validity_days,
                )

    # ── Subscription cancelled ────────────────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        if customer_id and SUPABASE_URL and SUPABASE_SERVICE_KEY:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{SUPABASE_URL}/rest/v1/profiles",
                    params={"stripe_customer_id": f"eq.{customer_id}", "select": "id", "limit": "1"},
                    headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
                )
                rows = resp.json()
                user_id = rows[0].get("id") if isinstance(rows, list) and rows else None

                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/profiles?stripe_customer_id=eq.{customer_id}",
                    json={"plan": "free", "stripe_subscription_id": None},
                    headers=_sb_headers(),
                )

                # Drop the unused part of the subscription allowance -- it was
                # rented, not bought. Credit PACKS survive: they were paid for
                # separately and run out their own 30 days. The old code set
                # credits to a flat 3, which destroyed both.
                if user_id:
                    await client.post(
                        f"{SUPABASE_URL}/rest/v1/rpc/revoke_subscription_credits",
                        json={"p_user_id": user_id},
                        headers=_sb_headers(),
                    )

    elif event_type == "invoice.payment_failed":
        pass  # TODO: notify user

    return {"received": True, "type": event_type}
