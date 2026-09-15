"""Stripe payment integration for MuseForge subscriptions + credit packages.

What a credit is worth, how long it lives, and how a grant reaches Supabase
now live in `billing.py`, because they are the same whether the money arrived
through Stripe or through Whop (see that module's docstring for why a second
copy of those numbers is a payment bug rather than a style one). What stays
here is everything that is TRUE OF STRIPE AND NOTHING ELSE: Prices, Checkout
Sessions, the Billing Portal, signature verification, and the shape of the
five events this deployment acts on.

The economics constants are re-exported below under the names they have always
had -- `stripe_integration.PLAN_CREDITS` is imported by the pricing-coherence
test and by the API -- so that this split is invisible to every caller.
"""

import asyncio
import logging
import os
from typing import Optional

import httpx  # noqa: F401  (tests patch httpx.AsyncClient through this module)
import stripe

import billing
from billing import (  # noqa: F401  (re-exported: callers import these from here)
    ANNUAL_ALLOWANCE_MONTHS,
    ANNUAL_CREDIT_VALIDITY_DAYS,
    ANNUAL_DISCOUNT_PERCENT,
    BILLING_INTERVALS,
    CREDIT_PACKAGES,
    CREDIT_VALIDITY_DAYS,
    DEFAULT_BILLING_INTERVAL,
    PACK_CREDIT_VALIDITY_DAYS,
    PLAN_CREDITS,
    allowance_for,
)

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

#: Which processor this module is. Everything it writes to the idempotency
#: table is keyed with it.
PROVIDER = "stripe"

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


def get_credit_price_id(package: str) -> Optional[str]:
    """Return Stripe price ID for a one-time credit package (SMALL/MEDIUM/LARGE)."""
    return os.environ.get(f"STRIPE_PRICE_CREDITS_{package.upper()}")


# ── Supabase helpers ──────────────────────────────────────────────────────────
# Thin wrappers over `billing`, kept under their original names because they
# are the seam the webhook tests patch.

async def _add_credits_to_profile(
    user_id: str,
    credits_delta: int,
    plan: Optional[str] = None,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    reason: str = "subscription_renewal",
    validity_days: int = CREDIT_VALIDITY_DAYS,
):
    """Grant credits as a new lot and record the Stripe ids on the profile."""
    await billing.grant_credits(
        user_id,
        credits_delta,
        plan=plan,
        profile_fields={
            "stripe_customer_id": stripe_customer_id,
            "stripe_subscription_id": stripe_subscription_id,
        },
        reason=reason,
        validity_days=validity_days,
    )


async def _mark_event_processed(event_id: str) -> bool:
    """Claim this Stripe event; False if it was already handled."""
    return await billing.mark_event_processed(PROVIDER, event_id)


async def _release_event_mark(event_id: str) -> None:
    """Give the claim back so Stripe's retry is allowed to do the work."""
    await billing.release_event_mark(PROVIDER, event_id)


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


async def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify Stripe webhook signature and process supported events."""
    if not STRIPE_WEBHOOK_SECRET:
        # Every webhook this deployment ever receives will be rejected, and
        # the access log shows only "400". Said once, loudly, with the cause.
        logger.error(
            "Stripe webhook rejected: STRIPE_WEBHOOK_SECRET is not configured, "
            "so no payment event can be verified or credited."
        )
        raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError as exc:
        # A bare 400 in the access log cannot be told apart from a port scan.
        # The two causes need different actions -- rotate the endpoint secret,
        # or ignore the noise -- so the log says which one this is.
        logger.error(
            "Stripe webhook rejected: signature verification failed (%s). "
            "If Stripe's dashboard shows these as failed deliveries, the "
            "endpoint's signing secret does not match STRIPE_WEBHOOK_SECRET.",
            exc,
        )
        raise ValueError(f"Invalid webhook signature: {exc}") from exc

    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]["object"]

    # Idempotency guard: skip already-processed events
    is_new = await _mark_event_processed(event_id)
    if not is_new:
        return {"status": "already_processed", "event_id": event_id}

    try:
        return await _dispatch_event(event_type, data)
    except Exception:
        # The mark was taken before the work; the work did not happen. Leaving
        # it in place is the expensive failure: Stripe retries a 5xx, the
        # retry finds the event already marked, returns 200 "already
        # processed", and a customer who paid is never credited -- silently,
        # permanently, and with a green delivery in the Stripe dashboard.
        #
        # Releasing it makes the retry do the work instead. The duplicate-grant
        # risk this reintroduces is bounded by the same failure having to
        # happen AFTER the credits landed, which is the one ordering
        # `_add_credits_to_profile` does not produce -- it is the last thing
        # every branch below does.
        logger.exception(
            "Stripe event %s (%s) failed while being handled; releasing its "
            "idempotency mark so the retry can be processed.",
            event_id,
            event_type,
        )
        await _release_event_mark(event_id)
        raise


async def _dispatch_event(event_type: str, data: dict) -> dict:
    """Apply one verified, not-yet-processed Stripe event.

    Split out of `handle_webhook` so the idempotency mark has a single place
    to be given back when this raises.
    """
    # ── Subscription checkout completed ──────────────────────────────────────
    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id") or data.get("metadata", {}).get("user_id")
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        payment_mode = data.get("mode", "subscription")

        if payment_mode == "payment":
            # One-time credit package purchase
            pkg_key = (data.get("metadata") or {}).get("credit_package", "")
            credits = billing.credits_in_package(pkg_key)
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
            plan = "creator"
            row = await billing.find_profile("stripe_customer_id", customer_id or "")
            if row:
                user_id = row.get("id")
                plan = row.get("plan", "creator")

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
        if customer_id:
            row = await billing.find_profile("stripe_customer_id", customer_id, select="id")
            await billing.end_subscription(
                (row or {}).get("id"),
                "stripe_customer_id",
                customer_id,
                clear_fields={"stripe_subscription_id": None},
            )

    elif event_type == "invoice.payment_failed":
        pass  # TODO: notify user

    return {"received": True, "type": event_type}
