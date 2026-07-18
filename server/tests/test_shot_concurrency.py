"""Verify shots are processed concurrently (not sequentially) while
preserving output order -- the fix for '13 minutes and still going'.
"""
import asyncio
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


@pytest.mark.asyncio
async def test_shots_run_concurrently_not_sequentially(monkeypatch, tmp_path):
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    from interfaces.shot import StoryboardShot

    SIMULATED_DELAY = 0.3  # per frame/video call

    async def fake_design_storyboard(self, script, characters, user_requirement, director_style):
        return [
            StoryboardShot(idx=i, visual_desc=f"shot {i}", motion_desc=f"motion {i}")
            for i in range(3)
        ]

    async def fake_generate_image(self, prompt, aspect_ratio):
        await asyncio.sleep(SIMULATED_DELAY)
        return "https://fake.cdn/frame.png"

    async def fake_generate_video(self, prompt, image_url, duration, aspect_ratio):
        await asyncio.sleep(SIMULATED_DELAY)
        return "https://fake.cdn/video.mp4"

    async def fake_download_video(url, path):
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    monkeypatch.setattr(
        "agents.storyboard_artist.StoryboardArtist.design_storyboard", fake_design_storyboard
    )
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image", fake_generate_image
    )
    monkeypatch.setattr(
        "tools.muapi_video_generator.MuAPIVideoGenerator.generate_video_from_image",
        fake_generate_video,
    )
    monkeypatch.setattr("pipelines.script2video.download_video", fake_download_video)

    async def fake_concatenate_videos(paths, out_path):
        with open(out_path, "wb") as f:
            f.write(b"fake concatenated")
        return out_path

    monkeypatch.setattr("pipelines.script2video.concatenate_videos", fake_concatenate_videos)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [CharacterInScene(idx=0, name="Alex", static_features="a person", is_visible=True)]

    start = time.monotonic()
    result = await pipeline.run(
        script="test script",
        characters=characters,
        working_dir=str(tmp_path),
    )
    elapsed = time.monotonic() - start

    # 3 shots x 2 sequential calls each (frame + video) x 0.3s would be
    # 1.8s if fully sequential. With concurrency=2 (default), it should
    # take meaningfully less -- generously bounding at 1.3s to avoid CI
    # flakiness while still catching a regression to full sequential.
    assert elapsed < 1.3, f"Shots don't appear to run concurrently (took {elapsed:.2f}s)"

    # Order must still be correct regardless of completion order.
    shots = result["shots"]
    assert [s["idx"] for s in shots] == [0, 1, 2]
