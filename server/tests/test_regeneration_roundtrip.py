"""End-to-end handoff: a real render, then a real retake of one of its scenes.

The unit tests for archiving and for regeneration each mock the other side, so
they would both still pass if the two disagreed about the shape of what gets
stored. This runs the actual pipeline to completion and then re-shoots scene 1
from nothing but the result dict it produced — which is exactly what the API
does, a request later, with the job row round-tripped through Supabase.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterProfile, DramaScript  # noqa: E402


class FakeShot:
    def __init__(self, desc="Kemal pours the coffee."):
        self.idx = 0
        self.visual_desc = desc
        self.motion_desc = "slow push-in"
        self.audio_desc = "ambient"
        self.shot_type = "medium shot"
        self.camera_movement = "static"
        self.lens = "50mm"
        self.duration_seconds = 5.0
        self.frame_url = None
        self.video_url = None

    def model_dump(self, **kwargs):
        return {
            "idx": self.idx,
            "visual_desc": self.visual_desc,
            "motion_desc": self.motion_desc,
            "duration_seconds": self.duration_seconds,
            "frame_url": self.frame_url,
            "video_url": self.video_url,
        }


@pytest.fixture
def fake_providers(monkeypatch):
    """Stub every paid call; keep all real orchestration, file handling and
    result-dict plumbing."""
    calls = {"frames": 0, "videos": 0}

    async def fake_generate_image(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        return "https://fake.cdn/plate.png" if "Empty location plate" in prompt else "https://fake.cdn/portrait.png"

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        calls["frames"] += 1
        return f"https://fake.cdn/frame_{calls['frames']}.png"

    async def fake_generate_video(self, prompt, image_url, duration=5, aspect_ratio="16:9", plan="free", is_cancelled=None):
        calls["videos"] += 1
        return f"https://fake.cdn/clip_{calls['videos']}.mp4"

    async def fake_design_storyboard(self, script, characters, *a, **kw):
        return [FakeShot()]

    async def fake_download_video(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(f"bytes for {url}".encode())
        return path

    async def fake_concatenate_videos(paths, out_path):
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        # Record the ORDER of what went in — that is what a splice must get
        # right. Full paths, because every scene's clip is named shot_0.mp4
        # inside its own directory; only the directory tells them apart.
        with open(out_path, "w") as f:
            json.dump(list(paths), f)
        return out_path

    async def fake_add_background_music(video_path, output_path, *a, **kw):
        with open(output_path, "w") as f:
            f.write(open(video_path).read())
        return output_path

    async def fake_apply_color_grade(video_path, output_path, *a, **kw):
        with open(output_path, "w") as f:
            f.write(open(video_path).read())
        return output_path

    import agents.storyboard_artist as storyboard_mod
    import pipelines.idea2video as idea2video_mod
    import pipelines.script2video as script2video_mod
    import tools.muapi_image_generator as image_mod
    import tools.muapi_video_generator as video_mod

    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image", fake_generate_image)
    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_generate_image_with_reference)
    monkeypatch.setattr(video_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video)
    monkeypatch.setattr(storyboard_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(script2video_mod, "download_video", fake_download_video)
    monkeypatch.setattr(idea2video_mod, "download_video", fake_download_video)
    monkeypatch.setattr(script2video_mod, "concatenate_videos", fake_concatenate_videos)
    monkeypatch.setattr(idea2video_mod, "concatenate_videos", fake_concatenate_videos)
    monkeypatch.setattr(idea2video_mod, "add_background_music", fake_add_background_music)
    monkeypatch.setattr(idea2video_mod, "apply_color_grade", fake_apply_color_grade)
    return calls


def _script():
    return DramaScript(
        title="Meridyen",
        logline="A coffee master hands down his craft.",
        mood="warm",
        estimated_duration_seconds=24,
        setting_location="stone-walled coffeehouse",
        setting_time_of_day="early morning",
        characters=[CharacterProfile(name="Kemal", description="70s man", role="protagonist")],
        scenes=[
            {"action": "Kemal lights the stove.", "tension": 3},
            {"action": "Kemal pours the coffee.", "tension": 7},
            {"action": "Kemal sets the cup down.", "tension": 5},
        ],
    )


@pytest.mark.asyncio
async def test_render_then_retake_scene_one(fake_providers, tmp_path):
    import pipelines.idea2video as idea2video_mod

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    working_dir = str(tmp_path / "job-abc")

    result = await pipeline.continue_from_script(
        script=_script(), working_dir=working_dir, aspect_ratio="16:9"
    )

    # --- what the render must have left behind for a retake to be possible ---
    assert result["_render_state"]["scene_durations"], "The retake needs the second budget"
    scenes = result["scenes"]
    assert [s["clip_index"] for s in scenes] == [0, 1, 2]
    for scene in scenes:
        assert scene.get("clip_path") and os.path.isfile(scene["clip_path"]), (
            "Every scene clip must be individually recoverable, not only the master"
        )

    frames_after_render = fake_providers["frames"]

    # --- the retake, from the result dict alone ---
    new_result = await pipeline.regenerate_scene(
        previous_result=result,
        scene_index=1,
        working_dir=working_dir,
        director_note="Warmer light on his hands.",
    )

    assert fake_providers["frames"] == frames_after_render + 1, (
        "Exactly one scene may be re-rendered — a retake that re-runs the "
        "whole drama is the thing this feature exists to avoid"
    )

    spliced = json.load(open(new_result["video_path"]))
    assert len(spliced) == 3, "The master must still contain every scene"
    assert "take2" in spliced[1], "Scene 1 must be the NEW take"
    assert "take2" not in spliced[0] and "take2" not in spliced[2], (
        "Scenes the user kept must be the original files, byte for byte"
    )
    assert new_result["scenes"][1]["take"] == 2

    # A second retake of a DIFFERENT scene still finds everything it needs,
    # including the scene that was already replaced once.
    newer = await pipeline.regenerate_scene(
        previous_result=new_result, scene_index=2, working_dir=working_dir
    )
    spliced = json.load(open(newer["video_path"]))
    assert "take2" in spliced[1], "The earlier retake must survive a later one"
    assert "take2" in spliced[2]
