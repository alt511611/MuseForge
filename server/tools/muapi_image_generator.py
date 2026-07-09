"""MuAPI image generation with reference support for character consistency."""

import hashlib

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
    IMAGE_ENDPOINT = "flux-dev"

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)

    def _build_payload(self, prompt: str, aspect_ratio: str, reference_url: str = None) -> dict:
        dims = ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"])
        payload = {
            "prompt": prompt,
            "width": dims["width"],
            "height": dims["height"],
        }
        if reference_url:
            payload["image_url"] = reference_url
            payload["strength"] = 0.65
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
