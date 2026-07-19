"""Pro-plan HD mode selection + fail-safe fallback to standard."""
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_mode_for_plan_pro_uses_professional(monkeypatch):
    monkeypatch.delenv("MUAPI_VIDEO_PRO_MODE", raising=False)
    from tools.muapi_video_generator import mode_for_plan

    assert mode_for_plan("pro") == "professional"
    assert mode_for_plan("creator") == "standard"
    assert mode_for_plan("free") == "standard"
    assert mode_for_plan("") == "standard"


def test_mode_for_plan_honors_env_override(monkeypatch):
    monkeypatch.setenv("MUAPI_VIDEO_PRO_MODE", "pro")
    from tools import muapi_video_generator as vg

    # Re-read via function (reads env each call)
    assert vg.mode_for_plan("pro") == "pro"
    assert vg.mode_for_plan("creator") == "standard"


@pytest.mark.asyncio
async def test_pro_plan_sends_professional_mode(monkeypatch):
    monkeypatch.delenv("MUAPI_VIDEO_PRO_MODE", raising=False)
    from tools.muapi_video_generator import MuAPIVideoGenerator

    gen = MuAPIVideoGenerator(api_key="k", demo=False)
    gen.client.generate = AsyncMock(return_value="https://cdn.example/v.mp4")

    url = await gen.generate_video_from_image(
        prompt="pan left",
        image_url="https://cdn.example/f.jpg",
        plan="pro",
    )
    assert url.endswith("v.mp4")
    payload = gen.client.generate.await_args.args[1]
    assert payload["mode"] == "professional"


@pytest.mark.asyncio
async def test_creator_plan_sends_standard_mode(monkeypatch):
    monkeypatch.delenv("MUAPI_VIDEO_PRO_MODE", raising=False)
    from tools.muapi_video_generator import MuAPIVideoGenerator

    gen = MuAPIVideoGenerator(api_key="k", demo=False)
    gen.client.generate = AsyncMock(return_value="https://cdn.example/v.mp4")

    await gen.generate_video_from_image(
        prompt="pan left",
        image_url="https://cdn.example/f.jpg",
        plan="creator",
    )
    payload = gen.client.generate.await_args.args[1]
    assert payload["mode"] == "standard"


@pytest.mark.asyncio
async def test_mode_422_retries_with_standard_and_succeeds(monkeypatch):
    """If professional is rejected with 422, retry standard — job still succeeds."""
    monkeypatch.delenv("MUAPI_VIDEO_PRO_MODE", raising=False)
    from tools.muapi_client import MuAPIError
    from tools.muapi_video_generator import MuAPIVideoGenerator

    gen = MuAPIVideoGenerator(api_key="k", demo=False)
    calls = []

    async def _generate(endpoint, payload, **kwargs):
        calls.append(payload["mode"])
        if payload["mode"] == "professional":
            raise MuAPIError("MuAPI request failed after 4 attempts: 422 Unprocessable Entity")
        return "https://cdn.example/ok.mp4"

    gen.client.generate = _generate

    url = await gen.generate_video_from_image(
        prompt="pan left",
        image_url="https://cdn.example/f.jpg",
        plan="pro",
    )
    assert url == "https://cdn.example/ok.mp4"
    assert calls == ["professional", "standard"]


@pytest.mark.asyncio
async def test_mode_404_retries_with_standard(monkeypatch):
    monkeypatch.delenv("MUAPI_VIDEO_PRO_MODE", raising=False)
    from tools.muapi_client import MuAPIError
    from tools.muapi_video_generator import MuAPIVideoGenerator

    gen = MuAPIVideoGenerator(api_key="k", demo=False)
    calls = []

    async def _generate(endpoint, payload, **kwargs):
        calls.append(payload["mode"])
        if payload["mode"] != "standard":
            raise MuAPIError("status_code=404 Not Found")
        return "https://cdn.example/ok.mp4"

    gen.client.generate = _generate

    url = await gen.generate_video_from_image(
        prompt="pan left",
        image_url="https://cdn.example/f.jpg",
        plan="pro",
    )
    assert url.endswith("ok.mp4")
    assert calls[0] == "professional"
    assert calls[-1] == "standard"
