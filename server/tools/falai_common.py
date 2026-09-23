"""Shared fal.ai submit/poll/result helpers.

Used by the optional fal.ai providers (image / music / reference-video).
The existing FalAIVideoGenerator keeps its own copy so its behaviour is
never accidentally changed by refactors here.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Callable, Optional

import fal_client

from tools.muapi_client import MuAPICancelled

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 3.0
#: 400 * 3.0s = 1200s (20 minutes) -- see the same constant and its reasoning
#: in falai_video_generator.py (that module keeps its own copy so a refactor
#: here can never silently change its behaviour). Image/SFX/music calls
#: finish in seconds regardless, so raising this only widens the ceiling for
#: the one caller here that renders video (falai_reference_video_generator.py)
#: and never makes a fast call wait longer than it already does.
DEFAULT_MAX_POLLS = int(os.environ.get("FALAI_MAX_POLLS", "400"))


def make_fal_client(api_key: str, demo: bool = False) -> fal_client.AsyncClient:
    # .strip() guards against trailing whitespace/newlines from a dashboard paste
    # that would otherwise cause "Illegal header value".
    key = (api_key or "").strip()
    if not key and not demo:
        # Found during a deep audit: previously this silently built a client
        # with key=None, which falls through to fal_client's own internal
        # env-var lookup -- if FAL_KEY genuinely isn't set anywhere, this
        # produced unpredictable behavior (a slow/unclear failure deep
        # inside the first network call) instead of an immediate, obvious
        # error at construction time, which is much harder to diagnose from
        # logs alone -- exactly the kind of "silent, invisible failure"
        # class of bug this whole project has repeatedly been bitten by.
        # Demo mode is exempt: it never makes a real network call, so it
        # never needs a real key.
        raise RuntimeError(
            "FAL_KEY is not set (or is empty) -- cannot use a fal.ai "
            "provider (MUSEFORGE_IMAGE_PROVIDER/MUSEFORGE_MUSIC_PROVIDER/"
            "MUSEFORGE_VIDEO_PROVIDER=falai) without it. Set FAL_KEY in "
            "Coolify's environment, or switch the provider(s) back to "
            "\"muapi\"."
        )
    return fal_client.AsyncClient(key=key or None)


#: A false-positive content-policy flag was observed to clear on a plain
#: resubmit of the SAME arguments (fal's checker is not fully deterministic
#: run to run), so one automatic retry is worth it before making the caller
#: burn a whole job attempt on what "try regenerating" would have fixed
#: anyway. Kept at 1: a flag that survives a retry is very likely a REAL
#: match, and this helper's caller (a single frame/cue inside a job already
#: in flight) should not sit doubling its wait on every poll cycle for that.
CONTENT_POLICY_RETRIES = 1


async def fal_generate(
    client: fal_client.AsyncClient,
    endpoint: str,
    arguments: dict,
    *,
    is_cancelled: Optional[Callable[[], bool]] = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    max_polls: int = DEFAULT_MAX_POLLS,
) -> Any:
    """Submit -> poll status (~3s) -> return result dict. Raises on failure.

    No silent MuAPI fallback -- fal.ai is an explicit user choice, so errors
    surface clearly rather than silently masking a wrong provider config.
    """
    attempts = CONTENT_POLICY_RETRIES + 1
    for attempt in range(attempts):
        try:
            return await _submit_and_wait(
                client,
                endpoint,
                arguments,
                is_cancelled=is_cancelled,
                poll_interval=poll_interval,
                max_polls=max_polls,
            )
        except RuntimeError as exc:
            if "content_policy_violation" not in str(exc) or attempt == attempts - 1:
                raise
            logger.warning(
                "fal.ai flagged %s as a content policy violation on attempt "
                "%d/%d; resubmitting the same arguments once before giving "
                "up.",
                endpoint,
                attempt + 1,
                attempts,
            )


async def _submit_and_wait(
    client: fal_client.AsyncClient,
    endpoint: str,
    arguments: dict,
    *,
    is_cancelled: Optional[Callable[[], bool]] = None,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    max_polls: int = DEFAULT_MAX_POLLS,
) -> Any:
    """One submit/poll/result cycle -- the retryable unit `fal_generate` wraps."""
    handle = await client.submit(endpoint, arguments=arguments)
    request_id = handle.request_id

    for _ in range(max_polls):
        if is_cancelled and is_cancelled():
            raise await _cancel(client, endpoint, request_id)

        status = await client.status(endpoint, request_id, with_logs=False)
        if isinstance(status, fal_client.Completed):
            if status.error:
                raise _translate(RuntimeError(
                    f"fal.ai job {request_id} failed: {status.error}"
                ))
            break

        if is_cancelled and is_cancelled():
            raise await _cancel(client, endpoint, request_id)
        await asyncio.sleep(poll_interval)
    else:
        raise TimeoutError(
            f"fal.ai job {request_id} timed out after {max_polls * poll_interval}s"
        )

    try:
        return await client.result(endpoint, request_id)
    except Exception as exc:
        raise _translate(exc) from exc


def _translate(exc: Exception) -> Exception:
    """Fal's raw content-policy error into one worth showing a person.

    The same translation falai_video_generator.py's own ``_run`` carries,
    duplicated here rather than shared with it (see that module's docstring:
    it keeps its own copy on purpose). Every OTHER fal caller goes through
    this one helper, though, and none of them had it -- a live job's frame
    generation surfaced fal's raw pydantic-shaped error (a list of {'loc',
    'msg', 'type': ...} dicts) straight up through jobs.py as "Internal
    error: [...]", unreadable and with no hint that a retry usually clears
    it. Returned, not raised, so both call sites above can attach their own
    ``from exc``.
    """
    if "content_policy_violation" in str(exc):
        return RuntimeError(
            "fal.ai flagged this content automatically (often a false "
            "positive). Try regenerating -- a new reference image or "
            "prompt wording may not trigger the same flag."
        )
    return exc


async def _cancel(
    client: fal_client.AsyncClient, endpoint: str, request_id: str
) -> MuAPICancelled:
    try:
        await client.cancel(endpoint, request_id)
    except Exception as exc:
        logger.warning("fal.ai cancel request failed (already finishing?): %s", exc)
    return MuAPICancelled(f"Job cancelled while polling fal.ai request {request_id}")
