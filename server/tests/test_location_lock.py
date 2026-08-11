"""Locked SET plate — the place counterpart to the locked character portrait.

The screenwriter fixes one location for the whole drama, but that agreement
only ever existed as words re-sent in every frame prompt, so the room was
re-imagined per shot. The plate renders it once and anchors the shots that
have no character to anchor to (establishing shots, inserts, objects) — which
previously borrowed the first character's PORTRAIT, pushing a face into shots
the storyboard deliberately wrote without one.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterProfile, DramaScript  # noqa: E402


class FakeShot:
    def __init__(self, visual_desc):
        self.idx = 0
        self.visual_desc = visual_desc
        self.motion_desc = "slow push-in"
        self.audio_desc = "ambient"
        self.shot_type = "wide shot"
        self.camera_movement = "static"
        self.lens = "35mm"
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


async def _run(monkeypatch, working_dir, shot_descs, location="", location_override=None):
    """Render one scene per entry in shot_descs. Returns (plate_prompts,
    reference_url_per_scene)."""
    plate_prompts = []
    reference_calls = []

    async def fake_generate_image(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        if "Empty location plate" in prompt:
            plate_prompts.append((prompt, aspect_ratio))
            return "https://fake.cdn/set_plate.png"
        return "https://fake.cdn/kemal_portrait.png"

    async def fake_generate_image_with_reference(
        self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None
    ):
        reference_calls.append(reference_url)
        return f"https://fake.cdn/frame_{len(reference_calls)}.png"

    async def fake_generate_video_from_image(
        self, prompt, image_url, duration=5, aspect_ratio="16:9", plan="free",
        is_cancelled=None, shot_profile=None
    ):
        return "https://fake.cdn/video.mp4"

    scene_shot = iter(shot_descs)

    async def fake_design_storyboard(self, script, characters, *a, **kw):
        return [FakeShot(next(scene_shot))]

    async def fake_download_video(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake video bytes")
        return path

    async def fake_concatenate_videos(paths, out_path):
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(b"fake concat")
        return out_path

    async def fake_add_background_music(video_path, output_path, *args, **kwargs):
        with open(output_path, "wb") as f:
            f.write(b"fake mixed")
        return output_path

    import agents.storyboard_artist as storyboard_mod
    import pipelines.idea2video as idea2video_mod
    import pipelines.script2video as script2video_mod
    import tools.muapi_image_generator as image_mod
    import tools.muapi_video_generator as video_mod

    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image", fake_generate_image)
    monkeypatch.setattr(
        image_mod.MuAPIImageGenerator,
        "generate_image_with_reference",
        fake_generate_image_with_reference,
    )
    monkeypatch.setattr(
        video_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video_from_image
    )
    monkeypatch.setattr(storyboard_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(script2video_mod, "download_video", fake_download_video)
    monkeypatch.setattr(script2video_mod, "concatenate_videos", fake_concatenate_videos)
    monkeypatch.setattr(idea2video_mod, "concatenate_videos", fake_concatenate_videos)
    monkeypatch.setattr(idea2video_mod, "add_background_music", fake_add_background_music)

    script = DramaScript(
        title="Meridyen",
        logline="A coffee master hands down his craft.",
        mood="warm",
        estimated_duration_seconds=24,
        setting_location=location,
        setting_time_of_day="early morning" if location else "",
        characters=[CharacterProfile(name="Kemal", description="70s man, white moustache", role="protagonist")],
        scenes=[f"Scene {i}" for i in range(len(shot_descs))],
    )

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    result = await pipeline.continue_from_script(
        script=script,
        working_dir=working_dir,
        aspect_ratio="16:9",
        location_image_override=location_override,
    )
    return plate_prompts, reference_calls, result


@pytest.mark.asyncio
async def test_characterless_shot_anchors_to_the_set_plate_not_a_face(monkeypatch, tmp_path):
    """The whole point: a shot with no character in it must reference the ROOM."""
    plate_prompts, references, result = await _run(
        monkeypatch,
        str(tmp_path / "job"),
        shot_descs=[
            "Kemal pours coffee from the copper pot.",  # names a character
            "The empty room, steam rising from a cup.",  # names nobody
        ],
        location="stone-walled old Istanbul coffeehouse",
    )

    assert len(plate_prompts) == 1, "The set must be rendered exactly ONCE for the whole drama"
    plate_prompt, plate_ratio = plate_prompts[0]
    assert "stone-walled old Istanbul coffeehouse" in plate_prompt
    assert "no people" in plate_prompt, "A place reference containing a person leaks that person into every shot using it"
    assert plate_ratio == "16:9", "The plate conditions widescreen frames, so it must be shot widescreen"

    assert references[0] == "https://fake.cdn/kemal_portrait.png", "A named character still wins the anchor"
    assert references[1] == "https://fake.cdn/set_plate.png", (
        "A characterless shot must anchor to the locked set, not to an arbitrary character's face"
    )
    assert result["location_plate"] == "https://fake.cdn/set_plate.png"


@pytest.mark.asyncio
async def test_uploaded_set_photo_is_used_verbatim(monkeypatch, tmp_path):
    """A user who uploads their real shop wants THAT shop, not an AI redraw."""
    plate_prompts, references, result = await _run(
        monkeypatch,
        str(tmp_path / "job"),
        shot_descs=["Wide on the empty counter at dawn."],
        location="stone-walled old Istanbul coffeehouse",
        location_override="https://user.cdn/my_real_shop.jpg",
    )

    assert plate_prompts == [], "An uploaded plate must skip generation entirely"
    assert references == ["https://user.cdn/my_real_shop.jpg"]
    assert result["location_plate"] == "https://user.cdn/my_real_shop.jpg"


@pytest.mark.asyncio
async def test_no_location_in_script_preserves_the_old_character_fallback(monkeypatch, tmp_path):
    """No plate is possible, so behaviour must be byte-for-byte what it was."""
    plate_prompts, references, result = await _run(
        monkeypatch,
        str(tmp_path / "job"),
        shot_descs=["The empty room, steam rising from a cup."],
        location="",
    )

    assert plate_prompts == []
    assert result["location_plate"] is None
    assert references == ["https://fake.cdn/kemal_portrait.png"], (
        "Without a plate the shot must still get the previous first-character "
        "reference rather than dropping to an unreferenced frame"
    )
