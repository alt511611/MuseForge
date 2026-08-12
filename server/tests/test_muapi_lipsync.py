"""The MuAPI lip-sync backend: payload shape, upload, and fail-open.

This is the call that used to force a fal.ai key on a deployment where
everything else already ran on MuAPI.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import tools.muapi_lipsync as lipsync_mod  # noqa: E402
from tools.muapi_client import MuAPIError  # noqa: E402


@pytest.mark.asyncio
async def test_payload_is_exactly_what_the_endpoint_declares(monkeypatch):
    """sync-lipsync takes video_url and audio_url and nothing else. Sending
    fal's `model`/`sync_mode` alongside would be an undeclared field, which
    MuAPI answers with a 422 -- and lip sync fails open, so it would simply
    stop happening with no error the user ever sees."""
    seen = {}

    async def fake_generate(self, endpoint, payload, **kwargs):
        seen["endpoint"] = endpoint
        seen["payload"] = dict(payload)
        return "https://cdn/synced.mp4"

    monkeypatch.setattr("tools.muapi_client.MuAPIClient.generate", fake_generate)

    url = await lipsync_mod.MuAPILipsync("k").sync(
        "https://cdn/scene.mp4", "https://cdn/voice.mp3"
    )
    assert url == "https://cdn/synced.mp4"
    assert seen["endpoint"] == "sync-lipsync"
    assert seen["payload"] == {
        "video_url": "https://cdn/scene.mp4",
        "audio_url": "https://cdn/voice.mp3",
    }


@pytest.mark.asyncio
async def test_a_local_clip_is_uploaded_first(monkeypatch, tmp_path):
    """The endpoint fetches the video by URL, and the clip to sync is the
    scene just rendered into the working directory."""
    clip = tmp_path / "scene_0.mp4"
    clip.write_bytes(b"bytes")

    uploaded = []

    async def fake_upload(path, api_key):
        uploaded.append(path)
        return "https://muapi.storage/scene_0.mp4"

    async def fake_generate(self, endpoint, payload, **kwargs):
        assert payload["video_url"] == "https://muapi.storage/scene_0.mp4"
        return "https://cdn/synced.mp4"

    monkeypatch.setattr("tools.muapi_uploader.upload_local_file", fake_upload)
    monkeypatch.setattr("tools.muapi_client.MuAPIClient.generate", fake_generate)

    assert await lipsync_mod.MuAPILipsync("k").sync(str(clip), "https://cdn/v.mp3")
    assert uploaded == [str(clip)]


@pytest.mark.asyncio
async def test_a_failed_upload_keeps_the_unsynced_take(monkeypatch, tmp_path):
    clip = tmp_path / "scene_0.mp4"
    clip.write_bytes(b"bytes")

    async def fake_upload(path, api_key):
        return None

    async def fake_generate(self, endpoint, payload, **kwargs):
        raise AssertionError("must not reach the API with no video URL")

    monkeypatch.setattr("tools.muapi_uploader.upload_local_file", fake_upload)
    monkeypatch.setattr("tools.muapi_client.MuAPIClient.generate", fake_generate)

    assert await lipsync_mod.MuAPILipsync("k").sync(str(clip), "https://cdn/v.mp3") is None


@pytest.mark.asyncio
async def test_a_provider_error_never_fails_the_job(monkeypatch):
    """Lip sync is polish running after the expensive generation is already
    paid for. Losing it must cost mouth accuracy, never the drama."""

    async def fake_generate(self, endpoint, payload, **kwargs):
        raise MuAPIError("status_code=500 upstream exploded")

    monkeypatch.setattr("tools.muapi_client.MuAPIClient.generate", fake_generate)

    assert await lipsync_mod.MuAPILipsync("k").sync(
        "https://cdn/scene.mp4", "https://cdn/v.mp3"
    ) is None


@pytest.mark.asyncio
async def test_nothing_is_attempted_without_a_key_or_in_demo(monkeypatch):
    monkeypatch.setenv("MUAPI_KEY", "")
    assert lipsync_mod.MuAPILipsync("").available() is False
    assert lipsync_mod.MuAPILipsync("k", demo=True).available() is False
    assert await lipsync_mod.MuAPILipsync("", demo=True).sync("v", "a") is None


def test_the_enabled_flag_has_one_definition():
    """Two copies would eventually disagree about which spellings count."""
    import tools.falai_lipsync as fal_mod

    assert fal_mod.is_lipsync_enabled is lipsync_mod.is_lipsync_enabled


def test_enabled_is_opt_in(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_LIPSYNC_ENABLED", raising=False)
    assert lipsync_mod.is_lipsync_enabled() is False
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "true")
    assert lipsync_mod.is_lipsync_enabled() is True
