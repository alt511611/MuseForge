"""Selling MuseForge through Whop: checkout links, webhooks, credit grants.

WHY THERE IS A SECOND PROCESSOR AT ALL
--------------------------------------
Stripe needs a registered company. MuseForge does not have one yet, and the
product is finished. Whop is the MERCHANT OF RECORD -- it takes the card, it
owes the tax, and it pays out to an individual -- so it is the only one of the
two that can sell anything this month. Stripe stays in the tree, configured
and tested, because the day the company exists it becomes the cheaper path
(Whop's cut is roughly 3% on top of card fees) and nothing about the product
should have to change to switch back. `PAYMENT_PROVIDER` is the switch, read
through the same `resolve_provider` the six pipeline stages use.

WHAT WHOP CALLS THINGS
----------------------
The mapping is nearly one-to-one with Stripe, and the two places it is NOT are
the two places this file is easy to get wrong:

    Stripe                          Whop
    Price                           Plan                  (plan_xxx)
    Checkout Session                Checkout Configuration (POST
                                    /api/v1/checkout_configurations
                                    → `purchase_url`)
    client_reference_id             metadata.user_id
    Customer                        User + Membership     (mem_xxx)
    checkout.session.completed      payment.succeeded, billing_reason
                                      = subscription_create / one_time
    invoice.paid (subscription_
      cycle)                        payment.succeeded, billing_reason
                                      = subscription_cycle
    customer.subscription.deleted   membership.went_invalid
    Billing Portal session          the customer's own Whop orders page

1. THERE IS NO `client_reference_id`. The only thing that carries "which
   MuseForge account is this" from the click to the webhook is the `metadata`
   object on the checkout configuration, which Whop copies onto the payment
   and the membership it creates. That is why `create_checkout_session` below
   refuses to build a link without a user id: a purchase that arrives with no
   metadata cannot be credited to anybody, and the money has already moved.

2. THERE IS NO BILLING PORTAL to create server-side. Stripe hands back a
   signed, single-use URL; Whop's equivalent is the customer's own orders page
   on whop.com, which they reach by logging in. So `manage_url()` returns a
   plain link and the API keeps the same response shape, which is what lets
   the existing dashboard button go on working unchanged.

ON VERIFYING THE SIGNATURE
--------------------------
Whop follows the Standard Webhooks spec: three headers (`webhook-id`,
`webhook-timestamp`, `webhook-signature`), and the signature covers
`{id}.{timestamp}.{raw body}` under HMAC-SHA256. Two details are load-bearing
and are both mistakes that produce a 401 nobody can debug from the logs:

  * The RAW body is signed. Parsing the JSON first and re-serialising it
    changes the bytes -- a re-serialised body differs in whitespace alone --
    and the digest will never match. `api.py` passes `await request.body()`.
  * The secret's key derivation is not observable from the outside. Whop's
    secrets carry a `ws_` prefix and their own SDK says to pass the secret
    exactly as issued because "the helper derives the key", while the
    Standard Webhooks reference implementation base64-decodes the part after
    the prefix. Rather than guess, `_signing_keys()` tries every derivation
    and accepts if ANY of them matches. That is not a weakened check: each
    candidate is still a full HMAC over the same signed string under a secret
    only Whop and this server know, so an attacker gains nothing from there
    being three ways to phrase it -- and the operator does not lose every
    payment for three days to a prefix.

The `webhook-timestamp` is also checked against the clock, because a signature
without a freshness window is replayable forever by anyone who once saw one
delivery.

WHAT THIS MODULE DOES NOT DO
----------------------------
It does not decide what a credit is worth or write one down -- `billing.py`
owns the allowances, the expiry windows and the Supabase RPCs, so that a Whop
customer and a Stripe customer get identical credits for identical money.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Iterable, Optional

import httpx

import billing
from billing import (
    DEFAULT_BILLING_INTERVAL,
    PACK_CREDIT_VALIDITY_DAYS,
    PLAN_CREDITS,
    allowance_for,
)

logger = logging.getLogger(__name__)

WHOP_API_KEY = os.environ.get("WHOP_API_KEY", "")
WHOP_WEBHOOK_SECRET = os.environ.get("WHOP_WEBHOOK_SECRET", "")

#: Sandbox lives at https://sandbox-api.whop.com/api/v1 and takes the same
#: shapes, so it is a variable rather than a constant.
WHOP_API_BASE = os.environ.get("WHOP_API_BASE", "https://api.whop.com/api/v1")

#: Where a subscriber manages or cancels their own plan. Whop has no
#: server-created portal session; this is the page they log in to.
WHOP_MANAGE_URL = os.environ.get("WHOP_MANAGE_URL", "https://whop.com/orders/")

#: How far out of date a delivery's timestamp may be before it is treated as a
#: replay. Whop retries for about three days, but a retry is re-signed with a
#: fresh timestamp -- only a captured-and-resent body looks old.
WEBHOOK_TOLERANCE_SECONDS = 300

PROVIDER = "whop"

#: Whop's `billing_reason` values that mean "a subscription cycle was paid",
#: first one included: `subscription_create` is the initial purchase and
#: `subscription_cycle` every renewal after it. Both grant the same allowance,
#: which is why they are one set rather than two branches.
SUBSCRIPTION_REASONS = ("subscription_create", "subscription_cycle", "subscription")

#: …and the ones that mean "a one-off pack was bought".
ONE_TIME_REASONS = ("one_time", "manual")

#: Membership events that end a subscription. Whop has renamed these once
#: already, so the handler matches a set rather than a single string: a
#: cancellation that matches nothing leaves a cancelled customer holding a
#: full allowance.
CANCELLATION_EVENTS = (
    "membership.went_invalid",
    "membership.deactivated",
    "membership.cancelled",
    "membership.canceled",
)


# ── Which Whop Plan is which MuseForge plan ───────────────────────────────────

def get_plan_id(plan: str, interval: str = DEFAULT_BILLING_INTERVAL) -> Optional[str]:
    """The Whop Plan id for a tier on a billing interval.

    Mirrors `stripe_integration.get_price_id`, including its refusal to fall
    back: an unset `WHOP_PLAN_PRO_ANNUAL` is a 400 the operator can see, not a
    customer who asked to be billed yearly and was quietly put on a monthly
    cycle.
    """
    plan = (plan or "").upper()
    if (interval or DEFAULT_BILLING_INTERVAL).lower() == "annual":
        return os.environ.get(f"WHOP_PLAN_{plan}_ANNUAL")
    return os.environ.get(f"WHOP_PLAN_{plan}")


def get_credit_plan_id(package: str) -> Optional[str]:
    """The Whop Plan id for a one-off credit pack (SMALL/MEDIUM/LARGE)."""
    return os.environ.get(f"WHOP_PLAN_CREDITS_{(package or '').upper()}")


def plan_for_plan_id(plan_id: str) -> Optional[str]:
    """Which tier a Whop Plan id belongs to, on either interval."""
    if not plan_id:
        return None
    for plan in PLAN_CREDITS:
        for interval in billing.BILLING_INTERVALS:
            if get_plan_id(plan, interval) == plan_id:
                return plan
    return None


def is_annual_plan_id(plan_id: str) -> bool:
    """True when this Plan id is one of the configured annual Plans."""
    if not plan_id:
        return False
    return any(get_plan_id(plan, "annual") == plan_id for plan in PLAN_CREDITS)


def package_for_plan_id(plan_id: str) -> Optional[str]:
    """Which credit pack a Whop Plan id sells, if any.

    The pack key normally arrives in the checkout metadata. This is the
    fallback for the payment that does not carry it -- a renewal of a
    subscription created before the metadata was added, or a sale made from a
    link pasted into Whop's own storefront rather than built here.
    """
    if not plan_id:
        return None
    for package in billing.CREDIT_PACKAGES:
        if get_credit_plan_id(package) == plan_id:
            return package
    return None


# ── Checkout ──────────────────────────────────────────────────────────────────

async def create_checkout_session(
    plan_id: str,
    user_id: str,
    user_email: str = "",
    success_url: str = "",
    metadata: Optional[dict] = None,
) -> str:
    """Create a Whop checkout configuration and return its purchase URL.

    `user_id` is attached as metadata and is NOT optional: Whop copies the
    checkout configuration's metadata onto the payment and the membership, and
    that copy is the only thread tying the money back to an account. A link
    built without it sells a subscription that can never be credited.
    """
    if not WHOP_API_KEY:
        raise ValueError("WHOP_API_KEY is not configured")
    if not user_id:
        raise ValueError("A Whop checkout link needs a user id to credit.")

    body: dict = {
        "plan_id": plan_id,
        "metadata": {"user_id": user_id, **(metadata or {})},
    }
    if user_email:
        body["metadata"]["email"] = user_email
    if success_url:
        body["redirect_url"] = success_url

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{WHOP_API_BASE}/checkout_configurations",
            json=body,
            headers={
                "Authorization": f"Bearer {WHOP_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        if resp.status_code >= 400:
            # The body says which field Whop rejected; a bare status code
            # sends the operator to the wrong plan id.
            raise ValueError(
                f"Whop refused the checkout configuration ({resp.status_code}): {resp.text}"
            )
        data = resp.json()

    url = data.get("purchase_url") or data.get("checkout_url")
    if not url:
        raise ValueError(f"Whop returned no purchase_url: {data}")
    return url


def manage_url(membership_id: str = "") -> str:
    """Where this customer manages or cancels their subscription.

    Whop has no server-created portal session, so there is nothing to await
    and nothing that can expire -- this is the customer's own orders page.
    """
    base = WHOP_MANAGE_URL.rstrip("/")
    return f"{base}/{membership_id}" if membership_id else f"{base}/"


# ── Webhook verification ──────────────────────────────────────────────────────

def _signing_keys(secret: str) -> Iterable[bytes]:
    """Every key the issued secret could reasonably derive to.

    See ON VERIFYING THE SIGNATURE in the module docstring: the prefix
    handling is not documented identically by Whop and by the Standard
    Webhooks reference, and being wrong about it rejects every real payment.
    """
    raw = (secret or "").strip()
    yield raw.encode()
    if "_" in raw:
        tail = raw.split("_", 1)[1]
        yield tail.encode()
        try:
            yield base64.b64decode(tail)
        except Exception:
            pass


def _delivered_signatures(header: str) -> Iterable[str]:
    """The base64 digests in a `webhook-signature` header.

    The header carries space-separated, version-tagged entries (`v1,<digest>`)
    so a secret can be rotated with both keys live; every one of them is a
    candidate.
    """
    for part in (header or "").split():
        yield part.split(",", 1)[1] if "," in part else part


def verify_webhook(payload: bytes, headers: dict) -> dict:
    """Return the parsed event, or raise ValueError if it is not Whop's.

    `headers` is a plain dict of the request's headers; lookup is
    case-insensitive because a proxy may normalise them either way.
    """
    if not WHOP_WEBHOOK_SECRET:
        # Every webhook this deployment ever receives will be rejected and the
        # access log shows only "400". Said once, loudly, with the cause.
        logger.error(
            "Whop webhook rejected: WHOP_WEBHOOK_SECRET is not configured, so "
            "no payment event can be verified or credited."
        )
        raise ValueError("WHOP_WEBHOOK_SECRET is not configured")

    lower = {str(k).lower(): v for k, v in (headers or {}).items()}
    msg_id = lower.get("webhook-id", "")
    timestamp = lower.get("webhook-timestamp", "")
    signature = lower.get("webhook-signature", "")

    if not (msg_id and timestamp and signature):
        raise ValueError(
            "Whop webhook rejected: missing webhook-id / webhook-timestamp / "
            "webhook-signature headers."
        )

    try:
        age = abs(time.time() - int(timestamp))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Whop webhook rejected: unreadable timestamp {timestamp!r}") from exc
    if age > WEBHOOK_TOLERANCE_SECONDS:
        raise ValueError(
            f"Whop webhook rejected: timestamp is {int(age)}s out of date, which "
            f"is outside the {WEBHOOK_TOLERANCE_SECONDS}s replay window."
        )

    signed = b"%s.%s.%s" % (msg_id.encode(), timestamp.encode(), payload)
    delivered = list(_delivered_signatures(signature))
    expected = [
        base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
        for key in _signing_keys(WHOP_WEBHOOK_SECRET)
    ]
    if not any(hmac.compare_digest(e, d) for e in expected for d in delivered):
        logger.error(
            "Whop webhook rejected: signature verification failed for message "
            "%s. If Whop's dashboard shows these as failed deliveries, the "
            "endpoint's signing secret does not match WHOP_WEBHOOK_SECRET.",
            msg_id,
        )
        raise ValueError("Invalid webhook signature")

    try:
        event = json.loads(payload.decode() or "{}")
    except ValueError as exc:
        raise ValueError(f"Whop webhook rejected: body is not JSON ({exc})") from exc

    # The id travels in the header, not the body, and it is what the
    # idempotency table is keyed on -- so it is put where the handler looks.
    event.setdefault("id", msg_id)
    return event


# ── Reading an event ──────────────────────────────────────────────────────────

def _dig(data: dict, *path: str):
    """Follow a dotted path through nested dicts, or None."""
    node = data
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _first(data: dict, *paths) -> Optional[str]:
    """The first of these paths that holds a truthy value.

    Whop's payload nests its resources (`data.plan.id`) while several of its
    own examples and older API versions send them flat (`data.plan_id`). This
    reads both rather than betting the deployment on which one arrives, since
    the cost of betting wrong is a paid customer credited nothing.
    """
    for path in paths:
        value = _dig(data, *path) if isinstance(path, tuple) else data.get(path)
        if value:
            return value
    return None


def event_metadata(data: dict) -> dict:
    """The checkout metadata Whop copied onto this payment or membership."""
    for candidate in (
        _dig(data, "metadata"),
        _dig(data, "checkout_configuration", "metadata"),
        _dig(data, "checkout_session", "metadata"),
        _dig(data, "membership", "metadata"),
        _dig(data, "plan", "metadata"),
    ):
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def plan_id_of(data: dict) -> str:
    return _first(data, ("plan", "id"), "plan_id") or ""


def membership_id_of(data: dict) -> str:
    return _first(data, ("membership", "id"), "membership_id", "id") or ""


def whop_user_id_of(data: dict) -> str:
    return _first(data, ("user", "id"), "user_id") or ""


async def _resolve_user_id(data: dict) -> Optional[str]:
    """Which MuseForge account this event belongs to.

    Metadata first, because it is exact and survives every Whop-side rename.
    The profile lookups behind it are what keep a RENEWAL creditable years
    later: the membership id was written onto the profile by the first
    payment, so even a payload that lost its metadata still lands on the right
    account.
    """
    user_id = event_metadata(data).get("user_id")
    if user_id:
        return user_id

    for column, value in (
        ("whop_membership_id", membership_id_of(data)),
        ("whop_user_id", whop_user_id_of(data)),
    ):
        if value:
            row = await billing.find_profile(column, value)
            if row:
                return row.get("id")
    return None


# ── The webhook ───────────────────────────────────────────────────────────────

async def handle_webhook(payload: bytes, headers: dict) -> dict:
    """Verify a Whop delivery and apply it exactly once."""
    event = verify_webhook(payload, headers)

    event_id = event.get("id") or ""
    event_type = event.get("type") or event.get("action") or ""
    data = event.get("data") or {}

    is_new = await billing.mark_event_processed(PROVIDER, event_id)
    if not is_new:
        return {"status": "already_processed", "event_id": event_id}

    try:
        return await _dispatch_event(event_type, data)
    except Exception:
        # Same argument as the Stripe handler: the mark was taken before the
        # work, so a handler that raises must give it back, or Whop's retry
        # will be answered "already processed" and a customer who paid is
        # never credited -- with a green delivery in Whop's dashboard.
        logger.exception(
            "Whop event %s (%s) failed while being handled; releasing its "
            "idempotency mark so the retry can be processed.",
            event_id,
            event_type,
        )
        await billing.release_event_mark(PROVIDER, event_id)
        raise


async def _dispatch_event(event_type: str, data: dict) -> dict:
    """Apply one verified, not-yet-processed Whop event."""

    if event_type == "payment.succeeded":
        reason = (data.get("billing_reason") or "").lower()
        metadata = event_metadata(data)
        plan_id = plan_id_of(data)
        package = (metadata.get("credit_package") or package_for_plan_id(plan_id) or "").upper()

        # A payment with no recognisable billing_reason is treated as what its
        # PLAN says it is. Whop sends `one_time` for packs and the
        # subscription_* family for cycles, but an unset reason on a pack sale
        # would otherwise be granted a subscription allowance -- 16 credits for
        # a $19 purchase.
        is_pack = reason in ONE_TIME_REASONS or (not reason and bool(package))
        is_cycle = reason in SUBSCRIPTION_REASONS or (not reason and not package)

        user_id = await _resolve_user_id(data)
        if not user_id:
            # Nothing can be done with this one, and it must not look like a
            # success: the operator has to be able to find the payment and
            # credit it by hand.
            logger.error(
                "Whop payment %s carried no user_id in its metadata and matched "
                "no profile; it has been PAID but NOT credited.",
                data.get("id"),
            )
            return {"received": True, "type": event_type, "credited": False}

        profile_fields = {
            "whop_membership_id": membership_id_of(data),
            "whop_user_id": whop_user_id_of(data),
        }

        if is_pack:
            credits = billing.credits_in_package(package)
            if credits:
                await billing.grant_credits(
                    user_id,
                    credits,
                    profile_fields=profile_fields,
                    reason="credit_purchase",
                    validity_days=PACK_CREDIT_VALIDITY_DAYS,
                )
                return {"received": True, "type": event_type, "credits": credits}
            logger.error(
                "Whop one-off payment %s names no known credit package "
                "(metadata=%s, plan=%s); nothing was credited.",
                data.get("id"),
                package or "-",
                plan_id or "-",
            )
            return {"received": True, "type": event_type, "credited": False}

        if is_cycle:
            plan = plan_for_plan_id(plan_id) or "creator"
            credits, validity_days = allowance_for(plan, is_annual_plan_id(plan_id))
            await billing.grant_credits(
                user_id,
                credits,
                plan=plan,
                profile_fields=profile_fields,
                reason="subscription_renewal",
                validity_days=validity_days,
            )
            return {"received": True, "type": event_type, "plan": plan, "credits": credits}

    elif event_type in CANCELLATION_EVENTS:
        membership_id = membership_id_of(data)
        if membership_id:
            row = await billing.find_profile("whop_membership_id", membership_id, select="id")
            await billing.end_subscription(
                (row or {}).get("id"),
                "whop_membership_id",
                membership_id,
            )

    elif event_type == "payment.failed":
        pass  # TODO: notify user

    return {"received": True, "type": event_type}
