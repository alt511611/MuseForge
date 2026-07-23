"""Shared fal.ai submit/poll/result helpers.

Used by the optional fal.ai providers (image / music / reference-video).
The existing FalAIVideoGenerator keeps its own copy so its behaviour is
never accidentally changed by refactors here.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

import fal_client

from tools.muapi_client import MuAPICancelled

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL = 3.0
DEFAULT_MAX_POLLS = 200


def make_fal_client(api_key: str, demo: bool = False) -> fal_client.AsyncClient:
    # .strip() guards against trailing whitespace/newlines from Render env paste
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
            "Render's environment, or switch the provider(s) back to "
            "\"muapi\"."
        )
    return fal_client.AsyncClient(key=key or None)


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
    handle = await client.submit(endpoint, arguments=arguments)
    request_id = handle.request_id

    for _ in range(max_polls):
        if is_cancelled and is_cancelled():
            raise await _cancel(client, endpoint, request_id)

        status = await client.status(endpoint, request_id, with_logs=False)
        if isinstance(status, fal_client.Completed):
            if status.error:
                raise RuntimeError(f"fal.ai job {request_id} failed: {status.error}")
            break

        if is_cancelled and is_cancelled():
            raise await _cancel(client, endpoint, request_id)
        await asyncio.sleep(poll_interval)
    else:
        raise TimeoutError(
            f"fal.ai job {request_id} timed out after {max_polls * poll_interval}s"
        )

    return await client.result(endpoint, request_id)


async def _cancel(
    client: fal_client.AsyncClient, endpoint: str, request_id: str
) -> MuAPICancelled:
    try:
        await client.cancel(endpoint, request_id)
    except Exception as exc:
        logger.warning("fal.ai cancel request failed (already finishing?): %s", exc)
    return MuAPICancelled(f"Job cancelled while polling fal.ai request {request_id}")
