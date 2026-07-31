"""Pro/Standard endpoint selection + fail-safe fallback to Standard."""
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_endpoint_for_plan_pro_vs_standard(monkeypatch):
    monkeypatch.delenv("MUAPI_VIDEO_MODEL_PRO", raising=False)
    monkeypatch.delenv("MUAPI_VIDEO_MODEL_STANDARD", raising=False)
    from tools import muapi_video_generator as vg

    assert vg.endpoint_for_plan("pro") == "kling-v3.0-pro-image-to-video"
    assert vg.endpoint_for_plan("creator") == "kling-v3.0-standard-image-to-video"
    assert vg.endpoint_for_plan("free") == "kling-v3.0-standard-image-to-video"
    assert vg.endpoint_for_plan("") == "kling-v3.0-standard-image-to-video"


def test_endpoint_for_plan_honors_env_override(monkeypatch):
    monkeypatch.setenv("MUAPI_VIDEO_MODEL_PRO", "custom-pro-endpoint")
    monkeypatch.setenv("MUAPI_VIDEO_MODEL_STANDARD", "custom-std-endpoint")
    from tools import muapi_video_generator as vg

    # Module-level constants are set at import; re-read via os.environ in
    # endpoint_for_plan would require reload. Instead patch the module attrs
    # the same way production env overrides work after process start.
    monkeypatch.setattr(vg, "PRO_ENDPOINT", "custom-pro-endpoint")
    monkeypatch.setattr(vg, "STANDARD_ENDPOINT", "custom-std-endpoint")
    assert vg.endpoint_for_plan("pro") == "custom-pro-endpoint"
    assert vg.endpoint_for_plan("creator") == "custom-std-endpoint"


@pytest.mark.asyncio
async def test_pro_plan_uses_pro_endpoint():
    from tools.muapi_video_generator import MuAPIVideoGenerator

    gen = MuAPIVideoGenerator(api_key="k", demo=False)
    gen.client.generate = AsyncMock(return_value="https://cdn.example/v.mp4")

    url = await gen.generate_video_from_image(
        prompt="pan left",
        image_url="https://cdn.example/f.jpg",
        plan="pro",
    )
    assert url.endswith("v.mp4")
    endpoint = gen.client.generate.await_args.args[0]
    payload = gen.client.generate.await_args.args[1]
    assert endpoint == "kling-v3.0-pro-image-to-video"
    assert "mode" not in payload
    # Native Kling audio is OFF by default: the assembly step drops it with
    # -an and lays the real score/dialogue over a silent picture, so
    # requesting it only burned generation time on an inaudible track.
    assert payload["generate_audio"] is False
    assert payload["duration"] == 5


@pytest.mark.asyncio
async def test_native_audio_off_by_default_and_opt_in(monkeypatch):
    from tools.muapi_video_generator import (
        MuAPIVideoGenerator,
        is_native_audio_enabled,
    )

    monkeypatch.delenv("MUSEFORGE_KLING_NATIVE_AUDIO", raising=False)
    assert is_native_audio_enabled() is False

    monkeypatch.setenv("MUSEFORGE_KLING_NATIVE_AUDIO", "1")
    assert is_native_audio_enabled() is True

    gen = MuAPIVideoGenerator(api_key="k", demo=False)
    gen.client.generate = AsyncMock(return_value="https://cdn.example/v.mp4")
    await gen.generate_video_from_image(
        prompt="pan", image_url="https://cdn.example/f.jpg", plan="pro"
    )
    assert gen.client.generate.await_args.args[1]["generate_audio"] is True


@pytest.mark.asyncio
async def test_assembly_discards_native_audio():
    """The reason native audio defaults off -- concat strips it outright."""
    import inspect

    from pipelines.script2video import concatenate_videos

    assert '"-an"' in inspect.getsource(concatenate_videos)


@pytest.mark.asyncio
async def test_creator_plan_uses_standard_endpoint():
    from tools.muapi_video_generator import MuAPIVideoGenerator

    gen = MuAPIVideoGenerator(api_key="k", demo=False)
    gen.client.generate = AsyncMock(return_value="https://cdn.example/v.mp4")

    await gen.generate_video_from_image(
        prompt="pan left",
        image_url="https://cdn.example/f.jpg",
        plan="creator",
    )
    endpoint = gen.client.generate.await_args.args[0]
    payload = gen.client.generate.await_args.args[1]
    assert endpoint == "kling-v3.0-standard-image-to-video"
    assert "mode" not in payload


@pytest.mark.asyncio
async def test_pro_endpoint_422_retries_with_standard_and_succeeds():
    """If Pro endpoint is rejected with 422, retry Standard — job still succeeds."""
    from tools.muapi_client import MuAPIError
    from tools.muapi_video_generator import MuAPIVideoGenerator

    gen = MuAPIVideoGenerator(api_key="k", demo=False)
    calls = []

    async def _generate(endpoint, payload, **kwargs):
        calls.append(endpoint)
        if endpoint == "kling-v3.0-pro-image-to-video":
            raise MuAPIError("MuAPI request failed after 4 attempts: 422 Unprocessable Entity")
        return "https://cdn.example/ok.mp4"

    gen.client.generate = _generate

    url = await gen.generate_video_from_image(
        prompt="pan left",
        image_url="https://cdn.example/f.jpg",
        plan="pro",
    )
    assert url == "https://cdn.example/ok.mp4"
    assert calls == [
        "kling-v3.0-pro-image-to-video",
        "kling-v3.0-standard-image-to-video",
    ]


@pytest.mark.asyncio
async def test_pro_endpoint_404_retries_with_standard():
    from tools.muapi_client import MuAPIError
    from tools.muapi_video_generator import MuAPIVideoGenerator

    gen = MuAPIVideoGenerator(api_key="k", demo=False)
    calls = []

    async def _generate(endpoint, payload, **kwargs):
        calls.append(endpoint)
        if endpoint != "kling-v3.0-standard-image-to-video":
            raise MuAPIError("status_code=404 Not Found")
        return "https://cdn.example/ok.mp4"

    gen.client.generate = _generate

    url = await gen.generate_video_from_image(
        prompt="pan left",
        image_url="https://cdn.example/f.jpg",
        plan="pro",
    )
    assert url.endswith("ok.mp4")
    assert calls[0] == "kling-v3.0-pro-image-to-video"
    assert calls[-1] == "kling-v3.0-standard-image-to-video"
