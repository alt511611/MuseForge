"""Shared MuAPI submit-and-poll client with retry/backoff resilience."""

import asyncio
import os
import random
from typing import Any, Callable, Dict, List, Optional

import httpx

MUAPI_BASE = os.environ.get("MUAPI_BASE", "https://api.muapi.ai/api/v1")
DEFAULT_POLL_INTERVAL = 2.0
# 240 * 2s = 8 min per MuAPI job — headroom for longer Kling clips (up to 15s
# finale) without failing long multi-scene dramas early.
DEFAULT_MAX_POLLS = 240
DEFAULT_MAX_RETRIES = 3
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class MuAPIError(Exception):
    """Raised when a MuAPI request fails in a non-recoverable way."""


class MuAPICancelled(MuAPIError):
    """Raised when is_cancelled() flips true while waiting on a MuAPI job.

    Found via a free (no-cost) audit of the cancellation path: a job
    marked cancelled by the user previously only stopped shots that
    hadn't STARTED their MuAPI call yet -- any request already in flight
    (submitted, waiting on poll_result's sleep loop) ran to completion
    regardless, silently spending real money on work the user had already
    cancelled. Checking is_cancelled() between poll iterations lets a
    cancel take effect within one poll_interval instead of the full
    remaining generation time.
    """


#: Keys a completed prediction may carry its file under. ``outputs`` is what
#: the image and video endpoints return and stays first, so their behaviour is
#: byte-identical; the rest exist because reading ONE key turns any other
#: shape into "Completed but no outputs", i.e. a finished, paid-for
#: generation thrown away over its envelope. The result is fed to an HTTP
#: download either way, so a wrong guess cannot do worse than the failure it
#: replaces.
_OUTPUT_KEYS = ("outputs", "output", "results", "result", "urls", "url")

#: Where a URL hides inside a per-output object.
_URL_KEYS = (
    "url", "audio_url", "video_url", "image_url",
    "output_url", "file_url", "signed_url", "download_url",
)


def _as_url(entry: Any) -> str:
    """A URL string from an output entry, whether it is one or wraps one."""
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict):
        for key in _URL_KEYS:
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def extract_output_urls(data: Dict[str, Any]) -> List[str]:
    """Every file URL in a completed prediction, in the order returned."""
    for key in _OUTPUT_KEYS:
        value = data.get(key)
        if value is None:
            continue
        entries = value if isinstance(value, list) else [value]
        urls = [url for url in (_as_url(entry) for entry in entries) if url]
        if urls:
            return urls
    return []


class MuAPIClient:
    def __init__(self, api_key: str, timeout: float = 120.0, max_retries: int = DEFAULT_MAX_RETRIES):
        self.api_key = api_key or os.environ.get("MUAPI_KEY", "")
        self.timeout = timeout
        self.max_retries = max_retries

    def _headers(self) -> Dict[str, str]:
        return {"x-api-key": self.api_key, "Content-Type": "application/json"}

    async def _request_with_retry(self, client: httpx.AsyncClient, method: str, url: str, **kwargs) -> httpx.Response:
        """Issue an HTTP request, retrying transient failures with exponential backoff + jitter."""
        last_exc: Exception = MuAPIError("request never attempted")
        attempts = 0
        for attempt in range(self.max_retries + 1):
            attempts = attempt + 1
            try:
                resp = await client.request(method, url, headers=self._headers(), **kwargs)
                if resp.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                    raise httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                return resp
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                # raise_for_status() above raises on ANY 4xx/5xx, so without
                # this gate a terminal client error (400 "prediction failed",
                # 401 bad key, 422 bad payload) was retried the full 4 times
                # with backoff -- burning ~7s before the caller could fall
                # back, and never succeeding. Only RETRYABLE_STATUS (and
                # transport errors, which carry no response) are worth a retry.
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and status not in RETRYABLE_STATUS:
                    break
                backoff = min(2 ** attempt + random.uniform(0, 0.5), 10.0)
                await asyncio.sleep(backoff)
        raise MuAPIError(
            f"MuAPI request failed after {attempts} attempt(s): "
            f"{last_exc}{self._response_detail(last_exc)}"
        )

    @staticmethod
    def _response_detail(exc: Exception) -> str:
        """httpx.HTTPStatusError's default str() only includes the status
        code and URL, discarding the actual response body -- which for a
        422 (or most 4xx) almost always contains the precise validation
        error (e.g. 'field X is required' or 'Y is not a valid value for
        Z'). Surface it so failures are diagnosable from logs alone
        instead of requiring guesswork against third-party docs."""
        response = getattr(exc, "response", None)
        if response is None:
            return ""
        try:
            return f" | Response body: {response.text[:1000]}"
        except Exception:
            return ""

    async def submit(self, endpoint: str, payload: Dict[str, Any]) -> str:
        if not self.api_key:
            raise MuAPIError("MUAPI_KEY is not configured")

        url = f"{MUAPI_BASE}/{endpoint.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await self._request_with_retry(client, "POST", url, json=payload)
            data = resp.json()

        request_id = data.get("request_id") or data.get("id")
        if not request_id:
            raise MuAPIError(f"No request_id in MuAPI response: {data}")
        return request_id

    async def poll_result(
        self,
        request_id: str,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_polls: int = DEFAULT_MAX_POLLS,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> List[str]:
        url = f"{MUAPI_BASE}/predictions/{request_id}/result"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for _ in range(max_polls):
                if is_cancelled and is_cancelled():
                    raise MuAPICancelled(f"Job cancelled while polling {request_id}")

                resp = await self._request_with_retry(client, "GET", url)
                data = resp.json()
                status = data.get("status", "")

                if status == "completed":
                    outputs = extract_output_urls(data)
                    if outputs:
                        return outputs
                    raise MuAPIError(f"Completed but no outputs: {data}")

                if status in ("failed", "cancelled"):
                    raise MuAPIError(f"MuAPI job {status}: {data.get('error', data)}")

                if is_cancelled and is_cancelled():
                    raise MuAPICancelled(f"Job cancelled while polling {request_id}")
                await asyncio.sleep(poll_interval)

        raise MuAPIError(f"MuAPI job timed out after {max_polls * poll_interval}s")

    async def generate(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_polls: int = DEFAULT_MAX_POLLS,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        request_id = await self.submit(endpoint, payload)
        outputs = await self.poll_result(request_id, poll_interval, max_polls, is_cancelled=is_cancelled)
        return outputs[0]
