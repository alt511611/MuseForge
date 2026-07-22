"""
Regression tests for the MuseForge cinema pipeline invariants:

  1) character-consistency lock — the portrait is generated once per drama,
     not once per scene;
  2) director_style propagation into the storyboard artist;
  3) background music added exactly once, on the final concatenated video;
  4) demo mode runs the full pipeline offline with placeholder assets.

All MuAPI/Claude network calls are monkey-patched — no API key or network
access required.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.camera import DIRECTOR_STYLES, get_director_style  # noqa: E402
from interfaces.character import CharacterInScene, CharacterProfile, DramaScript  # noqa: E402


class FakeShot:
    def __init__(self, idx):
        self.idx = idx
        self.visual_desc = "Maya walks through a corridor."
        self.motion_desc = "steady tracking shot"
        self.audio_desc = "ambient hum"
        self.shot_type = "medium shot"
        self.camera_movement = "slow push-in"
        self.lens = "50mm"
        self.duration_seconds = 5.0
        self.frame_url = None
        self.video_url = None

    def model_dump(self, **kwargs):
        return {
            "idx": self.idx,
            "visual_desc": self.visual_desc,
            "motion_desc": self.motion_desc,
            "audio_desc": self.audio_desc,
            "shot_type": self.shot_type,
            "camera_movement": self.camera_movement,
            "lens": self.lens,
            "duration_seconds": self.duration_seconds,
            "frame_url": self.frame_url,
            "video_url": self.video_url,
        }


def test_director_style_presets():
    assert "slow_cinematic" in DIRECTOR_STYLES
    preset = get_director_style("slow_cinematic")
    assert "slow" in preset.storyboard_guidance.lower()
    assert get_director_style("does_not_exist").label  # falls back, never raises


@pytest.mark.asyncio
async def test_pipeline_invariants(monkeypatch):
    """Drive the full idea->video pipeline once and assert the three invariants."""
    portrait_calls = []
    storyboard_calls = []
    music_calls = []

    async def fake_generate_image(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        portrait_calls.append(prompt)
        return f"https://fake.cdn/portrait_{len(portrait_calls)}.png"

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        return f"https://fake.cdn/frame_from_{reference_url.split('/')[-1]}"

    async def fake_generate_video_from_image(
        self, prompt, image_url, duration=5, aspect_ratio="16:9", plan="free", is_cancelled=None
    ):
        return "https://fake.cdn/video.mp4"

    async def fake_design_storyboard(self, script, characters, user_requirement="", director_style="cinematic_balanced", **_kwargs):
        storyboard_calls.append(director_style)
        return [FakeShot(0)]

    async def fake_write_script(self, idea, style="Cinematic", num_scenes=3, user_requirement="", preset_characters=None):
        return DramaScript(
            title="Maya",
            logline=idea,
            mood="cinematic",
            estimated_duration_seconds=24,
            characters=[CharacterProfile(name="Maya", description="30s woman, dark hair", role="protagonist")],
            scenes=[f"Scene {i}: Maya walks." for i in range(num_scenes)],
        )

    async def fake_download_video(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake video bytes")
        return path

    async def fake_concatenate_videos(paths, out_path):
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(b"fake concatenated video")
        return out_path

    async def fake_add_background_music(video_path, output_path, music_url=None):
        music_calls.append(output_path)
        with open(output_path, "wb") as f:
            f.write(b"fake video with music")
        return output_path

    import agents.screenwriter as screenwriter_mod
    import agents.storyboard_artist as storyboard_mod
    import pipelines.idea2video as idea2video_mod
    import pipelines.script2video as script2video_mod
    import tools.muapi_image_generator as image_mod
    import tools.muapi_video_generator as video_mod

    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image", fake_generate_image)
    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_generate_image_with_reference)
    monkeypatch.setattr(video_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video_from_image)
    monkeypatch.setattr(storyboard_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(screenwriter_mod.ScreenwriterAgent, "write_script", fake_write_script)
    monkeypatch.setattr(script2video_mod, "download_video", fake_download_video)
    monkeypatch.setattr(script2video_mod, "concatenate_videos", fake_concatenate_videos)
    monkeypatch.setattr(idea2video_mod, "concatenate_videos", fake_concatenate_videos)
    monkeypatch.setattr(idea2video_mod, "add_background_music", fake_add_background_music)

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    result = await pipeline.run(
        idea="Maya walks through the frozen city.",
        style="Cinematic",
        director_style="slow_cinematic",
        num_scenes=3,
        working_dir="/tmp/_museforge_test_drama",
    )

    # 1) Character portrait locked exactly once for the whole drama.
    assert len(portrait_calls) == 1, f"Portrait regenerated across scenes: {len(portrait_calls)}"

    # 2) director_style propagated to the storyboard artist on every scene.
    assert storyboard_calls == ["slow_cinematic"] * 3, storyboard_calls

    # 3) Background music added exactly once, on the final concatenated drama.
    assert len(music_calls) == 1, f"Music added {len(music_calls)} times, expected 1"

    assert result["scene_count"] == 3
    assert result["video_path"] and os.path.exists(result["video_path"])


@pytest.mark.asyncio
async def test_scene_pipeline_returns_shots(monkeypatch):
    """A single scene returns a downloadable path plus per-shot metadata."""
    import pipelines.script2video as script2video_mod
    import tools.muapi_image_generator as image_mod
    import tools.muapi_video_generator as video_mod
    import agents.storyboard_artist as storyboard_mod

    async def fake_img(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        return "https://fake.cdn/img.png"

    async def fake_img_ref(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        return "https://fake.cdn/frame.png"

    async def fake_vid(
        self, prompt, image_url, duration=5, aspect_ratio="16:9", plan="free", is_cancelled=None
    ):
        return "https://fake.cdn/clip.mp4"

    async def fake_storyboard(self, script, characters, user_requirement="", director_style="cinematic_balanced", **_kwargs):
        return [FakeShot(0)]

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x")
        return path

    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image", fake_img)
    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_img_ref)
    monkeypatch.setattr(video_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_vid)
    monkeypatch.setattr(storyboard_mod.StoryboardArtist, "design_storyboard", fake_storyboard)
    monkeypatch.setattr(script2video_mod, "download_video", fake_download)

    s2v = script2video_mod.Script2VideoPipeline(api_key="test-key-not-real")
    characters = [CharacterInScene(idx=0, name="Maya", static_features="30s woman", is_visible=True)]
    result = await s2v.run(
        script="Maya walks.",
        characters=characters,
        working_dir="/tmp/_museforge_test_scene",
        character_portraits={"Maya": "https://fake.cdn/portrait.png"},
        director_style="slow_cinematic",
    )
    assert result["path"] and os.path.exists(result["path"])
    assert result["shots"] and result["shots"][0]["video_url"] == "https://fake.cdn/clip.mp4"


@pytest.mark.asyncio
async def test_demo_mode_runs_offline(monkeypatch):
    """Demo mode produces a full result with placeholder assets and no network."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from pipelines.idea2video import Idea2VideoPipeline

    pipeline = Idea2VideoPipeline(api_key="", demo=True)
    result = await pipeline.run(
        idea="A lighthouse keeper meets a stranger at dawn.",
        num_scenes=2,
        working_dir="/tmp/_museforge_test_demo",
    )

    assert result["demo"] is True
    assert result["video_url"], "demo should expose a playable video_url"
    assert result["scene_count"] == 2
    first_frame = result["scenes"][0]["shots"][0]["frame_url"]
    assert first_frame.startswith("https://picsum.photos/")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
