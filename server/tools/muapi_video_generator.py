"""MuAPI image-to-video generation (Kling v3.0 Pro / Standard)."""

import logging
import os
from typing import Any, Dict, Optional

from tools.muapi_client import MuAPIClient, MuAPIError

logger = logging.getLogger(__name__)

# `or` (not a get() default): deployment files declare MUSEFORGE_DEMO_VIDEO
# as an optional passthrough, so it commonly arrives as an EMPTY string
# rather than unset -- and an empty demo URL breaks demo mode outright.
DEMO_VIDEO_URL = os.environ.get("MUSEFORGE_DEMO_VIDEO", "").strip() or (
    # The former default (Google's gtv-videos-bucket sample) started
    # returning 403 when that bucket was made private, which silently
    # broke demo mode: jobs completed but the "finished" video would not
    # play. Any third-party fixture can go the same way -- set
    # MUSEFORGE_DEMO_VIDEO in the deployment env to override without a
    # code change (render.yaml / docker-compose.yml both declare it).
    "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4"
)

# Confirmed MuAPI playground endpoints: Pro vs Standard is the endpoint
# itself, not a `mode` field inside one shared payload.
PRO_ENDPOINT = os.environ.get(
    "MUAPI_VIDEO_MODEL_PRO", "kling-v3.0-pro-image-to-video"
)
STANDARD_ENDPOINT = os.environ.get(
    "MUAPI_VIDEO_MODEL_STANDARD", "kling-v3.0-standard-image-to-video"
)


def endpoint_for_plan(plan: str) -> str:
    return PRO_ENDPOINT if (plan or "").lower() == "pro" else STANDARD_ENDPOINT


def is_native_audio_enabled() -> bool:
    """Whether to ask Kling to generate its own audio track.

    OFF by default, because that audio is unconditionally DISCARDED further
    down the pipeline: concatenate_videos() passes ``-an`` (and the moviepy
    fallback writes ``audio=False``), then add_background_music() lays the
    real score and dialogue over a silent picture. Requesting it only spent
    generation time and credits on a track no viewer could ever hear.

    Kept behind a flag rather than deleted so native Kling audio can be
    switched on the day the assembly step is taught to keep it.
    """
    return os.environ.get("MUSEFORGE_KLING_NATIVE_AUDIO", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _is_endpoint_rejected(exc: Exception) -> bool:
    """True when MuAPI likely rejected the endpoint (404/422)."""
    msg = str(exc).lower()
    if "404" in msg or "422" in msg:
        return True
    if "status_code=404" in msg or "status_code=422" in msg:
        return True
    return False


# Kept for any legacy callers / older Kling enums (5 or 10 only).
# New v3.0 path uses clamp_duration() instead.
VALID_DURATIONS = (5, 10)


def nearest_valid_duration(seconds) -> int:
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return VALID_DURATIONS[0]
    return min(VALID_DURATIONS, key=lambda d: abs(d - seconds))


def clamp_duration(seconds) -> int:
    """Kling v3.0 accepts integer duration 3–15 (default 5)."""
    try:
        value = int(round(float(seconds)))
    except (TypeError, ValueError):
        return 5
    return max(3, min(15, value))


class MuAPIVideoGenerator:
    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)

    def _payload(
        self,
        prompt: str,
        image_url: str,
        duration: int,
        generate_audio: bool = True,
        last_image: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Schema confirmed against MuAPI playground for kling-v3.0-*-image-to-video:
        # prompt, image_url, duration (int 3-15), generate_audio; optional last_image.
        # No `mode` field — Pro/Standard is selected via endpoint_for_plan().
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "image_url": image_url,
            "duration": clamp_duration(duration),
            "generate_audio": generate_audio,
        }
        if last_image:
            payload["last_image"] = last_image
        return payload

    async def generate_video_from_image(
        self,
        prompt: str,
        image_url: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        plan: str = "free",
        is_cancelled=None,
    ) -> str:
        # aspect_ratio kept in the signature for callers; not sent in payload
        # (Kling i2v derives aspect from the source image).
        _ = aspect_ratio
        if self.demo:
            return DEMO_VIDEO_URL

        endpoint = endpoint_for_plan(plan)
        payload = self._payload(
            prompt, image_url, duration, generate_audio=is_native_audio_enabled()
        )

        try:
            return await self.client.generate(
                endpoint,
                payload,
                poll_interval=3.0,
                max_polls=200,
                is_cancelled=is_cancelled,
            )
        except MuAPIError as exc:
            # Pro endpoint missing / schema mismatch — fall back to Standard
            # so the job still completes (same idea as the old mode fallback).
            if endpoint != STANDARD_ENDPOINT and _is_endpoint_rejected(exc):
                logger.warning(
                    "MuAPI rejected endpoint=%r (%s); retrying with %r",
                    endpoint,
                    exc,
                    STANDARD_ENDPOINT,
                )
                return await self.client.generate(
                    STANDARD_ENDPOINT,
                    payload,
                    poll_interval=3.0,
                    max_polls=200,
                    is_cancelled=is_cancelled,
                )
            raise
