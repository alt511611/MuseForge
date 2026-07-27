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
    """Endpoints must be adjustable via env var without a code change.

    NOTE: deliberately does NOT use importlib.reload() here -- reloading a
    module replaces its class objects with new ones, but any other module
    that already did `from tools.x import Y` still holds the OLD class
    reference. That mismatch broke unrelated tests' monkeypatches when run
    in the same session (patches applied to the reloaded module's fresh
    class didn't affect instances created via the stale reference held
    elsewhere, e.g. in pipelines/script2video.py). A source-level check
    avoids mutating any shared module state.
    """
    import inspect
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod

    img_source = inspect.getsource(img_mod)
    vid_source = inspect.getsource(vid_mod)
    assert 'os.environ.get("MUAPI_IMAGE_MODEL"' in img_source
    assert "MUAPI_VIDEO_MODEL_PRO" in vid_source
    assert "MUAPI_VIDEO_MODEL_STANDARD" in vid_source
    assert "os.environ.get" in vid_source


def test_video_payload_matches_kling_v3_schema():
    """Kling v3.0 i2v: prompt/image_url/duration/generate_audio; no mode,
    no aspect_ratio (derived from source image)."""
    from tools.muapi_video_generator import MuAPIVideoGenerator

    gen = MuAPIVideoGenerator(api_key="test-key")
    payload = gen._payload("pan left", "https://cdn.example/f.jpg", 5)
    assert "aspect_ratio" not in payload
    assert "mode" not in payload
    assert payload["duration"] == 5
    assert payload["generate_audio"] is True
    assert payload["prompt"] == "pan left"
    assert payload["image_url"] == "https://cdn.example/f.jpg"
    import inspect
    import tools.muapi_video_generator as vid_mod

    source = inspect.getsource(vid_mod)
    assert '"aspect_ratio"' not in source

    assert vid_mod.endpoint_for_plan("free") == vid_mod.STANDARD_ENDPOINT
    assert vid_mod.endpoint_for_plan("creator") == vid_mod.STANDARD_ENDPOINT
    assert vid_mod.endpoint_for_plan("pro") == vid_mod.PRO_ENDPOINT
    assert vid_mod.endpoint_for_plan("pro") != vid_mod.STANDARD_ENDPOINT
