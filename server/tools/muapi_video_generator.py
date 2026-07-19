"""MuAPI image-to-video generation."""

import logging
import os
from typing import Any, Dict

from tools.muapi_client import MuAPIClient, MuAPIError

logger = logging.getLogger(__name__)

DEMO_VIDEO_URL = os.environ.get(
    "MUSEFORGE_DEMO_VIDEO",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
)

# Kling O1: "standard" ≈ 720p, "professional" ≈ 1080p (third-party docs).
# Override via env if MuAPI's actual string differs (e.g. "pro").
DEFAULT_PRO_MODE = "professional"


def _pro_mode_value() -> str:
    return os.environ.get("MUAPI_VIDEO_PRO_MODE", DEFAULT_PRO_MODE).strip() or DEFAULT_PRO_MODE


def mode_for_plan(plan: str) -> str:
    """Return MuAPI `mode` for the caller's plan. Pro → HD; everyone else → standard."""
    if (plan or "").lower() == "pro":
        return _pro_mode_value()
    return "standard"


def _is_mode_rejected(exc: Exception) -> bool:
    """True when MuAPI likely rejected the mode value (404/422)."""
    msg = str(exc).lower()
    if "404" in msg or "422" in msg:
        return True
    # httpx.HTTPStatusError repr sometimes embeds status_code=
    if "status_code=404" in msg or "status_code=422" in msg:
        return True
    return False


class MuAPIVideoGenerator:
    VIDEO_ENDPOINT = os.environ.get(
        "MUAPI_VIDEO_MODEL", "kling-o1-standard-image-to-video"
    )

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)

    def _payload(
        self,
        prompt: str,
        image_url: str,
        duration: int,
        aspect_ratio: str,
        mode: str,
    ) -> Dict[str, Any]:
        return {
            "prompt": prompt,
            "image_url": image_url,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "mode": mode,
        }

    async def generate_video_from_image(
        self,
        prompt: str,
        image_url: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        plan: str = "free",
    ) -> str:
        if self.demo:
            return DEMO_VIDEO_URL

        mode = mode_for_plan(plan)
        payload = self._payload(prompt, image_url, duration, aspect_ratio, mode)

        try:
            return await self.client.generate(
                self.VIDEO_ENDPOINT,
                payload,
                poll_interval=3.0,
                max_polls=200,
            )
        except MuAPIError as exc:
            # Wrong mode string (e.g. MuAPI expects "pro" not "professional") —
            # fall back to standard so the job still completes without HD.
            if mode != "standard" and _is_mode_rejected(exc):
                logger.warning(
                    "MuAPI rejected mode=%r (%s); retrying with mode=standard",
                    mode,
                    exc,
                )
                payload = self._payload(prompt, image_url, duration, aspect_ratio, "standard")
                return await self.client.generate(
                    self.VIDEO_ENDPOINT,
                    payload,
                    poll_interval=3.0,
                    max_polls=200,
                )
            raise
