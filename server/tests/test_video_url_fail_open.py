"""Fail-open video_url must never expose a raw disk path to the client."""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_storage_fail_open_video_url_is_api_endpoint(tmp_path, monkeypatch):
    """When Storage upload returns a local path, video_url is /api/jobs/{id}/video."""
    monkeypatch.delenv("MUSEFORGE_DEMO", raising=False)

    from pipelines.idea2video import Idea2VideoPipeline

    working_dir = tmp_path / "326c6f17-367"
    working_dir.mkdir()
    final_file = working_dir / "drama_with_music.mp4"
    final_file.write_bytes(b"fake-mp4")

    # Minimal DramaScript-like object
    scene = MagicMock()
    script = MagicMock()
    script.title = "Test"
    script.logline = "logline"
    script.mood = "cinematic"
    script.estimated_duration_seconds = 10
    script.characters = []
    script.scenes = [scene]

    pipeline = Idea2VideoPipeline(api_key="test-key", demo=False)
    pipeline.screenwriter.write_script = AsyncMock(return_value=script)
    pipeline._lock_character_portraits = AsyncMock(return_value={})

    scene_path = str(working_dir / "scene_0.mp4")
    with open(scene_path, "wb") as f:
        f.write(b"scene")

    pipeline.script2video.run = AsyncMock(
        return_value={"path": scene_path, "shots": [{"video_url": "https://example.com/shot.mp4"}]}
    )
    pipeline._assemble_final_drama = AsyncMock(return_value=str(final_file))

    async def _fake_upload(path, job_id):
        # Fail-open: return the local path unchanged (Storage unavailable)
        assert job_id == "326c6f17-367"
        return path

    with patch("tools.supabase_storage.upload_video", side_effect=_fake_upload):
        result = await pipeline.run(
            idea="A quiet story",
            working_dir=str(working_dir),
            num_scenes=1,
            plan="free",
        )

    assert result["video_url"].startswith("/api/jobs/")
    assert result["video_url"] == "/api/jobs/326c6f17-367/video"
    assert not result["video_url"].startswith("/tmp/")
    assert "/museforge_jobs/" not in result["video_url"]
