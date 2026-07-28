"""MuAPI image generation with reference support for character consistency."""

import hashlib
import logging
import os

from tools.muapi_client import MuAPIClient, MuAPIError

logger = logging.getLogger(__name__)

# Pixel sizes for flux-2-pro / flux-dev-image style "size" payloads
# (e.g. "1024*1024"). Also used for demo placeholder URLs.
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
    # Referanssız text-to-image: flux-2-pro (size "W*H" schema).
    # flux-3-text-to-image currently 404s on MuAPI (not live yet).
    IMAGE_ENDPOINT = os.environ.get("MUAPI_IMAGE_MODEL", "flux-2-pro")
    # Legacy size-based endpoint kept only as PuLID fail-open fallback.
    LEGACY_SIZE_ENDPOINT = os.environ.get(
        "MUAPI_IMAGE_FALLBACK_MODEL", "flux-dev-image"
    )
    # Default stays flux-pulid -- confirmed working against real videos, do
    # not change. Override via MUAPI_KONTEXT_MODEL (e.g. to the cheaper
    # "flux-kontext-dev-i2i" tier) to try a different reference-image model;
    # generate_image_with_reference() below picks the correct payload shape
    # for whichever endpoint is configured (PuLID vs. the Kontext family use
    # different reference-image field names).
    KONTEXT_ENDPOINT = os.environ.get(
        "MUAPI_KONTEXT_MODEL", "flux-pulid"
    )

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)

    def _size_payload(
        self, prompt: str, aspect_ratio: str, reference_url: str = None
    ) -> dict:
        """flux-2-pro / flux-dev-image style payload (combined size string)."""
        dims = ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"])
        payload = {
            "prompt": prompt,
            "size": f"{dims['width']}*{dims['height']}",
            "num_inference_steps": 28,
            "seed": -1,
            "guidance_scale": 3.5,
            "num_images": 1,
        }
        if reference_url:
            payload["image"] = reference_url
        return payload

    # Aliases kept for call sites / tests.
    def _text_to_image_payload(self, prompt: str, aspect_ratio: str) -> dict:
        return self._size_payload(prompt, aspect_ratio)

    def _legacy_size_payload(
        self, prompt: str, aspect_ratio: str, reference_url: str = None
    ) -> dict:
        return self._size_payload(prompt, aspect_ratio, reference_url)

    def _build_payload(self, prompt: str, aspect_ratio: str, reference_url: str = None) -> dict:
        return self._size_payload(prompt, aspect_ratio, reference_url)

    async def generate_image(
        self, prompt: str, aspect_ratio: str = "1:1", is_cancelled=None
    ) -> str:
        if self.demo:
            return _demo_image_url(prompt, aspect_ratio)
        payload = self._text_to_image_payload(prompt, aspect_ratio)
        logger.info(
            "Sending %s request WITHOUT reference (prompt starts: %.80s)",
            self.IMAGE_ENDPOINT,
            prompt,
        )
        try:
            return await self.client.generate(
                self.IMAGE_ENDPOINT, payload, is_cancelled=is_cancelled
            )
        except MuAPIError as exc:
            message = str(exc).lower()
            is_schema_rejection = "404" in message or "422" in message
            is_runtime_failure = (
                '"status":"failed"' in message.replace(" ", "")
                or "internal error" in message
            )
            if not (is_schema_rejection or is_runtime_failure):
                raise

            logger.warning(
                "%s failed (schema_rejection=%s, runtime_failure=%s): %s; "
                "falling back to %s",
                self.IMAGE_ENDPOINT,
                is_schema_rejection,
                is_runtime_failure,
                exc,
                self.LEGACY_SIZE_ENDPOINT,
            )
            fallback_payload = self._legacy_size_payload(prompt, aspect_ratio)
            return await self.client.generate(
                self.LEGACY_SIZE_ENDPOINT, fallback_payload, is_cancelled=is_cancelled
            )

    async def generate_image_with_reference(
        self,
        prompt: str,
        reference_url: str,
        aspect_ratio: str = "16:9",
        is_cancelled=None,
    ) -> str:
        if self.demo:
            return _demo_image_url(prompt + "|ref", aspect_ratio)

        endpoint = self.KONTEXT_ENDPOINT
        if "pulid" in endpoint.lower():
            # PuLID is identity-focused and uses a singular reference URL.
            payload = {
                "prompt": prompt,
                "image_url": reference_url,
                "aspect_ratio": aspect_ratio,
            }
        else:
            # Kontext family (e.g. flux-kontext-dev-i2i, flux-kontext-pro-i2i)
            # expects a LIST of reference images under "images_list" --
            # confirmed against MuAPI's own 422 validation error during an
            # earlier attempt ({"loc": ["body", "images_list"]}).
            payload = {
                "prompt": prompt,
                "images_list": [reference_url],
                "aspect_ratio": aspect_ratio,
            }
        logger.info(
            "Sending %s request with reference (prompt starts: %.80s)",
            endpoint,
            prompt,
        )
        try:
            return await self.client.generate(
                endpoint,
                payload,
                is_cancelled=is_cancelled,
            )
        except MuAPIError as exc:
            message = str(exc).lower()
            is_schema_rejection = "404" in message or "422" in message
            is_runtime_failure = (
                '"status":"failed"' in message.replace(" ", "")
                or "internal error" in message
            )
            if not (is_schema_rejection or is_runtime_failure):
                raise

            logger.warning(
                "%s failed (schema_rejection=%s, runtime_failure=%s): %s; "
                "falling back to %s reference payload",
                endpoint,
                is_schema_rejection,
                is_runtime_failure,
                exc,
                self.LEGACY_SIZE_ENDPOINT,
            )
            fallback_payload = self._legacy_size_payload(
                prompt,
                aspect_ratio,
                reference_url,
            )
            return await self.client.generate(
                self.LEGACY_SIZE_ENDPOINT,
                fallback_payload,
                is_cancelled=is_cancelled,
            )
