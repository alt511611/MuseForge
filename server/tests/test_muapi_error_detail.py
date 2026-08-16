"""Verify MuAPIClient surfaces the actual response body on failure,
instead of just httpx's generic 'status code + URL' message -- critical
for diagnosing 422 validation errors without guessing.
"""
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def _no_sleep(_seconds):
    """Backoff without the wait."""
    return None

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


# --- a died inference is retried, not re-polled --------------------------
#
# The delivered failure, in full:
#
#   Internal error: MuAPI request failed after 1 attempt(s): HTTP 400:
#   Inference error occurred while processing the request. Please try again
#   or contact support if the issue persists.
#   (on /api/v1/predictions/0d0d82a9-79b8-47c6-b55a-1203bbbe3255/result)
#
# One frame of a three-scene drama, fourteen seconds in, and the whole job
# died. Two separate things were wrong and only one of them is the obvious
# one.


def test_a_died_inference_is_recognised_as_transient():
    """`HTTP 400` on a bare GET of a prediction id is not a client error --
    there is no body to get wrong. It is the provider reporting that its own
    inference failed, in the one message that tells you to try again."""
    from tools.muapi_client import MuAPIError, is_transient_inference_error

    assert is_transient_inference_error(
        MuAPIError(
            "MuAPI request failed after 1 attempt(s): HTTP 400: Inference "
            "error occurred while processing the request. Please try again "
            "or contact support if the issue persists."
        )
    )
    assert is_transient_inference_error(MuAPIError('MuAPI job failed: {"status":"failed"}'))


def test_an_endpoint_rejection_is_not_retried():
    """A 404 or 422 fails identically every time; re-sending it is a loop
    that ends in the same place having spent the customer's time."""
    from tools.muapi_client import MuAPIError, is_transient_inference_error

    assert not is_transient_inference_error(MuAPIError("HTTP 404: not found"))
    assert not is_transient_inference_error(
        MuAPIError("HTTP 422: field `size` is required")
    )


@pytest.mark.asyncio
async def test_a_fresh_generation_is_submitted_rather_than_the_poll_repeated(
    monkeypatch,
):
    """Retrying the GET would be useless: that prediction is dead and answers
    400 for as long as anyone asks it. What has to be retried is the
    generation."""
    from tools.muapi_client import MuAPIClient, MuAPIError

    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    client = MuAPIClient("k")
    attempts = []

    async def _once(endpoint, payload, poll_interval, max_polls, is_cancelled):
        attempts.append(endpoint)
        if len(attempts) < 3:
            raise MuAPIError("HTTP 400: Inference error occurred. Please try again")
        return "https://cdn/frame.png"

    monkeypatch.setattr(client, "_generate_once", _once)
    assert await client.generate("flux-pulid", {}) == "https://cdn/frame.png"
    assert len(attempts) == 3, attempts


@pytest.mark.asyncio
async def test_a_cancelled_job_is_never_retried(monkeypatch):
    from tools.muapi_client import MuAPICancelled, MuAPIClient

    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    client = MuAPIClient("k")
    attempts = []

    async def _once(*a, **k):
        attempts.append(1)
        raise MuAPICancelled("stopped")

    monkeypatch.setattr(client, "_generate_once", _once)
    with pytest.raises(MuAPICancelled):
        await client.generate("flux-pulid", {})
    assert len(attempts) == 1


@pytest.mark.asyncio
async def test_the_image_path_falls_back_once_the_retries_are_spent(monkeypatch):
    """After the client has re-submitted and still failed, the generator's own
    fallback to a different model has to recognise the error -- it did not,
    which is why this reached the user as a dead job rather than a frame from
    the backup endpoint."""
    from tools.muapi_client import MuAPIError
    from tools.muapi_image_generator import MuAPIImageGenerator

    generator = MuAPIImageGenerator("k")
    seen = []

    async def _generate(endpoint, payload, **kwargs):
        seen.append(endpoint)
        if endpoint != generator.LEGACY_SIZE_ENDPOINT:
            raise MuAPIError("HTTP 400: Inference error occurred. Please try again")
        return "https://cdn/fallback.png"

    monkeypatch.setattr(generator.client, "generate", _generate)
    assert await generator.generate_image("a still") == "https://cdn/fallback.png"
    assert generator.LEGACY_SIZE_ENDPOINT in seen
