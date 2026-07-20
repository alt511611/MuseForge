"""Script-approval pause: no video until approve-script."""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_require_script_approval_stops_before_video(monkeypatch, tmp_path):
    """write_script_only runs; continue_from_script / image / video never called."""
    import jobs as jobs_mod
    from interfaces.character import CharacterProfile, DramaScript

    monkeypatch.setattr(jobs_mod, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(jobs_mod, "cleanup_working_dir", lambda *_a, **_k: None)
    monkeypatch.setattr(jobs_mod.job_store, "persist", AsyncMock())
    monkeypatch.setattr(jobs_mod.job_store, "emit", AsyncMock())

    script = DramaScript(
        title="Harbor",
        logline="A goodbye",
        mood="melancholy",
        scenes=["Maya walks the pier.", "Maya leaves."],
        characters=[CharacterProfile(name="Maya", description="30s woman", role="protagonist")],
        setting_location="wooden pier",
        setting_time_of_day="sunset",
        setting_era="present day",
    )

    write_only = AsyncMock(return_value=script)
    continue_from = AsyncMock()
    gen_image = AsyncMock(return_value="https://fake/img.png")
    gen_video = AsyncMock(return_value="https://fake/v.mp4")

    mock_pipeline = MagicMock()
    mock_pipeline.write_script_only = write_only
    mock_pipeline.continue_from_script = continue_from
    mock_pipeline.run = AsyncMock()

    job = jobs_mod.Job(
        id="script-pause-1",
        idea="Maya at the harbor",
        status=jobs_mod.JobStatus.QUEUED,
        demo=True,
        num_scenes=2,
        require_script_approval=True,
    )

    with patch("pipelines.idea2video.Idea2VideoPipeline", return_value=mock_pipeline), \
         patch("tools.muapi_image_generator.MuAPIImageGenerator.generate_image", gen_image), \
         patch(
             "tools.muapi_video_generator.MuAPIVideoGenerator.generate_video_from_image",
             gen_video,
         ):
        await jobs_mod.run_generation_job(job, api_key="k")

    write_only.assert_awaited()
    continue_from.assert_not_awaited()
    mock_pipeline.run.assert_not_awaited()
    gen_image.assert_not_awaited()
    gen_video.assert_not_awaited()
    assert job.status == jobs_mod.JobStatus.AWAITING_SCRIPT_APPROVAL
    assert job.result and job.result.get("script", {}).get("title") == "Harbor"


@pytest.mark.asyncio
async def test_approve_script_continues_with_edited_scene(monkeypatch, tmp_path):
    """continue_from_script receives the user-edited scene text."""
    import jobs as jobs_mod
    from interfaces.character import DramaScript

    monkeypatch.setattr(jobs_mod, "JOBS_DIR", str(tmp_path))
    monkeypatch.setattr(jobs_mod, "cleanup_working_dir", lambda *_a, **_k: None)
    monkeypatch.setattr(jobs_mod.job_store, "persist", AsyncMock())
    monkeypatch.setattr(jobs_mod.job_store, "emit", AsyncMock())

    captured = {}

    async def fake_continue(self, script, **kwargs):
        captured["scenes"] = list(script.scenes)
        captured["title"] = script.title
        return {
            "title": script.title,
            "logline": script.logline,
            "mood": script.mood,
            "video_path": None,
            "video_url": "https://example.com/v.mp4",
            "scene_count": len(script.scenes),
            "duration_estimate": 20,
            "characters": [],
            "portraits": {},
            "scenes": [],
            "director_style": "cinematic_balanced",
            "style": "Cinematic",
            "aspect_ratio": "16:9",
            "demo": True,
            "music_enabled": False,
            "plan": "free",
        }

    job = jobs_mod.Job(
        id="script-approve-1",
        idea="Maya at the harbor",
        status=jobs_mod.JobStatus.AWAITING_SCRIPT_APPROVAL,
        demo=True,
        num_scenes=2,
        require_script_approval=True,
        result={"script": {"title": "Old"}},
    )

    edited = {
        "title": "Edited Harbor",
        "logline": "A goodbye",
        "mood": "melancholy",
        "scenes": ["EDITED SCENE ONE", "Maya leaves."],
        "characters": [{"name": "Maya", "description": "30s woman", "role": "protagonist"}],
        "setting_location": "wooden pier",
        "setting_time_of_day": "sunset",
        "setting_era": "present day",
        "estimated_duration_seconds": 20,
    }

    with patch(
        "pipelines.idea2video.Idea2VideoPipeline.continue_from_script",
        fake_continue,
    ):
        await jobs_mod.run_continue_from_script_job(job, api_key="k", script_data=edited)

    assert captured["scenes"][0] == "EDITED SCENE ONE"
    assert captured["title"] == "Edited Harbor"
    assert job.status == jobs_mod.JobStatus.COMPLETED
    assert job.result.get("script", {}).get("scenes", [None])[0] == "EDITED SCENE ONE"


def test_drama_script_roundtrip_from_approve_payload():
    from interfaces.character import DramaScript

    data = {
        "title": "T",
        "logline": "L",
        "mood": "m",
        "scenes": ["a", "b"],
        "characters": [{"name": "A", "description": "d", "role": "protagonist"}],
        "setting_location": "pier",
        "setting_time_of_day": "night",
        "setting_era": "present day",
        "estimated_duration_seconds": 16,
    }
    s = DramaScript(**data)
    assert s.scenes[0] == "a"
    assert s.setting_location == "pier"
