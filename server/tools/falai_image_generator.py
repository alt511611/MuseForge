"""fal.ai FLUX image generation — optional alternative to MuAPIImageGenerator.

Selected via MUSEFORGE_IMAGE_PROVIDER=falai (default remains "muapi").

Schemas CONFIRMED against fal.ai's own docs:

1) Text-to-image (generate_image) — fal-ai/flux-pro/v1.1
   https://fal.ai/models/fal-ai/flux-pro/v1.1/api
   input:  prompt (str, required),
           image_size (enum square_hd|square|portrait_4_3|portrait_16_9|
                       landscape_4_3|landscape_16_9 OR {width,height}),
           num_images, output_format, ...
   output: {"images": [{"url": "...", ...}, ...], ...}

2) Image-to-image / character reference (generate_image_with_reference)
   — fal-ai/flux-pro/kontext
   https://fal.ai/models/fal-ai/flux-pro/kontext/api
   input:  prompt (str, required),
           image_url (str, required) — singular reference image,
           aspect_ratio (enum 21:9|16:9|4:3|3:2|1:1|2:3|3:4|9:16|9:21),
           guidance_scale, num_images, output_format, ...
   output: {"images": [{"url": "...", ...}, ...], ...}

NOTE: fal's Kontext uses singular ``image_url`` (NOT MuAPI's images_list /
image_urls). Do not confuse the two schemas.

Errors raise (no silent MuAPI fallback).
"""

from __future__ import annotations

import hashlib
import os
from typing import Callable, Optional

from tools.falai_common import fal_generate, make_fal_client

ASPECT_RATIO_MAP = {
    "1:1": {"width": 1024, "height": 1024},
    "16:9": {"width": 1344, "height": 768},
    "9:16": {"width": 768, "height": 1344},
    "4:3": {"width": 1152, "height": 896},
}

# fal-ai/flux-pro/v1.1 accepts named enums; map our ratios onto the closest.
IMAGE_SIZE_ENUM = {
    "1:1": "square_hd",
    "16:9": "landscape_16_9",
    "9:16": "portrait_16_9",
    "4:3": "landscape_4_3",
}

KONTEXT_ASPECT_RATIOS = {
    "21:9",
    "16:9",
    "4:3",
    "3:2",
    "1:1",
    "2:3",
    "3:4",
    "9:16",
    "9:21",
}


def _demo_image_url(prompt: str, aspect_ratio: str) -> str:
    dims = ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"])
    seed = hashlib.sha1(f"{prompt}|{aspect_ratio}".encode()).hexdigest()[:12]
    return f"https://picsum.photos/seed/{seed}/{dims['width']}/{dims['height']}"


class FalAIImageGenerator:
    TEXT_ENDPOINT = os.environ.get("FALAI_IMAGE_MODEL", "fal-ai/flux-pro/v1.1")
    KONTEXT_ENDPOINT = os.environ.get(
        "FALAI_KONTEXT_MODEL", "fal-ai/flux-pro/kontext"
    )

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        self.client = make_fal_client(self.api_key)

    async def generate_image(
        self, prompt: str, aspect_ratio: str = "1:1", is_cancelled=None
    ) -> str:
        if self.demo:
            return _demo_image_url(prompt, aspect_ratio)

        payload = {
            "prompt": prompt,
            "image_size": IMAGE_SIZE_ENUM.get(aspect_ratio)
            or ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"]),
            "num_images": 1,
            "output_format": "jpeg",
        }
        result = await fal_generate(
            self.client,
            self.TEXT_ENDPOINT,
            payload,
            is_cancelled=is_cancelled,
        )
        return self._first_image_url(result)

    async def generate_image_with_reference(
        self,
        prompt: str,
        reference_url: str,
        aspect_ratio: str = "16:9",
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        if self.demo:
            return _demo_image_url(prompt + "|ref", aspect_ratio)

        # Confirmed: fal Kontext wants singular image_url, not a list.
        payload = {
            "prompt": prompt,
            "image_url": reference_url,
            "aspect_ratio": (
                aspect_ratio if aspect_ratio in KONTEXT_ASPECT_RATIOS else "16:9"
            ),
            "num_images": 1,
            "output_format": "jpeg",
        }
        result = await fal_generate(
            self.client,
            self.KONTEXT_ENDPOINT,
            payload,
            is_cancelled=is_cancelled,
        )
        return self._first_image_url(result)

    @staticmethod
    def _first_image_url(result) -> str:
        images = (result or {}).get("images") or []
        if not images or not images[0].get("url"):
            raise RuntimeError(f"fal.ai image completed but no image URL: {result}")
        return images[0]["url"]
