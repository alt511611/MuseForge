"""Shared MuAPI submit-and-poll client with retry/backoff resilience."""

import asyncio
import json
import logging
import os
import random
from typing import Any, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

MUAPI_BASE = os.environ.get("MUAPI_BASE", "https://api.muapi.ai/api/v1")
DEFAULT_POLL_INTERVAL = 2.0
# 240 * 2s = 8 min per MuAPI job — headroom for longer Kling clips (up to 15s
# finale) without failing long multi-scene dramas early.
DEFAULT_MAX_POLLS = 240
DEFAULT_MAX_RETRIES = 3
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


#: How many EXTRA generations to submit when the provider's inference fails.
#:
#: Not the same thing as the HTTP retry above, and the difference is the whole
#: point. A delivered failure::
#:
#:     MuAPI request failed after 1 attempt(s): HTTP 400: Inference error
#:     occurred while processing the request. Please try again or contact
#:     support if the issue persists.
#:     (on /api/v1/predictions/0d0d82a9-.../result)
#:
#: That 400 came from a bare GET of a prediction id -- a request with no body
#: and nothing to get wrong -- so it is not a client error at all; it is the
#: provider saying its own inference died, in the one place its own message
#: tells you to try again. Retrying the GET would be useless: that prediction
#: is dead and will 400 forever. What has to be retried is the GENERATION.
#:
#: Worth knowing before raising it: if MuAPI bills failed inferences, each
#: extra attempt is another charge. Two is chosen to survive a blip without
#: turning a systematically failing model into a bill.
GENERATION_RETRY_ATTEMPTS = int(
    os.environ.get("MUSEFORGE_GENERATION_RETRIES", "2") or 2
)

#: Fragments that mark a provider-side inference failure rather than a bad
#: request. Matched case-insensitively against the whole error text.
_TRANSIENT_INFERENCE_MARKERS = (
    "inference error",
    "please try again",
    "internal error",
    '"status":"failed"',
    "job failed",
)


def is_transient_inference_error(exc: Exception) -> bool:
    """True when the provider's inference failed and a fresh attempt may work.

    Deliberately narrow. A 404 or a 422 means this endpoint does not exist or
    will not take this payload, and re-sending it is a loop that ends in the
    same place having spent the customer's time; those keep failing fast.
    """
    message = str(exc).lower().replace(" ", "")
    return any(
        marker.replace(" ", "") in message for marker in _TRANSIENT_INFERENCE_MARKERS
    )


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


#: Keys a provider error message hides under, outermost first. Nested because
#: a failed prediction arrives wrapped in its own record:
#: ``{"detail": {"id": ..., "status": "failed", "error": "<the sentence>"}}``.
_MESSAGE_KEYS = ("error", "message", "detail", "msg", "reason")


def _dig_message(node: Any, depth: int = 0) -> str:
    """The human sentence inside an error envelope, however deep it is."""
    if depth > 5:
        return ""
    if isinstance(node, str):
        return node.strip()
    if isinstance(node, list):
        return "; ".join(
            part for part in (_dig_message(x, depth + 1) for x in node) if part
        )
    if isinstance(node, dict):
        for key in _MESSAGE_KEYS:
            if key in node:
                found = _dig_message(node[key], depth + 1)
                if found:
                    return found
    return ""


def provider_message(body: str) -> str:
    """The provider's own explanation, unwrapped from its JSON envelope.

    A failed voice job reached the user as::

        HTTP 400 on /api/v1/predictions/<uuid>/result | Response body:
        {"detail":{"id":"<uuid>","status":"failed","error":"Invalid voice…

    -- 214 characters of envelope in front of the only clause anyone needed,
    which is exactly where the warning's character budget ran out. Everything
    before ``error`` is either already known (the endpoint, the id) or noise
    (the JSON punctuation), so the message is dug out and the wrapper dropped.
    Returns "" when the body is not JSON, so raw bodies still print in full.
    """
    try:
        return _dig_message(json.loads(body or ""))
    except (ValueError, TypeError):
        return ""


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
    # Last: the file hanging directly off the response with no wrapper at all
    # (`{"id": ..., "audio_url": ...}`). Checked after every wrapper so a
    # response carrying both keeps returning the wrapped outputs it always did.
    direct = _as_url(data)
    return [direct] if direct else []


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
            f"{self._describe(last_exc)}"
        )

    @classmethod
    def _describe(cls, exc: Exception) -> str:
        """The failure in as few characters as carry meaning.

        httpx's own message spends most of its length on a link to MDN's
        page about HTTP status codes, which nobody reading a job's warning
        needs and which crowded out the one part that is specific to this
        failure: the body. Seen in production as a 400 that reached the user
        as "…For more information check: https://developer.mozilla.org/…"
        with the provider's actual explanation truncated off the end.
        """
        response = getattr(exc, "response", None)
        if response is None:
            return f"{exc}{cls._response_detail(exc)}"
        # When the provider explained itself, its sentence IS the failure, so
        # it leads. The path follows it rather than crowding it out: a voice
        # refused at submit and a voice refused on the finished prediction read
        # identically ("HTTP 400: Internal Error, Please try again later.") and
        # mean different things -- one spent nothing, the other spent a scene.
        request = getattr(response, "request", None)
        where = getattr(getattr(request, "url", None), "path", "") or ""
        message = cls._provider_message(exc)
        if message:
            tail = f" (on {where})" if where else ""
            return f"HTTP {response.status_code}: {message[:1000]}{tail}"
        return f"HTTP {response.status_code} on {where}{cls._response_detail(exc)}"

    @staticmethod
    def _provider_message(exc: Exception) -> str:
        """The provider's own words, or "" if it sent none we can find."""
        response = getattr(exc, "response", None)
        if response is None:
            return ""
        try:
            return provider_message(response.text)
        except Exception:
            return ""

    @classmethod
    def _response_detail(cls, exc: Exception) -> str:
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
            message = provider_message(response.text)
            if message:
                return f" | {message[:1000]}"
            return f" | Response body: {response.text[:1000]}"
        except Exception:
            return ""

    async def _submit_raw(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST the job and return the provider's whole answer.

        Kept separate from submit() because the answer is not always just a
        ticket: an endpoint fast enough to finish inline can hand back the
        finished file, and reading only the ticket out of it sends the caller
        off to poll for a prediction that was never queued.
        """
        if not self.api_key:
            raise MuAPIError("MUAPI_KEY is not configured")

        url = f"{MUAPI_BASE}/{endpoint.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await self._request_with_retry(client, "POST", url, json=payload)
            data = resp.json()
        return data if isinstance(data, dict) else {}

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
        """Submit a job and wait for its file, re-submitting a died inference.

        The retry here is a NEW prediction, not another poll of the old one:
        an inference that failed leaves a prediction that answers 400 for as
        long as anyone asks it (see GENERATION_RETRY_ATTEMPTS). Cancellation
        and endpoint rejections are never retried -- the first is the user's
        decision and the second would fail identically every time.
        """
        last_exc: Optional[MuAPIError] = None
        for attempt in range(GENERATION_RETRY_ATTEMPTS + 1):
            if is_cancelled and is_cancelled():
                raise MuAPICancelled(f"Job cancelled before {endpoint}")
            try:
                return await self._generate_once(
                    endpoint, payload, poll_interval, max_polls, is_cancelled
                )
            except MuAPICancelled:
                raise
            except MuAPIError as exc:
                last_exc = exc
                if attempt >= GENERATION_RETRY_ATTEMPTS or not is_transient_inference_error(exc):
                    raise
                backoff = min(2**attempt + random.uniform(0, 0.5), 10.0)
                logger.warning(
                    "%s inference failed (attempt %d/%d), submitting a fresh "
                    "generation in %.1fs: %s",
                    endpoint,
                    attempt + 1,
                    GENERATION_RETRY_ATTEMPTS + 1,
                    backoff,
                    exc,
                )
                await asyncio.sleep(backoff)
        raise last_exc or MuAPIError(f"{endpoint} never attempted")

    async def _generate_once(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_polls: int = DEFAULT_MAX_POLLS,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        data = await self._submit_raw(endpoint, payload)

        # A job that finished inline hands the file back on the spot. Reading
        # only the ticket out of that answer and then polling
        # /predictions/{id}/result is how a SUCCESSFUL generation became a
        # 400 Bad Request: the id belongs to a record that was never queued
        # as a prediction. Checked before the ticket, and only when the
        # response actually carries a file, so every asynchronous endpoint
        # (images, video) takes the identical path it always has.
        immediate = extract_output_urls(data)
        if immediate:
            logger.info(
                "%s answered inline with %d file(s); no polling needed.",
                endpoint,
                len(immediate),
            )
            return immediate[0]

        request_id = data.get("request_id") or data.get("id")
        if not request_id:
            raise MuAPIError(f"No request_id in MuAPI response: {data}")
        if not data.get("request_id"):
            # Worth knowing which key the ticket came from: `id` is a guess
            # that has already cost one silent feature, and a poll that 400s
            # right after a successful submit is what it looks like.
            logger.warning(
                "%s returned no request_id; polling on `id` %r instead. "
                "Response keys: %s",
                endpoint,
                request_id,
                sorted(data),
            )
        outputs = await self.poll_result(request_id, poll_interval, max_polls, is_cancelled=is_cancelled)
        return outputs[0]
