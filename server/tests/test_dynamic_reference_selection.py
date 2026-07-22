"""Dynamic character reference selection across scenes (adapted from ViMax's
"previous timeline" technique): from the second scene onward, the MOST
RECENTLY generated frame for a character should be used as the identity
reference, not the static locked portrait -- so outfit/pose/lighting drift
introduced in an earlier scene carries forward instead of always snapping
back to the original portrait.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene, CharacterProfile, DramaScript  # noqa: E402


class FakeShot:
    """One shot per scene, always naming the same character."""

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


@pytest.mark.asyncio
async def test_second_scene_references_first_scenes_generated_frame(monkeypatch):
    """3-scene script, one shot per scene: scene 2's reference must be
    scene 1's GENERATED FRAME, not scene 1's locked portrait."""
    reference_calls = []

    async def fake_generate_image(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        # Portrait lock (referenceless call) -- happens once, before any scene.
        return "https://fake.cdn/maya_portrait.png"

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        reference_calls.append(reference_url)
        return f"https://fake.cdn/frame_{len(reference_calls)}.png"

    async def fake_generate_video_from_image(
        self, prompt, image_url, duration=5, aspect_ratio="16:9", plan="free", is_cancelled=None
    ):
        return "https://fake.cdn/video.mp4"

    async def fake_design_storyboard(self, script, characters, user_requirement="", director_style="cinematic_balanced", **_kwargs):
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
        num_scenes=3,
        working_dir="/tmp/_museforge_test_dynamic_ref",
    )

    assert len(reference_calls) == 3, f"Expected exactly 3 frame generations, got {reference_calls}"

    # Scene 1 (first-ever shot for Maya): unchanged behavior -- the locked portrait.
    assert reference_calls[0] == "https://fake.cdn/maya_portrait.png"

    # Scene 2: must be scene 1's GENERATED FRAME, NOT the portrait again.
    assert reference_calls[1] == "https://fake.cdn/frame_1.png"
    assert reference_calls[1] != "https://fake.cdn/maya_portrait.png"

    # Scene 3: must chain forward to scene 2's generated frame.
    assert reference_calls[2] == "https://fake.cdn/frame_2.png"

    assert result["scene_count"] == 3


@pytest.mark.asyncio
async def test_single_scene_call_without_shared_dict_still_uses_portrait(monkeypatch):
    """Script2VideoPipeline.run() called directly (no last_frame_by_character
    passed, e.g. existing callers/tests) must behave exactly as before."""
    import pipelines.script2video as script2video_mod
    import tools.muapi_image_generator as image_mod
    import tools.muapi_video_generator as video_mod
    import agents.storyboard_artist as storyboard_mod

    async def fake_img_ref(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        return f"https://fake.cdn/frame_from_{reference_url.split('/')[-1]}"

    async def fake_vid(self, prompt, image_url, duration=5, aspect_ratio="16:9", plan="free", is_cancelled=None):
        return "https://fake.cdn/clip.mp4"

    async def fake_storyboard(self, script, characters, user_requirement="", director_style="cinematic_balanced", **_kwargs):
        return [FakeShot(0)]

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"x")
        return path

    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_img_ref)
    monkeypatch.setattr(video_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_vid)
    monkeypatch.setattr(storyboard_mod.StoryboardArtist, "design_storyboard", fake_storyboard)
    monkeypatch.setattr(script2video_mod, "download_video", fake_download)

    s2v = script2video_mod.Script2VideoPipeline(api_key="test-key-not-real")
    characters = [CharacterInScene(idx=0, name="Maya", static_features="30s woman", is_visible=True)]
    result = await s2v.run(
        script="Maya walks.",
        characters=characters,
        working_dir="/tmp/_museforge_test_dynamic_ref_single",
        character_portraits={"Maya": "https://fake.cdn/portrait.png"},
    )
    assert result["shots"][0]["frame_url"] == "https://fake.cdn/frame_from_portrait.png"
