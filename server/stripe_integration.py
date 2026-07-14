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
PLAN_CREDITS = {
    "creator": 120,
    "pro": 300,
}

# One-time credit packages: env var suffix → credit amount
CREDIT_PACKAGES = {
    "SMALL":  {"credits": 20,  "label": "20 Credits"},
    "MEDIUM": {"credits": 60,  "label": "60 Credits"},
    "LARGE":  {"credits": 150, "label": "150 Credits"},
}

stripe.api_key = STRIPE_SECRET_KEY


def get_price_id(plan: str) -> Optional[str]:
    env_key = f"STRIPE_PRICE_{plan.upper()}"
    return os.environ.get(env_key)


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


async def _add_ledger_entry(user_id: str, amount: int, reason: str, job_id: Optional[str] = None):
    """Insert a row into credit_ledger. Fire-and-forget safe."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return
    try:
        payload = {"user_id": user_id, "amount": amount, "reason": reason}
        if job_id:
            payload["job_id"] = job_id
        async with httpx.AsyncClient(timeout=6.0) as client:
            await client.post(
                f"{SUPABASE_URL}/rest/v1/credit_ledger",
                json=payload,
                headers=_sb_headers(),
            )
    except Exception:
        pass


async def _add_credits_to_profile(
    user_id: str,
    credits_delta: int,
    plan: Optional[str] = None,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    reason: str = "subscription_renewal",
):
    """Add (or deduct) credits from profiles and write a ledger entry."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return

    patch: dict = {"credits": f"credits+{credits_delta}"}  # will use RPC below
    # Supabase REST doesn't do increments natively; use raw SQL via rpc or a two-step read+write.
    # We do a simple two-step here since this runs inside webhook (serial).
    async with httpx.AsyncClient(timeout=10.0) as client:
        # 1. Read current
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/profiles",
            params={"id": f"eq.{user_id}", "select": "credits", "limit": "1"},
            headers={"apikey": SUPABASE_SERVICE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"},
        )
        data = resp.json()
        current = data[0].get("credits", 0) if isinstance(data, list) and data else 0
        new_credits = max(0, current + credits_delta)

        # 2. Patch
        patch_body: dict = {"credits": new_credits}
        if plan:
            patch_body["plan"] = plan
        if stripe_customer_id:
            patch_body["stripe_customer_id"] = stripe_customer_id
        if stripe_subscription_id:
            patch_body["stripe_subscription_id"] = stripe_subscription_id

        await client.patch(
            f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
            json=patch_body,
            headers=_sb_headers(),
        )

    await _add_ledger_entry(user_id, credits_delta, reason)


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
        raise ValueError("STRIPE_WEBHOOK_SECRET is not configured")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError as exc:
        raise ValueError(f"Invalid webhook signature: {exc}") from exc

    event_type = event["type"]
    data = event["data"]["object"]

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
                await _add_credits_to_profile(user_id, credits, reason="credit_purchase")

        else:
            # Subscription: grant initial credits + set plan
            plan = "creator"
            credits = PLAN_CREDITS["creator"]
            if subscription_id:
                sub = await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id)
                price_id = sub["items"]["data"][0]["price"]["id"]
                pro_price = os.environ.get("STRIPE_PRICE_PRO", "")
                if price_id == pro_price:
                    plan = "pro"
                    credits = PLAN_CREDITS["pro"]
            if user_id:
                await _add_credits_to_profile(
                    user_id=user_id,
                    credits_delta=credits,
                    plan=plan,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=subscription_id,
                    reason="subscription_renewal",
                )

    # ── Monthly invoice paid (subscription renewal) ───────────────────────────
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
                credits = PLAN_CREDITS.get(plan, PLAN_CREDITS["creator"])
                # Reset credits to plan allowance (not additive — prevents hoarding)
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.patch(
                        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
                        json={"credits": credits},
                        headers=_sb_headers(),
                    )
                await _add_ledger_entry(user_id, credits, "subscription_renewal")

    # ── Subscription cancelled ────────────────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        if customer_id and SUPABASE_URL and SUPABASE_SERVICE_KEY:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.patch(
                    f"{SUPABASE_URL}/rest/v1/profiles?stripe_customer_id=eq.{customer_id}",
                    json={"plan": "free", "credits": 3, "stripe_subscription_id": None},
                    headers=_sb_headers(),
                )

    elif event_type == "invoice.payment_failed":
        pass  # TODO: notify user

    return {"received": True, "type": event_type}
