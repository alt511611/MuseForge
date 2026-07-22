"""Alternative image-to-video provider: fal.ai's Kling O3 Pro model.

Selected via MUSEFORGE_VIDEO_PROVIDER=falai (default remains "muapi", the
existing MuAPIVideoGenerator path -- see _make_video_generator() in
pipelines/script2video.py). This module is only imported when that env
var is actually set to "falai", so the default path never needs fal-client
installed/importable.

Schema CONFIRMED against fal.ai's own docs
(https://fal.ai/models/fal-ai/kling-video/o3/pro/image-to-video/api):
    input:  prompt (str, optional), image_url (str, required),
            duration (str enum "3".."15", default "5" -- NOT the 5/10-only
            enum MuAPI's Kling O1 endpoint uses)
    output: {"video": {"url": "...", "file_name": ..., "file_size": ...,
             "content_type": ...}}

Polling follows the same submit -> poll status -> fetch result pattern (and
is_cancelled check between poll iterations) as tools/muapi_client.py, using
fal_client's AsyncClient directly (rather than its module-level
convenience functions) so the API key is scoped to this instance instead
of mutating process-wide environment state.
"""

import asyncio
import logging
import os
from typing import Callable, Optional

import fal_client

from tools.muapi_client import MuAPICancelled

logger = logging.getLogger(__name__)

DEMO_VIDEO_URL = os.environ.get(
    "MUSEFORGE_DEMO_VIDEO",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
)

MIN_DURATION_SECONDS = 3
MAX_DURATION_SECONDS = 15
DEFAULT_POLL_INTERVAL = 3.0
DEFAULT_MAX_POLLS = 200


def _duration_str(seconds) -> str:
    """Clamp to fal's supported 3-15s integer-string enum (unlike MuAPI's
    Kling O1 endpoint, this is NOT restricted to just 5 or 10)."""
    try:
        value = int(round(float(seconds)))
    except (TypeError, ValueError):
        value = 5
    value = max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, value))
    return str(value)


class FalAIVideoGenerator:
    # Endpoint ID confirmed against fal.ai's own model page/API docs.
    ENDPOINT = os.environ.get(
        "FALAI_VIDEO_MODEL", "fal-ai/kling-video/o3/pro/image-to-video"
    )

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.api_key = api_key or os.environ.get("FAL_KEY", "")
        self.client = fal_client.AsyncClient(key=self.api_key or None)

    async def generate_video_from_image(
        self,
        prompt: str,
        image_url: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        plan: str = "free",
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        # aspect_ratio/plan kept in the signature for interchangeability
        # with MuAPIVideoGenerator; this model derives aspect ratio from
        # the source image and has no HD/standard mode split (yet).
        _ = aspect_ratio, plan
        if self.demo:
            return DEMO_VIDEO_URL

        payload = {
            "prompt": prompt,
            "image_url": image_url,
            "duration": _duration_str(duration),
        }

        handle = await self.client.submit(self.ENDPOINT, arguments=payload)
        request_id = handle.request_id

        for _ in range(DEFAULT_MAX_POLLS):
            if is_cancelled and is_cancelled():
                raise await self._cancel(request_id)

            status = await self.client.status(self.ENDPOINT, request_id, with_logs=False)
            if isinstance(status, fal_client.Completed):
                if status.error:
                    raise RuntimeError(
                        f"fal.ai job {request_id} failed: {status.error}"
                    )
                break

            if is_cancelled and is_cancelled():
                raise await self._cancel(request_id)
            await asyncio.sleep(DEFAULT_POLL_INTERVAL)
        else:
            raise TimeoutError(
                f"fal.ai job {request_id} timed out after "
                f"{DEFAULT_MAX_POLLS * DEFAULT_POLL_INTERVAL}s"
            )

        result = await self.client.result(self.ENDPOINT, request_id)
        video_url = ((result or {}).get("video") or {}).get("url")
        if not video_url:
            raise RuntimeError(f"fal.ai completed but no video URL in result: {result}")
        return video_url

    async def _cancel(self, request_id: str) -> MuAPICancelled:
        """Best-effort remote cancel, then return (not raise) the exception
        the caller should raise -- lets the caller keep a single `raise`
        call site regardless of which cancellation check triggered it.
        Reuses MuAPICancelled (rather than a new exception type) so
        script2video.py's existing cancellation handling -- which already
        catches MuAPICancelled and translates it into PipelineCancelled --
        works unchanged for this provider too.
        """
        try:
            await self.client.cancel(self.ENDPOINT, request_id)
        except Exception as exc:
            logger.warning("fal.ai cancel request failed (already finishing?): %s", exc)
        return MuAPICancelled(f"Job cancelled while polling fal.ai request {request_id}")
