"""fal.ai Kling O3 Pro reference-to-video — one-step character-consistent video.

Selected via MUSEFORGE_VIDEO_PROVIDER=falai_reference (third option alongside
"muapi" / "falai"; default remains "muapi"). Replaces the two-step
PuLID-frame + Kling-animate path with a single fal.ai call that binds
character identity via ``elements`` and animates from the prompt.

Schema CONFIRMED against fal.ai's own OpenAPI/docs
(https://fal.ai/models/fal-ai/kling-video/o3/pro/reference-to-video/api):
    input:
      prompt (str) — use @Element1 / @Image1 tags to bind references
      start_image_url (str, optional) — first frame
      end_image_url (str, optional)
      image_urls (list[str], optional) — style/appearance refs (@ImageN)
      elements (list[{
          frontal_image_url: str,
          reference_image_urls: list[str]
      }], optional) — characters/objects (@ElementN)
      duration (str enum "3".."15", default "5")
      aspect_ratio ("16:9" | "9:16" | "1:1", default "16:9")
      generate_audio (bool, optional) — LEFT UNSET for now (later step)
    output: {"video": {"url": "...", ...}}

Errors raise (no silent MuAPI fallback) — this provider is an explicit choice.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from tools.falai_common import fal_generate, make_fal_client

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

MIN_DURATION_SECONDS = 3
MAX_DURATION_SECONDS = 15
VALID_ASPECT_RATIOS = {"16:9", "9:16", "1:1"}


def _duration_str(seconds) -> str:
    try:
        value = int(round(float(seconds)))
    except (TypeError, ValueError):
        value = 5
    value = max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, value))
    return str(value)


def _aspect_ratio(ratio: str) -> str:
    return ratio if ratio in VALID_ASPECT_RATIOS else "16:9"


class FalAIReferenceVideoGenerator:
    """Drop-in for MuAPIVideoGenerator.generate_video_from_image.

    ``uses_character_reference_to_video`` tells script2video to skip the
    separate frame-generation step and treat ``image_url`` as the character
    portrait / element reference instead of an already-animated start frame.
    """

    uses_character_reference_to_video = True

    ENDPOINT = os.environ.get(
        "FALAI_REFERENCE_VIDEO_MODEL",
        "fal-ai/kling-video/o3/pro/reference-to-video",
    )

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        self.client = make_fal_client(self.api_key, demo=demo)

    async def generate_video_from_image(
        self,
        prompt: str,
        image_url: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        plan: str = "free",
        is_cancelled: Optional[Callable[[], bool]] = None,
        shot_profile: Optional[str] = None,
    ) -> str:
        # plan kept for signature parity; this endpoint has no HD/standard mode.
        # shot_profile likewise: MuAPI-only routing (tools/video_model_router).
        _ = plan
        _ = shot_profile
        if self.demo:
            return DEMO_VIDEO_URL

        # One-step identity bind: portrait becomes @Element1. Prompt is
        # prefixed so the model knows to keep that character consistent.
        # generate_audio deliberately omitted (later step).
        payload = {
            "prompt": f"@Element1. {prompt}",
            "elements": [
                {
                    "frontal_image_url": image_url,
                    "reference_image_urls": [image_url],
                }
            ],
            "duration": _duration_str(duration),
            "aspect_ratio": _aspect_ratio(aspect_ratio),
        }

        result = await fal_generate(
            self.client,
            self.ENDPOINT,
            payload,
            is_cancelled=is_cancelled,
        )
        video_url = ((result or {}).get("video") or {}).get("url")
        if not video_url:
            raise RuntimeError(
                f"fal.ai reference-to-video completed but no video URL: {result}"
            )
        return video_url
