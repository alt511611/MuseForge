"""One place that decides where Claude is called from: Anthropic, or fal.

``MUSEFORGE_LLM_PROVIDER=falai`` sends every Claude call in the pipeline --
screenwriter, storyboard artist, frame QA, frame judge -- through fal's
``openrouter/router/openai/v1/chat/completions`` endpoint, so the whole
pipeline bills against the one fal balance it already spends on video, image,
voice and music instead of a second account that, when it runs dry, silently
turns QA off (job bb6c6f1f: Anthropic credit exhausted, every frame went
through unchecked).

Measured before this was written, on the real endpoint with model
``anthropic/claude-sonnet-5``:

* a JSON answer: $0.0025, finished in seconds;
* a vision call with ``image_urls``: valid JSON, $0.0031 for 1476 prompt tokens;
* a four-scene screenplay with reasoning and ``response_format: json_object``:
  5,934 output tokens, ``finish_reason: stop``, valid JSON, $0.0597.

The callers were written against the Anthropic SDK's surface -- ``messages
.create``, ``messages.stream(...).get_final_message()``, ``stop_reason``,
``content`` blocks filtered by type, the SDK's exception classes -- and each
of those carries hard-won handling (a refusal is a 200, a 429 is not a 404,
a thinking block is not the answer). So this module does not give them a
second code path. It gives them a second *client* with the same surface, and
raises the SDK's own exception classes, so ``classify`` and every
``except anthropic.APIStatusError`` keep meaning what they meant.

Not carried over, on purpose: ``cache_control`` (the fal route reports no
cache fields; the usage line prints zeros and the "asked to cache and did not"
warning is skipped for this provider).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

ENDPOINT = "openrouter/router/openai/v1/chat/completions"

#: fal's routes name the vendor; the pipeline names models the Anthropic way.
_MODEL_ALIASES = {
    "claude-sonnet-5": "anthropic/claude-sonnet-5",
}

_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.S | re.I)


def provider() -> str:
    """"falai" or "anthropic". Anything else is the default, not an error."""
    value = (os.environ.get("MUSEFORGE_LLM_PROVIDER") or "").strip().lower()
    return "falai" if value in ("falai", "fal") else "anthropic"


def api_key() -> str:
    """The key the chosen provider needs -- ANTHROPIC_API_KEY or FAL_KEY.

    Every caller guards its call with "is there a key" and quietly skips the
    check or falls to the template when there is not. Under fal that guard has
    to look at FAL_KEY, or a deployment that moved to fal would read as having
    no LLM at all.
    """
    if provider() == "falai":
        return (os.environ.get("FAL_KEY") or "").strip()
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def fal_model(model: str) -> str:
    override = (os.environ.get("FALAI_LLM_MODEL") or "").strip()
    if override:
        return override
    return _MODEL_ALIASES.get(model, model if "/" in model else f"anthropic/{model}")


def make_client(key: str, max_retries: int = 2):
    """The client for the chosen provider, with the SDK's ``messages`` surface."""
    if provider() == "falai":
        return FalMessagesClient(key or api_key(), max_retries=max_retries)
    import anthropic

    return anthropic.AsyncAnthropic(api_key=key, max_retries=max_retries)


# --- the response, shaped like the SDK's ------------------------------------


@dataclass
class _Block:
    type: str
    text: str = ""


@dataclass
class _Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    cost: float = 0.0


@dataclass
class _Message:
    content: List[_Block] = field(default_factory=list)
    stop_reason: str = "end_turn"
    stop_details: Any = None
    usage: _Usage = field(default_factory=_Usage)


@dataclass
class _Details:
    category: str


_STOP = {
    "stop": "end_turn",
    "end_turn": "end_turn",
    "length": "max_tokens",
    "max_tokens": "max_tokens",
    "tool_calls": "tool_use",
    "content_filter": "refusal",
}


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(
        str(b.get("text", ""))
        for b in content or []
        if isinstance(b, dict) and b.get("type") == "text"
    )


def build_payload(
    *,
    model: str,
    max_tokens: int,
    messages: list,
    system: Any = None,
    thinking: Optional[dict] = None,
    output_config: Optional[dict] = None,
    **_ignored: Any,
) -> dict:
    """An Anthropic-shaped request, as fal's OpenAI-compatible body.

    * ``system`` may be a string or the cacheable-block list; either becomes
      one system message.
    * Image blocks become ``image_urls`` -- the field that was proven on the
      real endpoint -- and the text blocks of that turn stay text.
    * ``output_config.format`` (a JSON schema) becomes ``json_object`` plus the
      schema spelled out in the prompt: the route guarantees valid JSON, and
      the prompt says which JSON, which is what the schema was for.
    * ``thinking`` disabled means no reasoning budget; anything else asks for
      one, because the screenwriter's adaptive thinking is what its story
      structure was tuned with. Thinking tokens come out of ``max_tokens``
      exactly as they do on Anthropic.
    """
    out: List[dict] = []
    system_text = _text_of(system) if system else ""
    if system_text:
        out.append({"role": "system", "content": system_text})

    image_urls: List[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image":
                    url = (block.get("source") or {}).get("url")
                    if url:
                        image_urls.append(url)
        out.append({"role": message["role"], "content": _text_of(content)})

    payload: dict = {
        "model": fal_model(model),
        "messages": out,
        "max_tokens": max_tokens,
    }
    if image_urls:
        payload["image_urls"] = image_urls

    fmt = ((output_config or {}).get("format") or {})
    if fmt.get("type") == "json_schema":
        payload["response_format"] = {"type": "json_object"}
        schema = json.dumps(fmt.get("schema", {}), separators=(",", ":"))
        out[-1]["content"] += (
            "\n\nReply with ONLY one JSON object matching this JSON schema, "
            f"no prose and no code fence: {schema}"
        )

    if (thinking or {}).get("type") != "disabled":
        budget = int(os.environ.get("FALAI_LLM_REASONING_TOKENS", "4000") or 0)
        # Never ask for more thinking than the answer can leave room for.
        budget = min(budget, max(0, max_tokens // 2))
        if budget >= 1024:
            payload["reasoning"] = {"max_tokens": budget}
    return payload


def parse_response(result: dict) -> _Message:
    """fal's chat.completion into the SDK's message."""
    choice = ((result or {}).get("choices") or [{}])[0]
    text = str((choice.get("message") or {}).get("content") or "")
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    finish = choice.get("finish_reason") or "stop"
    refused = bool((choice.get("message") or {}).get("refusal"))
    stop = "refusal" if refused else _STOP.get(finish, "end_turn")
    usage = (result or {}).get("usage") or {}
    return _Message(
        content=[_Block("text", text)],
        stop_reason=stop,
        stop_details=_Details("unspecified") if stop == "refusal" else None,
        usage=_Usage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cost=float(usage.get("cost") or 0.0),
        ),
    )


# --- failures, as the SDK's classes ----------------------------------------


def _sdk_error(status: int, detail: str) -> Exception:
    """The SDK's own exception for an HTTP status, so classify() keeps working."""
    import anthropic
    import httpx

    request = httpx.Request("POST", f"https://fal.run/{ENDPOINT}")
    response = httpx.Response(status, request=request, text=detail[:500])
    probe = anthropic.AsyncAnthropic(api_key="unused")
    return probe._make_status_error_from_response(response)


def _status_of(exc: Exception) -> int:
    response = getattr(exc, "response", None)
    code = getattr(response, "status_code", None)
    if isinstance(code, int):
        return code
    text = str(exc).lower()
    if "401" in text or "unauthorized" in text or "invalid api key" in text:
        return 401
    if "403" in text or "forbidden" in text or "balance" in text or "locked" in text:
        return 403
    if "429" in text or "rate limit" in text:
        return 429
    if "timed out" in text or "timeout" in text:
        return 0
    return 500


def translate(exc: Exception) -> Exception:
    import anthropic
    import httpx

    if isinstance(exc, (anthropic.APIStatusError, anthropic.APIConnectionError)):
        return exc
    status = _status_of(exc)
    if status == 0:
        return anthropic.APITimeoutError(
            request=httpx.Request("POST", f"https://fal.run/{ENDPOINT}")
        )
    return _sdk_error(status, f"{type(exc).__name__}: {exc}")


def _retryable(exc: Exception) -> bool:
    import anthropic

    return isinstance(
        exc,
        (anthropic.RateLimitError, anthropic.InternalServerError,
         anthropic.APIConnectionError),
    )


# --- the client ------------------------------------------------------------


class _Stream:
    """``async with client.messages.stream(...) as s: await s.get_final_message()``.

    Not incremental: the queue returns the whole completion. The callers only
    ever ask for the final message, and bound it with their own deadline.
    """

    def __init__(self, messages: "_Messages", kwargs: dict):
        self._messages = messages
        self._kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self) -> _Message:
        return await self._messages.create(**self._kwargs)


class _Messages:
    def __init__(self, client: Any, max_retries: int):
        self._client = client
        self._max_retries = max_retries

    def stream(self, **kwargs: Any) -> _Stream:
        return _Stream(self, kwargs)

    async def create(self, **kwargs: Any) -> _Message:
        from tools.falai_common import fal_generate

        payload = build_payload(**kwargs)
        attempt = 0
        while True:
            try:
                result = await fal_generate(self._client, ENDPOINT, payload)
                error = (result or {}).get("error")
                if error:
                    raise RuntimeError(f"fal LLM route returned an error: {error}")
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                failure = translate(exc)
                if attempt >= self._max_retries or not _retryable(failure):
                    raise failure from exc
                attempt += 1
                delay = 2.0 * attempt
                logger.warning(
                    "fal LLM call failed (%s); retry %d/%d in %.0fs",
                    type(failure).__name__, attempt, self._max_retries, delay,
                )
                await asyncio.sleep(delay)
        message = parse_response(result)
        logger.info(
            "fal llm: model=%s cost=$%.4f", payload["model"], message.usage.cost
        )
        return message


class FalMessagesClient:
    """The slice of ``anthropic.AsyncAnthropic`` the pipeline uses."""

    def __init__(self, key: str, max_retries: int = 2):
        from tools.falai_common import make_fal_client

        self._fal = make_fal_client(key)
        self.messages = _Messages(self._fal, max_retries)
