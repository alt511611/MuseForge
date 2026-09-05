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
  customer paid for keeps the length they paid for. Only the sync.so-family
  endpoints expose the knob -- see _ENDPOINT_FIELDS for which, and for what
  the ones that do not cost in exchange.

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

#: 3.0s x 240 = 12 minutes, matching the MuAPI and local backends.
#:
#: It was 120 polls, exactly 360s, which is the same ceiling the MuAPI module
#: measured and rejected: on a delivered three-scene job that provider's own
#: successful syncs came back at ~322s and ~367s, so a 360s cap decides by coin
#: toss whether a paid call produces a mouth. The number is the same here
#: because the reason is: syncs run concurrently (idea2video._lipsync_scenes),
#: so patience costs wall clock only on the slowest scene, and the cap should
#: mark "this request is lost", not "this request is slow".
DEFAULT_MAX_POLLS = 240

#: Which OPTIONAL fields each lip-sync endpoint accepts, read off fal's own
#: OpenAPI (``/api/openapi/queue/openapi.json?endpoint_id=<id>``).
#:
#: This is a map rather than one payload because fal VALIDATES the input: a
#: field the endpoint does not declare comes back 422, the module fails open,
#: and every scene in the drama silently keeps its closed mouth. Sending
#: ``model`` to LatentSync or ``sync_mode`` to VEED would do exactly that.
#:
#: BILLING SHAPE, which is the thing to check before switching (verified on
#: fal.ai, 2026-09-05) -- for the ~10s scenes this pipeline makes they do NOT
#: rank the way the per-minute headline reads:
#:
#:   fal-ai/latentsync            $0.20 FLAT up to 40s   -> $0.20 a scene
#:   fal-ai/sync-lipsync/v2       $3/min  ($0.05/s)      -> $0.50 a scene
#:   fal-ai/sync-lipsync/v2/pro   $5/min  ($0.083/s)     -> $0.83 a scene
#:   fal-ai/sync-lipsync/v3       $8/min  ($0.133/s)     -> $1.33 a scene
#:   fal-ai/sync-lipsync/react-1  $10/min ($0.167/s)     -> $1.67 a scene
#:   veed/lipsync/v2              $0.07/s               -> $0.70 a scene
#:
#: A scene's own generation is $0.72 flat on the default video endpoint, so
#: sync-3 and React-1 cost MORE than the footage they are correcting.
_ENDPOINT_FIELDS = {
    "fal-ai/sync-lipsync/v2": frozenset({"model", "sync_mode"}),
    "fal-ai/sync-lipsync/v2/pro": frozenset({"sync_mode"}),
    "fal-ai/sync-lipsync/v3": frozenset({"sync_mode"}),
    # LatentSync exposes no sync_mode at all; `loop_mode` only covers the
    # opposite case (audio LONGER than video). A short line still comes back
    # trimmed, which is why the length repair in idea2video._lipsync_scenes
    # (_restore_trimmed_length) is not optional on this endpoint.
    "fal-ai/latentsync": frozenset(),
    "veed/lipsync/v2": frozenset(),
    "fal-ai/kling-video/lipsync/audio-to-video": frozenset(),
}

#: What an endpoint we have no schema for gets: the two fields every lip-sync
#: model in the catalogue takes, and nothing else. Guessing wider is a 422.
_UNIVERSAL_FIELDS = frozenset()


def build_payload(video_url: str, audio_url: str, endpoint: str = "") -> dict:
    """The narrowest payload this endpoint is KNOWN to accept."""
    allowed = _ENDPOINT_FIELDS.get(endpoint or ENDPOINT, _UNIVERSAL_FIELDS)
    payload = {"video_url": video_url, "audio_url": audio_url}
    if "model" in allowed:
        payload["model"] = MODEL
    if "sync_mode" in allowed:
        payload["sync_mode"] = SYNC_MODE
    return payload


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

            # The voice track is not always a URL, and the same fix the MuAPI
            # backend carries is needed here for the same reason: the direct
            # ElevenLabs voice provider returns audio BYTES and writes them
            # into the job directory, so `audio_url` is a LOCAL PATH on that
            # deployment. The mixer opens it happily; fal cannot fetch it at
            # all. Sent as-is it fails, fails open, and lip sync silently
            # never happens -- on precisely the pairing (ElevenLabs voice +
            # fal lip sync) a deployment leaving MuAPI ends up with.
            if not str(audio_url).startswith(("http://", "https://")):
                if not os.path.isfile(audio_url):
                    return None
                audio_url = await self.client.upload_file(audio_url)

            handle = await self.client.submit(
                ENDPOINT,
                arguments=build_payload(video_url, audio_url, ENDPOINT),
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
