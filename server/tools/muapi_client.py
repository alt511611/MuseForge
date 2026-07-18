"""Shared MuAPI submit-and-poll client with retry/backoff resilience."""

import asyncio
import os
import random
from typing import Any, Dict, List

import httpx

MUAPI_BASE = os.environ.get("MUAPI_BASE", "https://api.muapi.ai/api/v1")
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_MAX_POLLS = 180
DEFAULT_MAX_RETRIES = 3
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class MuAPIError(Exception):
    """Raised when a MuAPI request fails in a non-recoverable way."""


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
        for attempt in range(self.max_retries + 1):
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
                backoff = min(2 ** attempt + random.uniform(0, 0.5), 10.0)
                await asyncio.sleep(backoff)
        raise MuAPIError(
            f"MuAPI request failed after {self.max_retries + 1} attempts: "
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
    ) -> List[str]:
        url = f"{MUAPI_BASE}/predictions/{request_id}/result"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for _ in range(max_polls):
                resp = await self._request_with_retry(client, "GET", url)
                data = resp.json()
                status = data.get("status", "")

                if status == "completed":
                    outputs = data.get("outputs") or []
                    if outputs:
                        return outputs
                    raise MuAPIError(f"Completed but no outputs: {data}")

                if status in ("failed", "cancelled"):
                    raise MuAPIError(f"MuAPI job {status}: {data.get('error', data)}")

                await asyncio.sleep(poll_interval)

        raise MuAPIError(f"MuAPI job timed out after {max_polls * poll_interval}s")

    async def generate(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_polls: int = DEFAULT_MAX_POLLS,
    ) -> str:
        request_id = await self.submit(endpoint, payload)
        outputs = await self.poll_result(request_id, poll_interval, max_polls)
        return outputs[0]
