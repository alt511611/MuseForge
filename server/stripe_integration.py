"""Stripe payment integration for MuseForge subscriptions."""

import asyncio
import os
from typing import Optional

import httpx
import stripe

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Plan definitions: plan name → (credits_per_month, display_label)
PLAN_CREDITS = {
    "creator": 30,
    "pro": 150,
}

stripe.api_key = STRIPE_SECRET_KEY


def get_price_id(plan: str) -> Optional[str]:
    env_key = f"STRIPE_PRICE_{plan.upper()}"
    return os.environ.get(env_key)


async def create_checkout_session(
    price_id: str,
    user_id: str,
    user_email: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Create a Stripe Checkout session and return the session URL."""
    if not STRIPE_SECRET_KEY:
        raise ValueError("STRIPE_SECRET_KEY is not configured")

    # stripe's SDK is synchronous under the hood; run it in a thread so it
    # doesn't block the event loop for other concurrent requests.
    session = await asyncio.to_thread(
        stripe.checkout.Session.create,
        payment_method_types=["card"],
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        client_reference_id=user_id,
        customer_email=user_email,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"user_id": user_id},
    )
    return session.url


async def _update_supabase_profile(
    user_id: str,
    plan: str,
    credits: int,
    stripe_customer_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
):
    """Update the user's plan and credits in Supabase profiles table."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        return  # Silently skip in dev/test if Supabase not configured

    patch = {"plan": plan, "credits": credits}
    if stripe_customer_id:
        patch["stripe_customer_id"] = stripe_customer_id
    if stripe_subscription_id:
        patch["stripe_subscription_id"] = stripe_subscription_id

    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.patch(
            f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{user_id}",
            json=patch,
            headers={
                "apikey": SUPABASE_SERVICE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )


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

    if event_type == "checkout.session.completed":
        user_id = data.get("client_reference_id") or data.get("metadata", {}).get("user_id")
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")

        # Determine plan from the subscription's price
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
            await _update_supabase_profile(
                user_id=user_id,
                plan=plan,
                credits=credits,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
            )

    elif event_type == "customer.subscription.deleted":
        # Find user by customer_id (best-effort)
        customer_id = data.get("customer")
        if customer_id and SUPABASE_URL and SUPABASE_SERVICE_KEY:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.patch(
                    f"{SUPABASE_URL}/rest/v1/profiles?stripe_customer_id=eq.{customer_id}",
                    json={"plan": "free", "credits": 3, "stripe_subscription_id": None},
                    headers={
                        "apikey": SUPABASE_SERVICE_KEY,
                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
                        "Content-Type": "application/json",
                        "Prefer": "return=minimal",
                    },
                )
                resp.raise_for_status()

    elif event_type == "invoice.payment_failed":
        # Optional: notify user or restrict access — no-op for now
        pass

    return {"received": True, "type": event_type}
