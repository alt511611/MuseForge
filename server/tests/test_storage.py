"""Supabase Storage upload tests (fully mocked — no real network)."""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def local_mp4(tmp_path):
    p = tmp_path / "final.mp4"
    p.write_bytes(b"fake-mp4-bytes")
    return str(p)


@pytest.mark.asyncio
async def test_upload_returns_signed_url_on_success(local_mp4, monkeypatch):
    monkeypatch.delenv("MUSEFORGE_DEMO", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service_key")

    import tools.supabase_storage as storage

    monkeypatch.setattr(storage, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(storage, "SUPABASE_SERVICE_KEY", "service_key")

    upload_resp = MagicMock()
    upload_resp.raise_for_status = MagicMock()
    sign_resp = MagicMock()
    sign_resp.raise_for_status = MagicMock()
    sign_resp.json.return_value = {
        "signedURL": "/object/sign/videos/job123.mp4?token=abc"
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=[upload_resp, sign_resp])

    with patch("tools.supabase_storage.httpx.AsyncClient", return_value=mock_client):
        url = await storage.upload_video(local_mp4, "job123")

    assert url.startswith("https://proj.supabase.co/storage/v1/object/sign/")
    assert "job123.mp4" in url
    assert mock_client.post.await_count == 2


@pytest.mark.asyncio
async def test_demo_mode_makes_no_network_calls(local_mp4, monkeypatch):
    monkeypatch.setenv("MUSEFORGE_DEMO", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service_key")

    import tools.supabase_storage as storage

    monkeypatch.setattr(storage, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(storage, "SUPABASE_SERVICE_KEY", "service_key")

    with patch("tools.supabase_storage.httpx.AsyncClient") as client_cls:
        url = await storage.upload_video(local_mp4, "job-demo")
        client_cls.assert_not_called()

    assert url == local_mp4


@pytest.mark.asyncio
async def test_upload_failure_fail_open_keeps_local_path(local_mp4, monkeypatch):
    monkeypatch.delenv("MUSEFORGE_DEMO", raising=False)

    import tools.supabase_storage as storage

    monkeypatch.setattr(storage, "SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setattr(storage, "SUPABASE_SERVICE_KEY", "service_key")

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("network down"))

    with patch("tools.supabase_storage.httpx.AsyncClient", return_value=mock_client):
        url = await storage.upload_video(local_mp4, "job-fail")

    assert url == local_mp4
    assert Path(local_mp4).is_file()


@pytest.mark.asyncio
async def test_missing_supabase_env_skips_network(local_mp4, monkeypatch):
    monkeypatch.delenv("MUSEFORGE_DEMO", raising=False)

    import tools.supabase_storage as storage

    monkeypatch.setattr(storage, "SUPABASE_URL", "")
    monkeypatch.setattr(storage, "SUPABASE_SERVICE_KEY", "")

    with patch("tools.supabase_storage.httpx.AsyncClient") as client_cls:
        url = await storage.upload_video(local_mp4, "job-local")
        client_cls.assert_not_called()

    assert url == local_mp4
