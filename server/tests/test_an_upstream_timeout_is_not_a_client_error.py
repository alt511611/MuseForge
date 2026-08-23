"""MuAPI proxies its upstreams, and a 400 can be carrying a 504.

From a delivered job, the whole of what scene 0's lip sync cost::

    Lip sync unavailable for this scene, using the unsynced clip: MuAPI
    request failed after 1 attempt(s): HTTP 400: Unexpected status code:
    504 (on /api/v1/predictions/34151906-.../result)

A bare GET of a finished prediction -- no body, nothing to get wrong -- came
back 400 because MuAPI's own upstream had timed out. 504 has been in
RETRYABLE_STATUS since the module was written; the gate simply never saw it,
because it reads `resp.status_code`, and that was the 400. So the single most
retryable failure there is got one attempt, and the scene shipped with a
closed mouth over a paid-for line.

Deliberately narrow: only a number introduced AS a status code counts, so the
terminal 400s the gate exists to fail fast on still fail fast.
"""
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")

from tools.muapi_client import (  # noqa: E402
    MuAPIClient,
    MuAPIError,
    quoted_retryable_status,
)

URL = "https://api.muapi.ai/api/v1/predictions/34151906/result"


def _responder(status, body, calls):
    class FakeResponse:
        status_code = status
        text = body
        request = httpx.Request("GET", URL)

        def raise_for_status(self):
            raise httpx.HTTPStatusError(
                str(status), request=httpx.Request("GET", URL), response=self
            )

    async def fake_request(self, method, url, headers=None, **kwargs):
        calls["n"] += 1
        return FakeResponse()

    return fake_request


async def _no_sleep(_seconds):
    return None


# ── reading the quoted status ───────────────────────────────────────────────


def test_the_status_the_provider_quoted_is_the_one_that_counts():
    assert quoted_retryable_status("Unexpected status code: 504") == 504
    assert quoted_retryable_status("unexpected status code 502") == 502
    assert quoted_retryable_status("Status Code: 429") == 429


def test_a_quoted_status_that_is_not_retryable_is_not_retryable():
    assert quoted_retryable_status("Unexpected status code: 404") is None
    assert quoted_retryable_status("Unexpected status code: 400") is None


def test_a_bare_number_is_not_a_status_code():
    """A prediction id, a duration and a byte count all contain digits. Only
    a number introduced as a status code is the provider naming its upstream."""
    assert quoted_retryable_status("prediction 34151906-504a-4978-bb19") is None
    assert quoted_retryable_status("504") is None
    assert quoted_retryable_status("audio is 503 ms long") is None
    assert quoted_retryable_status("") is None
    assert quoted_retryable_status(None) is None


# ── what the gate does with it ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_delivered_failure_is_retried(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(
        httpx.AsyncClient,
        "request",
        _responder(400, '{"detail": "Unexpected status code: 504"}', calls),
    )
    monkeypatch.setattr("tools.muapi_client.asyncio.sleep", _no_sleep)

    client = MuAPIClient(api_key="test-key", max_retries=2)
    with pytest.raises(MuAPIError):
        async with httpx.AsyncClient() as http_client:
            await client._request_with_retry(http_client, "GET", URL)

    assert calls["n"] == 3, "the upstream timeout was still treated as terminal"


@pytest.mark.asyncio
async def test_a_terminal_client_error_still_fails_fast(monkeypatch):
    """The gate's whole reason for existing: a 400 that means what it says
    must not burn the retry budget with backoff on a request that can never
    succeed."""
    calls = {"n": 0}
    monkeypatch.setattr(
        httpx.AsyncClient,
        "request",
        _responder(400, '{"detail": "prediction 34151906 failed"}', calls),
    )
    monkeypatch.setattr("tools.muapi_client.asyncio.sleep", _no_sleep)

    client = MuAPIClient(api_key="test-key", max_retries=2)
    with pytest.raises(MuAPIError):
        async with httpx.AsyncClient() as http_client:
            await client._request_with_retry(http_client, "GET", URL)

    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_a_refused_reference_still_fails_fast(monkeypatch):
    """Deterministic: the portrait will not contain the object on the fourth
    ask either, and the caller has a real fallback waiting."""
    calls = {"n": 0}
    monkeypatch.setattr(
        httpx.AsyncClient,
        "request",
        _responder(
            400,
            '{"detail": "input image does not contain the object described"}',
            calls,
        ),
    )
    monkeypatch.setattr("tools.muapi_client.asyncio.sleep", _no_sleep)

    client = MuAPIClient(api_key="test-key", max_retries=2)
    with pytest.raises(MuAPIError):
        async with httpx.AsyncClient() as http_client:
            await client._request_with_retry(http_client, "GET", URL)

    assert calls["n"] == 1
