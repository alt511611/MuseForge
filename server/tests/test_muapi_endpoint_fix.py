"""Verify MuAPI image endpoint + flux-2-pro size payload schema."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _expected_size(aspect_ratio):
    """Derive from the map so a deliberate resolution change does not
    silently fail an unrelated schema test."""
    from tools.muapi_image_generator import ASPECT_RATIO_MAP

    dims = ASPECT_RATIO_MAP[aspect_ratio]
    return f"{dims['width']}*{dims['height']}"
os.environ.setdefault("MUAPI_KEY", "test-key")


def test_image_endpoint_is_flux_2_pro():
    from tools.muapi_image_generator import MuAPIImageGenerator

    assert MuAPIImageGenerator.IMAGE_ENDPOINT == "flux-2-pro"
    assert MuAPIImageGenerator.KONTEXT_ENDPOINT == "flux-pulid"


def test_flux_2_pro_is_asked_in_ratios_not_pixels():
    """flux-2-pro's schema is {prompt, aspect_ratio, resolution}. Nothing else.

    Read off MuAPI's schema service, and the reason this test exists: the
    payload used to be `size: "864*1536"` with num_inference_steps, seed and
    guidance_scale, none of which flux-2-pro declares. It answered every call
    with HTTP 400 Internal Error, and the retry ladder paid for it three times
    per image before falling back.
    """
    from tools.muapi_image_generator import MuAPIImageGenerator

    gen = MuAPIImageGenerator(api_key="test-key")
    payload = gen._text_to_image_payload("a cat", "9:16")

    assert payload == {
        "prompt": "a cat",
        "aspect_ratio": "9:16",
        "resolution": "1k",
    }


def test_an_aspect_ratio_the_endpoint_does_not_take_becomes_one_it_does():
    from tools.muapi_image_generator import MuAPIImageGenerator

    gen = MuAPIImageGenerator(api_key="test-key")
    payload = gen._text_to_image_payload("a cat", "99:1")
    assert payload["aspect_ratio"] == "1:1", (
        "a ratio outside the endpoint's enum is refused, not clamped; order "
        "one it declares and let the frame be conformed downstream"
    )


def test_resolution_is_a_knob(monkeypatch):
    from tools.muapi_image_generator import MuAPIImageGenerator

    monkeypatch.setenv("MUSEFORGE_IMAGE_RESOLUTION", "2k")
    gen = MuAPIImageGenerator(api_key="test-key")
    assert gen._text_to_image_payload("a cat", "16:9")["resolution"] == "2k"


def test_flux_dev_image_is_asked_in_pixels_divisible_by_64():
    """The fallback's schema is {prompt, width, height, num_images}.

    It ignored the `size` string it used to be sent and rendered its 1024x1024
    default, which is how a 9:16 order kept coming back square. Its own
    constraint is that both axes are divisible by 64, so 864 -- the old 9:16
    width -- was never going to be honoured even once the field name was right.
    """
    from tools.muapi_image_generator import ASPECT_RATIO_MAP, MuAPIImageGenerator

    gen = MuAPIImageGenerator(api_key="test-key")
    payload = gen._legacy_size_payload("a cat", "9:16")

    assert payload == {
        "prompt": "a cat",
        "width": ASPECT_RATIO_MAP["9:16"]["width"],
        "height": ASPECT_RATIO_MAP["9:16"]["height"],
        "num_images": 1,
    }
    assert "size" not in payload


def test_every_mapped_size_is_divisible_by_64():
    from tools.muapi_image_generator import ASPECT_RATIO_MAP

    for ratio, dims in ASPECT_RATIO_MAP.items():
        assert dims["width"] % 64 == 0, f"{ratio} width {dims['width']}"
        assert dims["height"] % 64 == 0, f"{ratio} height {dims['height']}"


def test_the_text_only_fallback_does_not_pretend_to_take_a_reference(caplog):
    """flux-dev-image has no image input, so a reference handed to it is lost.

    Silently dropping it is what made a fallback look character-locked in the
    log while the faces drifted in the delivered frame.
    """
    import logging

    from tools.muapi_image_generator import MuAPIImageGenerator

    gen = MuAPIImageGenerator(api_key="test-key")
    with caplog.at_level(logging.WARNING):
        payload = gen._build_payload(
            "a cat", "16:9", reference_url="https://example.com/ref.png"
        )

    assert "image" not in payload and "image_url" not in payload
    assert "dropped" in caplog.text


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
    in the same session. A source-level check avoids mutating shared state.
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
    import tools.muapi_video_generator as vid_mod

    # Kling must not be sent an aspect_ratio even when the caller supplies one:
    # it derives aspect from the source image and has no such field. This used
    # to be pinned by scanning the module source for the string, which stopped
    # being possible once OTHER endpoints in the chain (Seedance, Veo) started
    # taking one -- the field map is what enforces it now.
    assert "aspect_ratio" not in gen._payload(
        "pan left",
        "https://cdn.example/f.jpg",
        5,
        endpoint=vid_mod.STANDARD_ENDPOINT,
        aspect_ratio="9:16",
    )

    assert vid_mod.endpoint_for_plan("free") == vid_mod.STANDARD_ENDPOINT
    assert vid_mod.endpoint_for_plan("creator") == vid_mod.STANDARD_ENDPOINT
    assert vid_mod.endpoint_for_plan("pro") == vid_mod.PRO_ENDPOINT
    assert vid_mod.endpoint_for_plan("pro") != vid_mod.STANDARD_ENDPOINT
