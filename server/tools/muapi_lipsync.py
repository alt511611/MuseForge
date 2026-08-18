"""Optional, fail-open lip synchronisation via MuAPI's Sync Labs endpoint.

Dialogue already existed as a separate audio layer mixed over the finished
video, which means the characters' mouths were not saying the words the
audience hears. This drives the mouth from that same audio instead.

This is the default provider because it is the ONLY remaining reason the
pipeline needed a second vendor: video, images, voice and music all run on
MuAPI, and a deployment that wanted lip sync had to hold a fal.ai key purely
for this one call. tools/falai_lipsync.py is still selectable via
MUSEFORGE_LIPSYNC_PROVIDER=falai.

Two things this endpoint does NOT give us, both handled by the caller:

* No ``sync_mode``. The fal implementation pins it to ``silence`` because the
  provider's own default (``cut_off``) trims the VIDEO down to the length of
  the audio, which would let a short line silently shorten a scene and break
  the fixed per-credit second budget the costing model rests on. MuAPI does
  not expose the knob, so the pipeline verifies the returned clip's duration
  instead and keeps the unsynced take if it came back short (see
  idea2video._lipsync_scenes).

* No cancellation. MuAPIClient checks is_cancelled between polls and raises,
  which is enough to stop waiting; there is no request-cancel call to make.

Every failure path returns ``None`` rather than raising. Lip sync is a polish
stage running after the expensive generation is already paid for; losing it
must cost mouth accuracy, never the job.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from tools.muapi_client import MuAPIClient, MuAPIError

logger = logging.getLogger(__name__)

TRUTHY = {"1", "true", "yes", "on"}

ENDPOINT = os.environ.get("MUAPI_LIPSYNC_MODEL", "sync-lipsync")

DEFAULT_POLL_INTERVAL = 3.0
DEFAULT_MAX_POLLS = 120


def is_lipsync_enabled() -> bool:
    """Opt-in: every synced scene is a paid API call on top of generation."""
    return os.environ.get("MUSEFORGE_LIPSYNC_ENABLED", "").strip().lower() in TRUTHY


def make_lipsync(demo: bool = False):
    """The configured lip-sync backend.

    MUSEFORGE_LIPSYNC_PROVIDER:
      - "muapi" (default) — this module, no second vendor key needed
      - "falai" — fal.ai Sync Lipsync, which exposes sync_mode directly
    """
    provider = (os.environ.get("MUSEFORGE_LIPSYNC_PROVIDER", "muapi") or "").strip().lower()
    if provider == "falai":
        # Lazy: the default path must never require fal-client to be installed.
        from tools.falai_lipsync import FalAILipsync

        return FalAILipsync(os.environ.get("FAL_KEY", ""), demo=demo)
    return MuAPILipsync(os.environ.get("MUAPI_KEY", ""), demo=demo)


class MuAPILipsync:
    def __init__(self, api_key: str = "", demo: bool = False):
        self.demo = demo
        self.api_key = (api_key or os.environ.get("MUAPI_KEY", "")).strip()
        self.client = MuAPIClient(self.api_key)

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
        disk) — it is uploaded to MuAPI storage first, because the API fetches
        the video by URL.
        """
        if not self.available() or not audio_url or not video_path_or_url:
            return None

        try:
            video_url = video_path_or_url
            if not str(video_path_or_url).startswith(("http://", "https://")):
                from tools.muapi_uploader import upload_local_file

                if not os.path.isfile(video_path_or_url):
                    return None
                video_url = await upload_local_file(video_path_or_url, self.api_key)
                if not video_url:
                    logger.warning(
                        "Scene clip could not be uploaded for lip sync, "
                        "keeping the unsynced take"
                    )
                    return None

            # The voice track is not always a URL. The ElevenLabs backend
            # returns audio BYTES and writes them into the job directory, so
            # `audio_url` carries a LOCAL PATH on that provider -- which the
            # mixer opens happily and this endpoint cannot fetch at all. Sent
            # as-is it fails every time, fails open, and lip sync silently
            # never happens on any deployment using that voice provider.
            if not str(audio_url).startswith(("http://", "https://")):
                from tools.muapi_uploader import upload_local_file

                if not os.path.isfile(audio_url):
                    return None
                uploaded_audio = await upload_local_file(audio_url, self.api_key)
                if not uploaded_audio:
                    logger.warning(
                        "Dialogue audio could not be uploaded for lip sync, "
                        "keeping the unsynced take"
                    )
                    return None
                audio_url = uploaded_audio

            return await self.client.generate(
                ENDPOINT,
                {"video_url": video_url, "audio_url": audio_url},
                poll_interval=DEFAULT_POLL_INTERVAL,
                max_polls=DEFAULT_MAX_POLLS,
                is_cancelled=is_cancelled,
            )
        except MuAPIError as exc:
            logger.warning(
                "Lip sync unavailable for this scene, using the unsynced clip: %s", exc
            )
            return None
        except Exception as exc:
            logger.warning(
                "Lip sync unavailable for this scene, using the unsynced clip: %s", exc
            )
            return None
