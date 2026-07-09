"""
Regression test for:
  1) the character-consistency lock (portrait generated once per drama, not
     once per scene)
  2) director_style propagation into the storyboard artist
  3) background music added exactly once, on the final concatenated video

All MuAPI network calls are monkey-patched — no API key or network access
required.
"""
import asyncio
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.camera import DIRECTOR_STYLES, get_director_style
from interfaces.character import CharacterInScene


async def main():
    # ---- Camera presets sanity check ----
    assert "slow_cinematic" in DIRECTOR_STYLES
    preset = get_director_style("slow_cinematic")
    assert "slow" in preset.storyboard_guidance.lower()
    print(f"[OK] Director style preset resolves: {preset.label} -> lens {preset.default_lens}")

    fake_portrait_calls = []
    music_call_count = 0

    async def fake_generate_image(self, prompt, aspect_ratio="1:1"):
        fake_portrait_calls.append(prompt)
        return f"https://fake.cdn/portrait_{len(fake_portrait_calls)}.png"

    fake_storyboard_calls = []

    class FakeShot:
        def __init__(self, idx):
            self.idx = idx
            self.visual_desc = "Maya walks through a corridor."
            self.motion_desc = "steady tracking shot"
            self.audio_desc = "ambient hum"
            self.shot_type = "medium shot"
            self.camera_movement = "slow push-in"
            self.lens = "50mm"

        def model_dump(self):
            return {
                "idx": self.idx,
                "visual_desc": self.visual_desc,
                "motion_desc": self.motion_desc,
                "audio_desc": self.audio_desc,
                "shot_type": self.shot_type,
                "camera_movement": self.camera_movement,
                "lens": self.lens,
            }

    async def fake_design_storyboard(self, script, characters, user_requirement, director_style="cinematic_balanced"):
        fake_storyboard_calls.append(director_style)
        return [FakeShot(0)]

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9"):
        return f"https://fake.cdn/frame_from_{reference_url.split('/')[-1]}"

    async def fake_generate_video_from_image(self, prompt, image_url, duration=5, aspect_ratio="16:9"):
        return "https://fake.cdn/video.mp4"

    async def fake_download_video(url, path):
        with open(path, "wb") as f:
            f.write(b"fake video bytes")

    async def fake_concatenate_videos(paths, out_path):
        with open(out_path, "wb") as f:
            f.write(b"fake concatenated video")

    async def fake_add_background_music(video_path, output_path, music_url=None):
        nonlocal music_call_count
        music_call_count += 1
        with open(output_path, "wb") as f:
            f.write(b"fake video with music")
        return output_path

    with patch("tools.muapi_image_generator.MuAPIImageGenerator.generate_image", new=fake_generate_image), \
         patch("tools.muapi_image_generator.MuAPIImageGenerator.generate_image_with_reference", new=fake_generate_image_with_reference), \
         patch("tools.muapi_video_generator.MuAPIVideoGenerator.generate_video_from_image", new=fake_generate_video_from_image), \
         patch("agents.storyboard_artist.StoryboardArtist.design_storyboard", new=fake_design_storyboard), \
         patch("pipelines.script2video.download_video", new=fake_download_video), \
         patch("pipelines.script2video.concatenate_videos", new=fake_concatenate_videos), \
         patch("pipelines.idea2video.concatenate_videos", new=fake_concatenate_videos), \
         patch("pipelines.idea2video.add_background_music", new=fake_add_background_music):

        from pipelines.idea2video import Idea2VideoPipeline
        from pipelines.script2video import Script2VideoPipeline

        pipeline = Idea2VideoPipeline(api_key="test-key-not-real")

        characters = [
            CharacterInScene(
                idx=0, name="Maya", static_features="30s woman, dark hair",
                dynamic_features="arctic parka", is_visible=True,
            )
        ]

        portraits = await pipeline._lock_character_portraits(characters, style="Cinematic")
        assert "Maya" in portraits
        assert len(fake_portrait_calls) == 1
        print(f"[OK] Locked portrait generated once for Maya: {portraits['Maya']}")

        async def noop_progress(stage, message, progress, data=None):
            pass

        s2v = Script2VideoPipeline(api_key="test-key-not-real")

        for scene_idx in (0, 1, 2):
            video_path = await s2v.run(
                script="Maya walks down the corridor.",
                characters=characters,
                user_requirement="",
                style="Cinematic",
                working_dir=f"/tmp/_smoke_scene_{scene_idx}",
                progress_callback=noop_progress,
                scene_idx=scene_idx,
                character_portraits=portraits,
                director_style="slow_cinematic",
            )
            assert os.path.exists(video_path)

        assert len(fake_portrait_calls) == 1, (
            f"Character portrait was regenerated across scenes! Expected 1, got {len(fake_portrait_calls)}"
        )
        print(f"[OK] Portrait NOT regenerated across 3 scenes — still {len(fake_portrait_calls)} call total")

        assert fake_storyboard_calls == ["slow_cinematic"] * 3
        print(f"[OK] director_style propagated to storyboard artist every scene: {fake_storyboard_calls}")

        # CRITICAL: Background music must be added exactly ONCE, on the final
        # concatenated drama, not per scene. This assertion guards against
        # regressions where someone re-introduces per-scene music calls.
        assert music_call_count == 1, (
            f"Background music called {music_call_count} times, expected exactly 1 "
            "(on the final concatenated video, not per scene)."
        )
        print(f"[OK] Background music called exactly once: {music_call_count}")

    print("\nALL SMOKE TESTS PASSED ✅")


if __name__ == "__main__":
    asyncio.run(main())
