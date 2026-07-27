"""Duration helpers for MuAPI Kling video endpoints."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


def test_nearest_valid_duration_rounds_correctly():
    """Legacy 5/10 enum helper kept for callers that still need it."""
    from tools.muapi_video_generator import nearest_valid_duration

    assert nearest_valid_duration(14) == 10  # the exact reported bug
    assert nearest_valid_duration(5) == 5
    assert nearest_valid_duration(10) == 10
    assert nearest_valid_duration(7) == 5
    assert nearest_valid_duration(8) == 10
    assert nearest_valid_duration(3) == 5
    assert nearest_valid_duration(20) == 10
    assert nearest_valid_duration(None) == 5  # never crash on bad input
    assert nearest_valid_duration("not a number") == 5


def test_clamp_duration_allows_3_to_15():
    from tools.muapi_video_generator import clamp_duration

    assert clamp_duration(14) == 14
    assert clamp_duration(5) == 5
    assert clamp_duration(3) == 3
    assert clamp_duration(15) == 15
    assert clamp_duration(1) == 3
    assert clamp_duration(30) == 15
    assert clamp_duration(None) == 5
    assert clamp_duration("not a number") == 5


@pytest.mark.asyncio
async def test_generate_video_from_image_clamps_duration(monkeypatch):
    from tools.muapi_video_generator import MuAPIVideoGenerator

    captured_payload = {}

    async def fake_generate(self, endpoint, payload, **kwargs):
        captured_payload.update(payload)
        return "https://fake.cdn/video.mp4"

    monkeypatch.setattr("tools.muapi_client.MuAPIClient.generate", fake_generate)

    gen = MuAPIVideoGenerator(api_key="test-key", demo=False)
    await gen.generate_video_from_image(
        prompt="test", image_url="https://x.com/i.png", duration=14
    )

    assert captured_payload["duration"] == 14
    assert captured_payload["generate_audio"] is True
    assert "mode" not in captured_payload
