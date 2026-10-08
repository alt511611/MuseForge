"""fal.ai Vidu Q4 reference-to-video -- one-step character-consistent video.

Selected via MUSEFORGE_VIDEO_PROVIDER=falai_vidu. Same shape as
falai_reference (Kling O3): the locked portrait is a reference, the frame step
is skipped, and the shot's motion prompt animates it in one call.

Why it exists: a candidate to compare against Kling v3 on the same shot. On
the catalogue's own numbers a 30 s drama costs about $2.00-$2.85 at 720p and
$2.52-$3.60 at 1080p, against $2.52-$3.78 for Kling v3 Standard, and audio is
not billed. Quality is NOT established by that table -- this is here so it can
be measured, not because it has been shown better.

Schema CONFIRMED against fal.ai's OpenAPI
(/api/openapi/queue/openapi.json?endpoint_id=fal-ai/vidu/q4/reference-to-video):
    input:
      prompt (str, required, <=5000) -- refer to references by position:
          [@reference_image_1], [@reference_image_2] ...
      reference_image_urls (list[str]) -- up to 12 (png, jpeg, jpg, webp)
      reference_audio_urls (list[str]) -- up to 3 mp3, 3-12 s each
      duration (int 3..16, default 5)
      resolution ("540p"|"720p"|"1080p"|"2K"|"4K", default "720p")
      aspect_ratio ("16:9"|"9:16"|"4:3"|"3:4"|"1:1", default "16:9")
      audio (bool, default false) -- true generates dialogue and effects
      seed (int)
    output: {"video": {"url": ...}, "cover_image": {...}, "seed": int}

Two things this schema does NOT have, and what that costs:
* No end frame. The acted-peak ``last_image`` the pipeline can pass is
  accepted for signature parity and ignored.
* No cut control. Whether the model cuts inside a generation from the prompt
  alone is unverified, so this runs the per-shot path, one generation per
  framing, exactly as falai_reference does.

``audio`` is left at the schema default (off): the dialogue is voiced by the
TTS pass and mixed afterwards, and a model-made track on top would double it.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from tools.falai_common import fal_generate, make_fal_client
from tools.falai_reference_video_generator import DEMO_VIDEO_URL

ENDPOINT_DEFAULT = "fal-ai/vidu/q4/reference-to-video"

MIN_DURATION_SECONDS = 3
MAX_DURATION_SECONDS = 16
MAX_PROMPT_CHARS = 5000
VALID_ASPECT_RATIOS = {"16:9", "9:16", "4:3", "3:4", "1:1"}
VALID_RESOLUTIONS = ("540p", "720p", "1080p", "2K", "4K")
DEFAULT_RESOLUTION = "720p"


def _duration(seconds) -> int:
    try:
        value = int(round(float(seconds)))
    except (TypeError, ValueError):
        value = 5
    return max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, value))


def _aspect_ratio(ratio: str) -> str:
    return ratio if ratio in VALID_ASPECT_RATIOS else "16:9"


def _resolution() -> str:
    """FALAI_VIDU_RESOLUTION, case-insensitively, or 720p.

    An unknown value is a 422 from fal on every shot of every job, so it falls
    back rather than being passed through.
    """
    raw = (os.environ.get("FALAI_VIDU_RESOLUTION", "") or "").strip()
    for known in VALID_RESOLUTIONS:
        if raw.lower() == known.lower():
            return known
    return DEFAULT_RESOLUTION


class FalAIViduVideoGenerator:
    """Drop-in for MuAPIVideoGenerator.generate_video_from_image.

    ``uses_character_reference_to_video`` tells script2video to skip the
    separate frame step and treat ``image_url`` as the character reference.
    """

    uses_character_reference_to_video = True

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        self.client = make_fal_client(self.api_key, demo=demo)

    @property
    def endpoint(self) -> str:
        return os.environ.get("FALAI_VIDU_VIDEO_MODEL", "").strip() or ENDPOINT_DEFAULT

    async def generate_video_from_image(
        self,
        prompt: str,
        image_url: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        plan: str = "free",
        is_cancelled: Optional[Callable[[], bool]] = None,
        shot_profile: Optional[str] = None,
        last_image: Optional[str] = None,
    ) -> str:
        # plan, shot_profile and last_image: signature parity only -- no HD
        # mode, no MuAPI-style routing, and no end-frame field on this schema.
        _ = (plan, shot_profile, last_image)
        if self.demo:
            return DEMO_VIDEO_URL

        payload = {
            "prompt": f"[@reference_image_1] {prompt}"[:MAX_PROMPT_CHARS],
            "reference_image_urls": [image_url],
            "duration": _duration(duration),
            "resolution": _resolution(),
            "aspect_ratio": _aspect_ratio(aspect_ratio),
        }
        result = await fal_generate(
            self.client,
            self.endpoint,
            payload,
            is_cancelled=is_cancelled,
        )
        video_url = ((result or {}).get("video") or {}).get("url")
        if not video_url:
            raise RuntimeError(
                f"fal.ai Vidu reference-to-video completed but no video URL: {result}"
            )
        return video_url
