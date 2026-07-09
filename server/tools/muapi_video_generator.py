"""MuAPI image-to-video generation."""

import os

from tools.muapi_client import MuAPIClient

DEMO_VIDEO_URL = os.environ.get(
    "MUSEFORGE_DEMO_VIDEO",
    "https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
)


class MuAPIVideoGenerator:
    VIDEO_ENDPOINT = "kling-o1-standard-image-to-video"

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
            "aspect_ratio": aspect_ratio,
        }
        return await self.client.generate(
            self.VIDEO_ENDPOINT,
            payload,
            poll_interval=3.0,
            max_polls=200,
        )
