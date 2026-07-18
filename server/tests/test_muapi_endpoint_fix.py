"""Verify the flux-dev-image endpoint fix: correct endpoint slug (confirmed
against MuAPI's own docs) and correct payload shape (combined "size"
string, not separate width/height).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


def test_image_endpoint_matches_muapi_docs():
    from tools.muapi_image_generator import MuAPIImageGenerator

    # Confirmed against https://www.muapi.ai/docs/flux-dev's own curl
    # example: POST https://api.muapi.ai/api/v1/flux-dev-image
    assert MuAPIImageGenerator.IMAGE_ENDPOINT == "flux-dev-image"


def test_payload_uses_combined_size_string_not_separate_dimensions():
    from tools.muapi_image_generator import MuAPIImageGenerator

    gen = MuAPIImageGenerator(api_key="test-key")
    payload = gen._build_payload("a cat", "1:1")

    assert payload["size"] == "1024*1024"
    assert "width" not in payload
    assert "height" not in payload


def test_reference_image_uses_image_field():
    from tools.muapi_image_generator import MuAPIImageGenerator

    gen = MuAPIImageGenerator(api_key="test-key")
    payload = gen._build_payload("a cat", "16:9", reference_url="https://example.com/ref.png")

    assert payload["image"] == "https://example.com/ref.png"
    assert "image_url" not in payload


@pytest.mark.asyncio
async def test_demo_mode_still_works_without_network():
    from tools.muapi_image_generator import MuAPIImageGenerator

    gen = MuAPIImageGenerator(api_key="test-key", demo=True)
    url = await gen.generate_image("a cat", "1:1")
    assert url.startswith("https://picsum.photos/")


def test_endpoints_are_env_overridable():
    """Both endpoints must be adjustable via env var without a code change,
    since neither could be 100% confirmed against first-party docs (image
    endpoint was confirmed; video endpoint was not)."""
    assert os.environ.get("MUAPI_IMAGE_MODEL_ENV_SUPPORTED", True)
    import importlib
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod

    os.environ["MUAPI_IMAGE_MODEL"] = "some-other-image-model"
    os.environ["MUAPI_VIDEO_MODEL"] = "some-other-video-model"
    importlib.reload(img_mod)
    importlib.reload(vid_mod)
    try:
        assert img_mod.MuAPIImageGenerator.IMAGE_ENDPOINT == "some-other-image-model"
        assert vid_mod.MuAPIVideoGenerator.VIDEO_ENDPOINT == "some-other-video-model"
    finally:
        del os.environ["MUAPI_IMAGE_MODEL"]
        del os.environ["MUAPI_VIDEO_MODEL"]
        importlib.reload(img_mod)
        importlib.reload(vid_mod)


def test_video_payload_no_longer_sends_aspect_ratio():
    """aspect_ratio removed as a likely cause of the reported 422 --
    Kling image-to-video APIs typically derive aspect ratio from the
    source image rather than accepting it as a parameter. Not a
    first-party-confirmed fact (unlike the flux-dev-image fix), so this
    test documents the current best-effort payload shape rather than an
    assertion the endpoint is exactly correct."""
    # We can't easily unit test the private payload dict without a real
    # network call, so this test asserts on the source directly to catch
    # any accidental re-introduction of aspect_ratio into the payload.
    import inspect
    import tools.muapi_video_generator as vid_mod

    source = inspect.getsource(vid_mod.MuAPIVideoGenerator.generate_video_from_image)
    assert '"aspect_ratio"' not in source
    assert '"mode": "standard"' in source
