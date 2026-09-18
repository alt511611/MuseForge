"""What a failing dependency is allowed to turn into.

Four of these are about money and one is about the door, and they share a
shape: something downstream answered with the wrong KIND of thing, and the
code read it as the right kind.

- A deduction RPC that returned an error object was compared against -1,
  which an object never equals, so the failure read as a successful charge
  and the render ran for free.
- A balance endpoint that returned `true` satisfied `isinstance(x, int)`,
  because bool subclasses int in Python, and the customer was shown a
  balance of 1 credit.
- A hostile origin satisfied `re.match`, which anchors only the start of the
  string, so `https://museforge.studio.attacker.com` was echoed back as an
  allowed origin.

Staying fail-OPEN on an outage is the deliberate choice throughout: a paying
customer is not blocked because the database had a bad minute. What was
missing is that the choice left no record, so nobody could tell a free render
from a paid one afterwards.
"""

import logging
import os
import re
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api as _api  # noqa: E402


def _client_returning(resp):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=resp)
    client.get = AsyncMock(return_value=resp)
    return client


def _response(status_code=200, body=None, text=""):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = text
    return resp


# ── the deduction ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_deduction_rpc_that_errored_is_not_a_charge_that_happened(caplog):
    """500 from PostgREST: the job goes through, and the log says it was free."""
    resp = _response(
        status_code=500,
        body={"message": "function deduct_credits does not exist"},
        text='{"message":"function deduct_credits does not exist"}',
    )

    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "key"), \
         patch("api.httpx.AsyncClient", return_value=_client_returning(resp)), \
         caplog.at_level(logging.ERROR, logger="api"):
        allowed = await _api._deduct_credits("user-1", 5)

    assert allowed is True, "fail-open is the deliberate choice"
    assert any(
        "deduct_credits RPC failed" in record.message for record in caplog.records
    ), "a render nobody was charged for has to leave a record"


@pytest.mark.asyncio
async def test_an_error_object_is_not_a_balance(caplog):
    """200 with a body that is not a number. The old `body == -1` said False."""
    resp = _response(status_code=200, body={"error": "deadlock detected"})

    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "key"), \
         patch("api.httpx.AsyncClient", return_value=_client_returning(resp)), \
         caplog.at_level(logging.ERROR, logger="api"):
        allowed = await _api._deduct_credits("user-1", 5)

    assert allowed is True
    assert any("not a balance" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_an_insufficient_balance_is_still_a_refusal():
    """The one answer that must keep meaning no."""
    resp = _response(status_code=200, body=-1)

    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "key"), \
         patch("api.httpx.AsyncClient", return_value=_client_returning(resp)):
        assert await _api._deduct_credits("user-1", 5) is False


# ── the balance ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_true_is_not_one_credit():
    """isinstance(True, int) is True, and a customer with `true` credits is not
    a customer with one credit. -1 means "could not be read", which is what
    this is."""
    resp = _response(status_code=200, body=True)
    client = _client_returning(resp)
    # The profiles fallback answers the same nonsense, so the only honest
    # answer left is "unknown".
    client.get = AsyncMock(return_value=_response(status_code=200, body=[]))

    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "key"), \
         patch("api.httpx.AsyncClient", return_value=client):
        assert await _api._get_user_credits("user-1") == -1


@pytest.mark.asyncio
async def test_a_real_balance_still_comes_back():
    resp = _response(status_code=200, body=42)

    with patch("api.SUPABASE_URL", "https://fake.supabase.co"), \
         patch("api.SUPABASE_SERVICE_KEY", "key"), \
         patch("api.httpx.AsyncClient", return_value=_client_returning(resp)):
        assert await _api._get_user_credits("user-1") == 42


# ── the door ─────────────────────────────────────────────────────────────────

class _FakeRequest:
    def __init__(self, origin):
        self.headers = {"origin": origin}


@pytest.mark.parametrize(
    "origin",
    [
        "https://museforge.studio.attacker.com",
        "https://museforge.studio.evil.example",
        "https://preview.vercel.app.attacker.com",
        "https://evil.com/?x=https://museforge.studio",
    ],
)
def test_an_origin_that_merely_starts_right_is_refused(origin):
    assert _api._cors_header_for(_FakeRequest(origin)) == {}


@pytest.mark.parametrize(
    "origin",
    [
        "https://museforge.studio",
        "https://www.museforge.studio",
        "https://muse-forge-i3ah-1vo7vxdxh-alt-051.vercel.app",
    ],
)
def test_the_origins_the_product_actually_ships_from_still_pass(origin):
    header = _api._cors_header_for(_FakeRequest(origin))

    assert header.get("Access-Control-Allow-Origin") == origin


def test_the_regex_the_middleware_gets_is_anchored_at_both_ends():
    """Starlette matches allow_origin_regex with fullmatch, so a pattern that
    only makes sense under `match` is a pattern the middleware will refuse to
    honour -- and this manual path has to agree with the middleware."""
    for origin in ("https://museforge.studio", "https://x.vercel.app"):
        assert re.fullmatch(_api.ALLOWED_ORIGIN_REGEX, origin)
    assert not re.fullmatch(
        _api.ALLOWED_ORIGIN_REGEX, "https://museforge.studio.attacker.com"
    )


# ── the rate limiter ─────────────────────────────────────────────────────────

def test_a_spray_of_addresses_does_not_grow_the_limiter_forever():
    """One key per address, none of them ever removed, is a memory leak with a
    trivially cheap trigger: a botnet only has to be varied, not fast."""
    limiter = _api._SlidingWindowRateLimiter(limit=5, window=60.0)
    limiter._SWEEP_THRESHOLD = 50

    for i in range(500):
        limiter.allow(f"10.0.0.{i}")

    assert len(limiter._hits) <= 51


def test_the_limiter_still_refuses_the_sixth_request_in_a_window():
    limiter = _api._SlidingWindowRateLimiter(limit=5, window=60.0)

    assert [limiter.allow("user-1") for _ in range(6)] == [
        True, True, True, True, True, False,
    ]


def test_a_key_that_was_never_seen_is_not_created_by_asking():
    """defaultdict made every lookup a write. Nothing here reads before it
    decides to record, but the store should not grow on a refusal either."""
    limiter = _api._SlidingWindowRateLimiter(limit=1, window=60.0)
    limiter.allow("user-1")
    limiter.allow("user-1")

    assert list(limiter._hits) == ["user-1"]


# ── the job's own front door ─────────────────────────────────────────────────

def test_the_video_and_the_stream_ask_who_is_calling():
    """Both used to take a job id and nothing else, so anyone holding an id --
    a shared link, a log line, a browser history -- could download somebody
    else's film and watch their render live."""
    import inspect

    for endpoint in (_api.get_job_video, _api.stream_job):
        source = inspect.getsource(endpoint)
        assert "current_user" in source, endpoint.__name__
        assert "_assert_may_read_job" in source, endpoint.__name__


def test_another_signed_in_customer_is_refused():
    from fastapi import HTTPException

    from auth import AuthUser

    with pytest.raises(HTTPException) as caught:
        _api._assert_may_read_job("user-owner", AuthUser("user-someone-else", "e@x"))

    assert caught.value.status_code == 403


def test_the_owner_and_an_admin_are_not():
    from auth import AuthUser

    _api._assert_may_read_job("user-owner", AuthUser("user-owner", "e@x"))
    _api._assert_may_read_job("user-owner", AuthUser("user-root", "e@x", role="admin"))


def test_a_caller_with_no_token_is_not_refused():
    """A <video> tag and an EventSource cannot send an Authorization header,
    so refusing them would break the owner's own page."""
    _api._assert_may_read_job("user-owner", None)
