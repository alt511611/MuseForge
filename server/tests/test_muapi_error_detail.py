"""Verify MuAPIClient surfaces the actual response body on failure,
instead of just httpx's generic 'status code + URL' message -- critical
for diagnosing 422 validation errors without guessing.
"""
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


@pytest.mark.asyncio
async def test_error_message_includes_response_body(monkeypatch):
    from tools.muapi_client import MuAPIClient, MuAPIError

    fake_body = '{"detail": "aspect_ratio is not a valid field for this model"}'

    class FakeResponse:
        status_code = 422
        text = fake_body

        def raise_for_status(self):
            request = httpx.Request("POST", "https://api.muapi.ai/api/v1/kling-o1-image-to-video")
            raise httpx.HTTPStatusError("422 error", request=request, response=self)

    async def fake_request(self, method, url, headers=None, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    client = MuAPIClient(api_key="test-key", max_retries=0)
    with pytest.raises(MuAPIError) as exc_info:
        async with httpx.AsyncClient() as http_client:
            await client._request_with_retry(http_client, "POST", "https://api.muapi.ai/api/v1/kling-o1-image-to-video")

    assert "aspect_ratio is not a valid field" in str(exc_info.value)


@pytest.mark.asyncio
async def test_non_retryable_client_error_is_not_retried(monkeypatch):
    """A terminal 400 (MuAPI reporting the prediction itself failed) must
    fail fast so the caller can fall back, instead of burning the full
    retry budget with backoff on a request that can never succeed."""
    from tools.muapi_client import MuAPIClient, MuAPIError

    calls = {"n": 0}

    class FakeResponse:
        status_code = 400
        text = '{"detail": {"status": "failed", "error": "upstream 500"}}'

        def raise_for_status(self):
            request = httpx.Request("GET", "https://api.muapi.ai/api/v1/predictions/x/result")
            raise httpx.HTTPStatusError("400 error", request=request, response=self)

    async def fake_request(self, method, url, headers=None, **kwargs):
        calls["n"] += 1
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)

    client = MuAPIClient(api_key="test-key", max_retries=3)
    with pytest.raises(MuAPIError) as exc_info:
        async with httpx.AsyncClient() as http_client:
            await client._request_with_retry(
                http_client, "GET", "https://api.muapi.ai/api/v1/predictions/x/result"
            )

    assert calls["n"] == 1
    assert "1 attempt" in str(exc_info.value)
    assert "upstream 500" in str(exc_info.value)


@pytest.mark.asyncio
async def test_retryable_server_error_still_retries(monkeypatch):
    from tools.muapi_client import MuAPIClient, MuAPIError

    calls = {"n": 0}

    class FakeResponse:
        status_code = 503
        text = "unavailable"
        request = httpx.Request("GET", "https://api.muapi.ai/api/v1/predictions/x/result")

        def raise_for_status(self):
            request = httpx.Request("GET", "https://api.muapi.ai/api/v1/predictions/x/result")
            raise httpx.HTTPStatusError("503", request=request, response=self)

    async def fake_request(self, method, url, headers=None, **kwargs):
        calls["n"] += 1
        return FakeResponse()

    async def no_sleep(_):
        return None

    monkeypatch.setattr(httpx.AsyncClient, "request", fake_request)
    monkeypatch.setattr("tools.muapi_client.asyncio.sleep", no_sleep)

    client = MuAPIClient(api_key="test-key", max_retries=2)
    with pytest.raises(MuAPIError):
        async with httpx.AsyncClient() as http_client:
            await client._request_with_retry(
                http_client, "GET", "https://api.muapi.ai/api/v1/predictions/x/result"
            )

    assert calls["n"] == 3
