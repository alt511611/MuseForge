"""The three things every Claude call in this pipeline has to get right.

Not a client wrapper. Three agents call the Messages API -- the screenwriter,
the storyboard artist and the frame QA -- and each of them had its own answer
to the same three questions, which is how two of them ended up with no answer
at all.

**A refusal is a 200.** The API can decline a request and still return HTTP
200, with `stop_reason: "refusal"` and a category in `stop_details`. Nothing
raises. The screenwriter checks for it; the storyboard artist did not, and its
`except Exception -> return []` turns a declined scene into the template shot
list -- the exact silent fallback its own comments record fighting twice, with
a third cause nobody had looked for. The frame QA is worse: it fails OPEN, so
a declined check passes the frame.

**A 429 is not a 404.** Both agents caught `APIStatusError` and treated every
status inside it identically. One of those is worth retrying and the other is
a key that cannot reach the model, and a pipeline that cannot tell them apart
logs the same line for a busy minute and a broken deployment.

**A cached prefix has to be verified, not declared.** `cache_control` is a
request for caching, and a prefix that is one byte different, or shorter than
the model's minimum, silently does not cache. The only proof is
`usage.cache_read_input_tokens` coming back non-zero.

Which calls should cache at all is a judgement made per caller, and only one
of the three earns it -- see `cached_system`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiFailure:
    """What kind of failure this was, and whether trying again could help."""

    kind: str
    retryable: bool
    detail: str


def classify(exc: Exception) -> ApiFailure:
    """One exception, sorted most-specific first.

    The order is the point. `RateLimitError` and `NotFoundError` are both
    `APIStatusError`, so a handler that catches the parent first can never
    see either -- which is what both agents were doing.
    """
    import anthropic

    body = ""
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            body = f" body={response.text[:500]}"
        except Exception:
            pass
    label = f"{type(exc).__name__}: {exc}{body}"

    if isinstance(exc, anthropic.AuthenticationError):
        return ApiFailure("auth", False, f"the API key was rejected | {label}")
    if isinstance(exc, anthropic.PermissionDeniedError):
        return ApiFailure(
            "auth", False, f"this key may not reach this model | {label}"
        )
    if isinstance(exc, anthropic.NotFoundError):
        return ApiFailure("not_found", False, f"no such model or route | {label}")
    if isinstance(exc, anthropic.RateLimitError):
        return ApiFailure("rate_limit", True, f"rate limited | {label}")
    if isinstance(exc, anthropic.BadRequestError):
        # Ours to fix: a malformed request does not become well-formed by
        # being sent again.
        return ApiFailure("request", False, f"the request was rejected | {label}")
    if isinstance(exc, anthropic.InternalServerError):
        return ApiFailure("server", True, f"the API failed | {label}")
    if isinstance(exc, anthropic.APIStatusError):
        status = getattr(exc, "status_code", 0) or 0
        return ApiFailure("status", status >= 500, f"HTTP {status} | {label}")
    if isinstance(exc, anthropic.APIConnectionError):
        # Covers APITimeoutError, which subclasses it.
        return ApiFailure("network", True, f"never reached the API | {label}")
    return ApiFailure("unknown", False, label)


def refusal_of(message: Any) -> Optional[str]:
    """The refusal category when the model declined, else None.

    `stop_details` is populated ONLY for a refusal and is `None` for every
    other stop reason, so it is read through a guard rather than trusted --
    and the category is an open set, which is why this returns the string it
    was given instead of matching against a list.
    """
    if getattr(message, "stop_reason", None) != "refusal":
        return None
    details = getattr(message, "stop_details", None)
    return str(getattr(details, "category", None) or "unspecified")


def cached_system(text: str) -> List[dict]:
    """One system prompt as a cacheable block.

    For the caller whose prompt is BYTE-IDENTICAL across several calls close
    together. That is the storyboard artist and nothing else here:

    * It is called once per SCENE, four to six times a minute apart, with a
      prompt that `system_prompt_for` settles once from an environment
      variable and then never varies within a job.
    * The screenwriter is called once per job. A cache write costs more than
      an ordinary read, so caching a prompt sent once buys a discount on a
      second call that may never come and charges a premium for the
      certainty -- it is a loss on an idle instance and this does not offer
      it one.
    * The frame QA's prompt is about 200 tokens and its two variable hints
      sit in the MIDDLE of it. It is under every model's minimum cacheable
      prefix, so a breakpoint there would be accepted and then silently do
      nothing, which is worse than not asking.

    Verify with `log_cache_use` rather than assuming: this function returns a
    REQUEST to cache, not a cache.
    """
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def log_cache_use(label: str, usage: Any) -> None:
    """Say what the cache actually did, at the call that asked for it."""
    written = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
    if read:
        logger.info("%s: %d tokens read from cache", label, read)
    elif written:
        logger.info("%s: %d tokens written to cache (first call)", label, written)
    else:
        # Neither written nor read means the breakpoint did nothing: a prefix
        # under the model's minimum, or one that changes between calls.
        logger.warning(
            "%s: asked to cache and neither wrote nor read -- the prefix is "
            "too short or is not identical between calls", label
        )
