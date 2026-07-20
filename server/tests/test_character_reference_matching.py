"""Verify shot-level character reference selection: the ACTUAL character
named in a shot's text is used as the portrait reference, not always
"whichever character is first in the list" -- found via a real report of
other characters appearing between scenes.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


@pytest.mark.asyncio
async def test_reference_uses_named_character_not_always_first(monkeypatch, tmp_path):
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    from interfaces.shot import StoryboardShot

    captured_refs = []

    async def fake_design_storyboard(self, script, characters, user_requirement, director_style, **_kwargs):
        # Two shots: first mentions Sam, second mentions Maria -- reversed
        # from list order (Sam is characters[0], Maria is characters[1]),
        # so a correct implementation must NOT just always pick Sam.
        return [
            StoryboardShot(idx=0, visual_desc="Maria stands by the window", motion_desc="Maria turns"),
        ]

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        captured_refs.append(reference_url)
        return "https://fake.cdn/frame.png"

    async def fake_generate_image(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        captured_refs.append(None)
        return "https://fake.cdn/frame.png"

    async def fake_generate_video(self, prompt, image_url, duration, aspect_ratio="16:9", plan="free", is_cancelled=None):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    import agents.storyboard_artist as sb_mod
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod
    import pipelines.script2video as s2v_mod

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_generate_image_with_reference)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image", fake_generate_image)
    monkeypatch.setattr(vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [
        CharacterInScene(idx=0, name="Sam", static_features="a sailor", is_visible=True),
        CharacterInScene(idx=1, name="Maria", static_features="a painter", is_visible=True),
    ]
    portraits = {"Sam": "https://fake.cdn/sam_portrait.png", "Maria": "https://fake.cdn/maria_portrait.png"}

    result = await pipeline.run(
        script="test script",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits=portraits,
    )

    # The shot's text only mentions Maria -- must use Maria's portrait,
    # NOT Sam's (Sam is characters[0], the old buggy "always first" pick).
    assert captured_refs == ["https://fake.cdn/maria_portrait.png"], (
        f"Expected Maria's portrait to be used (she's named in the shot text), "
        f"got: {captured_refs}"
    )
    assert result["shots"][0]["reference_character"] == "Maria"


@pytest.mark.asyncio
async def test_reference_falls_back_to_first_character_when_no_name_matches(monkeypatch, tmp_path):
    """A pure landscape/establishing shot with no character name in its
    text should fall back to the first visible character (same as the
    previous unconditional behavior), not fail to find a reference at all."""
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    from interfaces.shot import StoryboardShot

    captured_refs = []

    async def fake_design_storyboard(self, script, characters, user_requirement, director_style, **_kwargs):
        return [StoryboardShot(idx=0, visual_desc="A wide shot of the harbor at dawn", motion_desc="static")]

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        captured_refs.append(reference_url)
        return "https://fake.cdn/frame.png"

    async def fake_generate_video(self, prompt, image_url, duration, aspect_ratio="16:9", plan="free", is_cancelled=None):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    import agents.storyboard_artist as sb_mod
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod
    import pipelines.script2video as s2v_mod

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_generate_image_with_reference)
    monkeypatch.setattr(vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [
        CharacterInScene(idx=0, name="Sam", static_features="a sailor", is_visible=True),
        CharacterInScene(idx=1, name="Maria", static_features="a painter", is_visible=True),
    ]
    portraits = {"Sam": "https://fake.cdn/sam_portrait.png", "Maria": "https://fake.cdn/maria_portrait.png"}

    result = await pipeline.run(
        script="test script",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits=portraits,
    )

    assert captured_refs == ["https://fake.cdn/sam_portrait.png"]
    assert result["shots"][0]["reference_character"] == "Sam"
