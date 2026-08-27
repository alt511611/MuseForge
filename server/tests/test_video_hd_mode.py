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
async def test_assembly_discards_native_audio(tmp_path):
    """The reason native audio defaults off -- concat strips it outright.

    Asserted on the joined file rather than on the source text of the function
    that writes it: the ffmpeg invocation has already moved once, into the
    demuxer helper and its timescale-normalising retry, and a grep for "-an"
    would have failed that refactor while the behaviour it guards was intact.
    """
    import subprocess

    from pipelines.script2video import _ffmpeg_binary, concatenate_videos

    ffmpeg = _ffmpeg_binary()
    clips = []
    for index in range(2):
        path = str(tmp_path / f"withaudio_{index}.mp4")
        subprocess.run(
            [
                ffmpeg, "-y", "-v", "error",
                "-f", "lavfi", "-i", "testsrc=size=160x90:rate=24:duration=0.5",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=0.5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", path,
            ],
            check=True,
        )
        clips.append(path)

    output = str(tmp_path / "joined.mp4")
    await concatenate_videos(clips, output)

    from moviepy import VideoFileClip

    with VideoFileClip(clips[0]) as source:
        assert source.audio is not None, "fixture should carry audio"
    with VideoFileClip(output) as joined:
        assert joined.audio is None


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
