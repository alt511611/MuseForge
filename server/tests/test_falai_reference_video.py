"""fal.ai Kling O3 Pro reference-to-video provider tests."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


def test_factory_returns_reference_generator(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_reference")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import _make_video_generator
    from tools.falai_reference_video_generator import FalAIReferenceVideoGenerator

    gen = _make_video_generator("test-key", demo=False)
    assert isinstance(gen, FalAIReferenceVideoGenerator)
    assert gen.uses_character_reference_to_video is True


def test_factory_default_still_muapi(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_VIDEO_PROVIDER", raising=False)
    from pipelines.script2video import _make_video_generator
    from tools.muapi_video_generator import MuAPIVideoGenerator

    assert isinstance(_make_video_generator("k", demo=False), MuAPIVideoGenerator)


@pytest.mark.asyncio
async def test_reference_payload_uses_confirmed_elements_schema(monkeypatch):
    """Payload must match fal.ai reference-to-video OpenAPI:
    elements[].frontal_image_url + reference_image_urls, duration as STRING,
    aspect_ratio, prompt with @Element1 — NOT generate_audio (deferred).
    """
    import tools.falai_reference_video_generator as mod
    from tools.falai_reference_video_generator import FalAIReferenceVideoGenerator

    captured = {}

    async def fake_fal_generate(client, endpoint, arguments, **_kwargs):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {"video": {"url": "https://fal.media/ref.mp4"}}

    monkeypatch.setattr(mod, "fal_generate", fake_fal_generate)

    gen = FalAIReferenceVideoGenerator(api_key="k", demo=False)
    url = await gen.generate_video_from_image(
        prompt="walks toward the camera",
        image_url="https://example.com/portrait.png",
        duration=8,
        aspect_ratio="9:16",
    )

    assert url == "https://fal.media/ref.mp4"
    assert captured["endpoint"] == "fal-ai/kling-video/o3/pro/reference-to-video"
    args = captured["arguments"]
    assert args["prompt"].startswith("@Element1.")
    assert "walks toward the camera" in args["prompt"]
    assert args["duration"] == "8"
    assert args["aspect_ratio"] == "9:16"
    assert args["elements"] == [
        {
            "frontal_image_url": "https://example.com/portrait.png",
            "reference_image_urls": ["https://example.com/portrait.png"],
        }
    ]
    assert "generate_audio" not in args
    assert "image_url" not in args  # that field is for plain image-to-video


@pytest.mark.asyncio
async def test_demo_mode_skips_network():
    from tools.falai_reference_video_generator import (
        DEMO_VIDEO_URL,
        FalAIReferenceVideoGenerator,
    )

    gen = FalAIReferenceVideoGenerator(api_key="", demo=True)
    assert await gen.generate_video_from_image("p", "https://x") == DEMO_VIDEO_URL
