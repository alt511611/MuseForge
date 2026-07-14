"""Credit system security tests.

Covers:
- Unauthenticated users get 401 outside demo mode
- Insufficient-credit users get 402
- Atomic credit deduction (RPC returns -1 → 402, no double-spend)
- Stripe webhook idempotency (duplicate event_id → skip processing)
"""
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ─── Module-level: clear demo flag so we can test non-demo behaviour ──────────
os.environ.pop("MUSEFORGE_DEMO", None)
os.environ.pop("MUAPI_KEY", None)  # no key → demo mode in _is_demo()


# ── Helper: force non-demo mode ───────────────────────────────────────────────

def _set_demo(value: bool):
    """Toggle the in-process demo flag."""
    import api as _api
    _api.DEMO_FLAG = value


# ══════════════════════════════════════════════════════════════════════════════
# 1. Anonymous bypass — 401 outside demo mode
# ══════════════════════════════════════════════════════════════════════════════

def test_anon_user_gets_401_outside_demo():
    """Unauthenticated requests must return 401 when MUAPI_KEY is set (non-demo)."""
    from fastapi.testclient import TestClient
    import api as _api

    # Simulate a real API key being present (non-demo)
    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real_key_here"}):

        # Ensure _is_demo() returns False (key is set, flag is False)
        assert _api._is_demo() is False

        tc = TestClient(_api.app, raise_server_exceptions=False)
        resp = tc.post(
            "/api/generate",
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 2},
            # No Authorization header → get_optional_user returns None
        )
        assert resp.status_code == 401
        assert "sign in" in resp.json()["detail"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# 2. Insufficient credits → 402
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_insufficient_credits_returns_false():
    """_deduct_credits returns False when the Supabase RPC returns -1."""
    import api as _api

    mock_resp = MagicMock()
    mock_resp.json.return_value = -1  # RPC signals insufficient balance

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "fake_service_key"), \
         patch("api.httpx.AsyncClient", return_value=mock_client):

        result = await _api._deduct_credits("user-123", 5)
        assert result is False


@pytest.mark.asyncio
async def test_sufficient_credits_returns_true():
    """_deduct_credits returns True when the Supabase RPC returns a non-negative balance."""
    import api as _api

    mock_resp = MagicMock()
    mock_resp.json.return_value = 10  # 15 credits → deduct 5 → 10 remaining

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "fake_service_key"), \
         patch("api.httpx.AsyncClient", return_value=mock_client):

        result = await _api._deduct_credits("user-123", 5)
        assert result is True


# ══════════════════════════════════════════════════════════════════════════════
# 3. Atomic deduction — concurrent requests cannot double-spend
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_concurrent_deductions_use_rpc_atomically():
    """Simulate two concurrent deduction requests.

    The mock mirrors the DB atomicity: first call returns the new balance,
    second call (same credits) returns -1 because the first already consumed them.
    The important guarantee is that each request calls the RPC once — it does NOT
    do a read-then-write that a second concurrent request could race between.
    """
    import api as _api

    call_count = 0

    async def _fake_post(url, **kwargs):
        nonlocal call_count
        resp = MagicMock()
        if "rpc/deduct_credits" in url:
            call_count += 1
            # First call succeeds, second call returns -1 (atomic DB constraint)
            resp.json.return_value = 5 if call_count == 1 else -1
        else:
            resp.json.return_value = {}
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = _fake_post

    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "fake_service_key"), \
         patch("api.httpx.AsyncClient", return_value=mock_client):

        results = await asyncio.gather(
            _api._deduct_credits("user-abc", 5),
            _api._deduct_credits("user-abc", 5),
        )

    # Exactly one should succeed and one should fail
    assert results.count(True) == 1
    assert results.count(False) == 1
    # Both requests hit the RPC once each — no extra reads
    assert call_count == 2


# ══════════════════════════════════════════════════════════════════════════════
# 4. Stripe webhook idempotency
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_stripe_webhook_idempotent_for_duplicate_event_ids():
    """Credits must be added only once when the same Stripe event arrives twice."""
    import stripe_integration as si

    credits_added = []

    async def _fake_add_credits(user_id, credits_delta, **kwargs):
        credits_added.append(credits_delta)

    seen_events: set[str] = set()

    async def _fake_mark_processed(event_id: str) -> bool:
        if event_id in seen_events:
            return False  # duplicate
        seen_events.add(event_id)
        return True

    fake_event = {
        "id": "evt_test_idempotency_001",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "payment",
                "client_reference_id": "user-xyz",
                "customer": "cus_test",
                "subscription": None,
                "metadata": {"credit_package": "SMALL"},
            }
        },
    }

    with patch.object(si, "_mark_event_processed", side_effect=_fake_mark_processed), \
         patch.object(si, "_add_credits_to_profile", side_effect=_fake_add_credits), \
         patch.object(si, "STRIPE_WEBHOOK_SECRET", "whsec_test_secret"), \
         patch("stripe_integration.stripe.Webhook.construct_event", return_value=fake_event):

        # First delivery
        await si.handle_webhook(b"payload", "sig_header")
        # Second delivery — same event_id
        await si.handle_webhook(b"payload", "sig_header")

    # Credits should only have been added once
    assert len(credits_added) == 1
    assert credits_added[0] == si.CREDIT_PACKAGES["SMALL"]["credits"]
