"""Verify the QA reject-and-regenerate loop: a frame that fails
character/setting QA gets regenerated (up to MUSEFORGE_QA_MAX_RETRIES
times) BEFORE the expensive video-animation step runs, and the job
always completes (fail-open) even if QA never passes.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


@pytest.mark.asyncio
async def test_frame_regenerated_when_qa_fails_then_succeeds(monkeypatch, tmp_path):
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    from interfaces.shot import StoryboardShot

    monkeypatch.setenv("MUSEFORGE_CHARACTER_QA_ENABLED", "true")
    monkeypatch.setenv("MUSEFORGE_QA_MAX_RETRIES", "2")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")

    image_calls = {"n": 0}
    qa_calls = {"n": 0}

    async def fake_design_storyboard(self, script, characters, user_requirement, director_style, **_kw):
        return [StoryboardShot(idx=0, visual_desc="Maria at the window", motion_desc="turns")]

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        image_calls["n"] += 1
        return f"https://fake.cdn/frame_attempt_{image_calls['n']}.png"

    async def fake_generate_video(self, prompt, image_url, duration, aspect_ratio="16:9", plan="free", is_cancelled=None):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    async def fake_verify_frame(frame_url, expected_character_desc, expected_setting, anthropic_api_key):
        qa_calls["n"] += 1
        # Fail on the first attempt, succeed on the second.
        return {"character_ok": qa_calls["n"] >= 2, "setting_ok": True}

    import agents.storyboard_artist as sb_mod
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod
    import pipelines.script2video as s2v_mod

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_generate_image_with_reference)
    monkeypatch.setattr(vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)
    monkeypatch.setattr(s2v_mod, "verify_frame", fake_verify_frame)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [CharacterInScene(idx=0, name="Maria", static_features="a painter", is_visible=True)]
    portraits = {"Maria": "https://fake.cdn/maria_portrait.png"}

    result = await pipeline.run(
        script="test script", characters=characters, working_dir=str(tmp_path),
        character_portraits=portraits,
    )

    assert qa_calls["n"] == 2, f"Expected QA to run exactly twice (fail then pass), ran {qa_calls['n']}"
    assert image_calls["n"] == 2, f"Expected frame to be regenerated once after QA failure, got {image_calls['n']} calls"
    assert result["shots"][0].get("character_qa_warning") is not True


@pytest.mark.asyncio
async def test_job_completes_even_if_qa_never_passes(monkeypatch, tmp_path):
    """Fail-open: exhausting all retries must NOT fail the job -- it must
    proceed with the last frame and simply flag the warning."""
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    from interfaces.shot import StoryboardShot

    monkeypatch.setenv("MUSEFORGE_CHARACTER_QA_ENABLED", "true")
    monkeypatch.setenv("MUSEFORGE_QA_MAX_RETRIES", "2")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")

    image_calls = {"n": 0}

    async def fake_design_storyboard(self, script, characters, user_requirement, director_style, **_kw):
        return [StoryboardShot(idx=0, visual_desc="Maria at the window", motion_desc="turns")]

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        image_calls["n"] += 1
        return f"https://fake.cdn/frame_attempt_{image_calls['n']}.png"

    async def fake_generate_video(self, prompt, image_url, duration, aspect_ratio="16:9", plan="free", is_cancelled=None):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    async def fake_verify_frame_always_fails(frame_url, expected_character_desc, expected_setting, anthropic_api_key):
        return {"character_ok": False, "setting_ok": True}

    import agents.storyboard_artist as sb_mod
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod
    import pipelines.script2video as s2v_mod

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_generate_image_with_reference)
    monkeypatch.setattr(vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)
    monkeypatch.setattr(s2v_mod, "verify_frame", fake_verify_frame_always_fails)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [CharacterInScene(idx=0, name="Maria", static_features="a painter", is_visible=True)]
    portraits = {"Maria": "https://fake.cdn/maria_portrait.png"}

    result = await pipeline.run(
        script="test script", characters=characters, working_dir=str(tmp_path),
        character_portraits=portraits,
    )

    # 1 initial + 2 retries = 3 total attempts (MUSEFORGE_QA_MAX_RETRIES=2)
    assert image_calls["n"] == 3
    assert result["shots"][0]["character_qa_warning"] is True
    assert result["path"] is not None  # job still completed, never failed


@pytest.mark.asyncio
async def test_no_retries_or_extra_calls_when_qa_disabled(monkeypatch, tmp_path):
    """QA disabled (the default) must add zero extra calls/behavior."""
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    from interfaces.shot import StoryboardShot

    monkeypatch.delenv("MUSEFORGE_CHARACTER_QA_ENABLED", raising=False)

    image_calls = {"n": 0}
    verify_calls = {"n": 0}

    async def fake_design_storyboard(self, script, characters, user_requirement, director_style, **_kw):
        return [StoryboardShot(idx=0, visual_desc="Maria at the window", motion_desc="turns")]

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        image_calls["n"] += 1
        return "https://fake.cdn/frame.png"

    async def fake_generate_video(self, prompt, image_url, duration, aspect_ratio="16:9", plan="free", is_cancelled=None):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    async def fake_verify_frame(*a, **kw):
        verify_calls["n"] += 1
        return {"character_ok": False, "setting_ok": False}

    import agents.storyboard_artist as sb_mod
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod
    import pipelines.script2video as s2v_mod

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_generate_image_with_reference)
    monkeypatch.setattr(vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)
    monkeypatch.setattr(s2v_mod, "verify_frame", fake_verify_frame)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [CharacterInScene(idx=0, name="Maria", static_features="a painter", is_visible=True)]
    portraits = {"Maria": "https://fake.cdn/maria_portrait.png"}

    result = await pipeline.run(
        script="test script", characters=characters, working_dir=str(tmp_path),
        character_portraits=portraits,
    )

    assert image_calls["n"] == 1, "QA disabled must not trigger any retry"
    assert verify_calls["n"] == 0, "QA disabled must not call verify_frame at all"
