"""MuAPI image generation with reference support for character consistency."""

import hashlib
import os

from tools.muapi_client import MuAPIClient

ASPECT_RATIO_MAP = {
    "1:1": {"width": 1024, "height": 1024},
    "16:9": {"width": 1344, "height": 768},
    "9:16": {"width": 768, "height": 1344},
    "4:3": {"width": 1152, "height": 896},
}


def _demo_image_url(prompt: str, aspect_ratio: str) -> str:
    """Deterministic placeholder image so the pipeline works with no API key."""
    dims = ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"])
    seed = hashlib.sha1(f"{prompt}|{aspect_ratio}".encode()).hexdigest()[:12]
    return f"https://picsum.photos/seed/{seed}/{dims['width']}/{dims['height']}"


class MuAPIImageGenerator:
    # Confirmed against MuAPI's own docs page (muapi.ai/docs/flux-dev),
    # which shows the real endpoint as "flux-dev-image", not "flux-dev" --
    # the bare "flux-dev" slug 404s. Configurable via env var in case
    # MuAPI's catalog changes again; no code change needed if so.
    IMAGE_ENDPOINT = os.environ.get("MUAPI_IMAGE_MODEL", "flux-dev-image")

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)

    def _build_payload(self, prompt: str, aspect_ratio: str, reference_url: str = None) -> dict:
        dims = ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"])
        payload = {
            "prompt": prompt,
            # MuAPI's flux-dev-image docs show a combined "size" string
            # (e.g. "1024*1024"), not separate width/height fields.
            "size": f"{dims['width']}*{dims['height']}",
            "num_inference_steps": 28,
            "seed": -1,
            "guidance_scale": 3.5,
            "num_images": 1,
        }
        if reference_url:
            # NOTE: MuAPI's own example curl shows an "image" field for
            # reference input, but leaves it empty in their sample --
            # the exact expected value (URL vs base64) isn't confirmed
            # from that doc alone. If character-reference generation
            # fails, check MuAPI's flux-dev-image playground page for the
            # confirmed reference-image parameter and adjust here.
            payload["image"] = reference_url
        return payload

    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        if self.demo:
            return _demo_image_url(prompt, aspect_ratio)
        payload = self._build_payload(prompt, aspect_ratio)
        return await self.client.generate(self.IMAGE_ENDPOINT, payload)

    async def generate_image_with_reference(
        self,
        prompt: str,
        reference_url: str,
        aspect_ratio: str = "16:9",
    ) -> str:
        if self.demo:
            return _demo_image_url(prompt + "|ref", aspect_ratio)
        payload = self._build_payload(prompt, aspect_ratio, reference_url)
        return await self.client.generate(self.IMAGE_ENDPOINT, payload)
