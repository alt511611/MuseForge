"""fal.ai FLUX image provider tests (flux-pro/v1.1 + flux-pro/kontext)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


def test_image_factory_defaults_to_muapi(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_IMAGE_PROVIDER", raising=False)
    from pipelines.script2video import _make_image_generator
    from tools.muapi_image_generator import MuAPIImageGenerator

    assert isinstance(_make_image_generator("k", demo=False), MuAPIImageGenerator)


def test_image_factory_returns_falai(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import _make_image_generator
    from tools.falai_image_generator import FalAIImageGenerator

    assert isinstance(_make_image_generator("k", demo=False), FalAIImageGenerator)


@pytest.mark.asyncio
async def test_generate_image_uses_flux_pro_v11_schema(monkeypatch):
    import tools.falai_image_generator as mod
    from tools.falai_image_generator import FalAIImageGenerator

    captured = {}

    async def fake_fal_generate(client, endpoint, arguments, **_kwargs):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {"images": [{"url": "https://fal.media/img.jpg"}]}

    monkeypatch.setattr(mod, "fal_generate", fake_fal_generate)

    gen = FalAIImageGenerator(api_key="k", demo=False)
    url = await gen.generate_image("a cat", aspect_ratio="16:9")

    assert url == "https://fal.media/img.jpg"
    assert captured["endpoint"] == "fal-ai/flux-pro/v1.1"
    assert captured["arguments"]["prompt"] == "a cat"
    assert captured["arguments"]["image_size"] == "landscape_16_9"
    assert captured["arguments"]["num_images"] == 1


@pytest.mark.asyncio
async def test_generate_image_with_reference_uses_kontext_image_url(monkeypatch):
    """Confirmed: fal Kontext uses singular image_url — NOT images_list."""
    import tools.falai_image_generator as mod
    from tools.falai_image_generator import FalAIImageGenerator

    captured = {}

    async def fake_fal_generate(client, endpoint, arguments, **_kwargs):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {"images": [{"url": "https://fal.media/ref.jpg"}]}

    monkeypatch.setattr(mod, "fal_generate", fake_fal_generate)

    gen = FalAIImageGenerator(api_key="k", demo=False)
    url = await gen.generate_image_with_reference(
        "same person in a cafe",
        "https://example.com/portrait.png",
        aspect_ratio="16:9",
    )

    assert url == "https://fal.media/ref.jpg"
    assert captured["endpoint"] == "fal-ai/flux-pro/kontext"
    args = captured["arguments"]
    assert args["prompt"] == "same person in a cafe"
    assert args["image_url"] == "https://example.com/portrait.png"
    assert args["aspect_ratio"] == "16:9"
    assert "images_list" not in args
    assert "image_urls" not in args


@pytest.mark.asyncio
async def test_demo_mode_no_network():
    from tools.falai_image_generator import FalAIImageGenerator

    gen = FalAIImageGenerator(api_key="", demo=True)
    url = await gen.generate_image("x", "1:1")
    assert url.startswith("https://picsum.photos/")
