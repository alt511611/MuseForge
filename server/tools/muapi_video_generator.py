"""MuAPI image-to-video generation."""

import os

from tools.muapi_client import MuAPIClient

DEMO_VIDEO_URL = os.environ.get(
    "MUSEFORGE_DEMO_VIDEO",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
)


class MuAPIVideoGenerator:
    # UPDATED based on finding MuAPI's own playground page at
    # muapi.ai/playground/kling-o1-image-to-video -- suggesting "standard"
    # is a *mode* parameter, not part of the URL slug (the previous
    # "kling-o1-standard-image-to-video" 404'd... then this slug got a 422,
    # meaning it's at least a real, reachable endpoint, unlike the 404 case).
    # STILL NOT independently confirmed with an exact first-party curl
    # example (unlike flux-dev-image, which was). If this 422s again,
    # open https://muapi.ai/playground/kling-o1-image-to-video directly and
    # check the exact parameter names/schema shown there.
    VIDEO_ENDPOINT = os.environ.get("MUAPI_VIDEO_MODEL", "kling-o1-image-to-video")

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)

    async def generate_video_from_image(
        self,
        prompt: str,
        image_url: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
    ) -> str:
        if self.demo:
            return DEMO_VIDEO_URL
        payload = {
            "prompt": prompt,
            "image_url": image_url,
            "duration": duration,
            "mode": "standard",
            # aspect_ratio removed: most Kling image-to-video APIs (across
            # several providers, consistently) derive the output aspect
            # ratio from the source image itself rather than accepting it
            # as a request parameter -- a likely candidate for the 422
            # ("Unprocessable Entity" = reachable endpoint, invalid field).
        }
        return await self.client.generate(
            self.VIDEO_ENDPOINT,
            payload,
            poll_interval=3.0,
            max_polls=200,
        )
