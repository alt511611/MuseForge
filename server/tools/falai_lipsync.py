"""Optional, fail-open lip synchronisation via fal.ai Sync Lipsync.

Dialogue already existed as a separate audio layer mixed over the finished
video, which means the characters' mouths were not saying the words the
audience hears. This drives the mouth from that same audio instead.

Two deliberate choices:

* ``sync_mode`` defaults to ``silence``, NOT the provider's own ``cut_off``
  default. ``cut_off`` trims the VIDEO down to the length of the audio, which
  would let a short line silently shorten a scene and break the fixed
  per-credit second budget (see interfaces/second_budget.py) that the whole
  costing model rests on. ``silence`` pads the audio instead, so the clip a
  customer paid for keeps the length they paid for.

* Every failure path returns ``None`` rather than raising. Lip sync is a
  polish stage running after the expensive generation is already paid for;
  losing it must cost mouth accuracy, never the job.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Optional

import fal_client

logger = logging.getLogger(__name__)

TRUTHY = {"1", "true", "yes", "on"}

ENDPOINT = os.environ.get("FALAI_LIPSYNC_MODEL", "fal-ai/sync-lipsync/v2")
# "lipsync-2" / "lipsync-2-pro" — the pro variant costs ~1.67x per minute.
MODEL = os.environ.get("FALAI_LIPSYNC_QUALITY", "lipsync-2")
SYNC_MODE = os.environ.get("FALAI_LIPSYNC_SYNC_MODE", "silence")

DEFAULT_POLL_INTERVAL = 3.0
DEFAULT_MAX_POLLS = 120


# Re-exported, not redefined: the flag is provider-neutral and now lives with
# the default (MuAPI) backend. Two copies of it would eventually disagree about
# which spellings count as true.
from tools.muapi_lipsync import is_lipsync_enabled  # noqa: E402,F401


class FalAILipsync:
    def __init__(self, api_key: str = "", demo: bool = False):
        self.demo = demo
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        # Unlike the video/image providers this does NOT raise on a missing
        # key: lip sync is optional polish, so an unconfigured deployment
        # should quietly render without it rather than fail every job that
        # happens to contain dialogue.
        self.client = fal_client.AsyncClient(key=self.api_key or None)

    def available(self) -> bool:
        return bool(self.api_key) and not self.demo

    async def sync(
        self,
        video_path_or_url: str,
        audio_url: str,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Optional[str]:
        """Return a URL to the lip-synced clip, or None if it could not be done.

        ``video_path_or_url`` may be a local file (the assembled scene clip on
        disk) — it is uploaded to fal's storage first, because the API fetches
        the video by URL.
        """
        if not self.available() or not audio_url or not video_path_or_url:
            return None

        try:
            video_url = video_path_or_url
            if not str(video_path_or_url).startswith(("http://", "https://")):
                if not os.path.isfile(video_path_or_url):
                    return None
                video_url = await self.client.upload_file(video_path_or_url)

            handle = await self.client.submit(
                ENDPOINT,
                arguments={
                    "model": MODEL,
                    "video_url": video_url,
                    "audio_url": audio_url,
                    "sync_mode": SYNC_MODE,
                },
            )
            request_id = handle.request_id

            for _ in range(DEFAULT_MAX_POLLS):
                if is_cancelled and is_cancelled():
                    await self._cancel(request_id)
                    return None
                status = await self.client.status(ENDPOINT, request_id, with_logs=False)
                if isinstance(status, fal_client.Completed):
                    if status.error:
                        logger.warning(
                            "Lip sync request %s failed: %s", request_id, status.error
                        )
                        return None
                    break
                await asyncio.sleep(DEFAULT_POLL_INTERVAL)
            else:
                logger.warning("Lip sync request %s timed out", request_id)
                await self._cancel(request_id)
                return None

            result = await self.client.result(ENDPOINT, request_id)
            synced_url = ((result or {}).get("video") or {}).get("url")
            if not synced_url:
                logger.warning("Lip sync completed with no video URL: %s", result)
                return None
            return synced_url
        except Exception as exc:
            logger.warning("Lip sync unavailable for this scene, using the unsynced clip: %s", exc)
            return None

    async def _cancel(self, request_id: str) -> None:
        try:
            await self.client.cancel(ENDPOINT, request_id)
        except Exception as exc:
            logger.warning("Lip sync cancel failed (already finishing?): %s", exc)
