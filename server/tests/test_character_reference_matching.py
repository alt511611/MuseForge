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

    async def fake_generate_video(self, prompt, image_url, duration, aspect_ratio="16:9", plan="free", is_cancelled=None, shot_profile=None):
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

    async def fake_generate_video(self, prompt, image_url, duration, aspect_ratio="16:9", plan="free", is_cancelled=None, shot_profile=None):
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


def _stub_generation(monkeypatch, captured_refs):
    """Wire the image/video/download calls to fakes and record every reference."""
    import agents.storyboard_artist as sb_mod
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod
    import pipelines.script2video as s2v_mod

    async def fake_generate_image_with_reference(
        self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None
    ):
        captured_refs.append(reference_url)
        return "https://fake.cdn/frame.png"

    async def fake_generate_image(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        captured_refs.append(None)
        return "https://fake.cdn/frame.png"

    async def fake_generate_video(
        self, prompt, image_url, duration, aspect_ratio="16:9", plan="free",
        is_cancelled=None, shot_profile=None,
    ):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    monkeypatch.setattr(
        img_mod.MuAPIImageGenerator,
        "generate_image_with_reference",
        fake_generate_image_with_reference,
    )
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image", fake_generate_image)
    monkeypatch.setattr(
        vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video
    )
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)
    return sb_mod


def _one_shot(visual_desc, motion_desc="static"):
    from interfaces.shot import StoryboardShot

    async def fake_design_storyboard(
        self, script, characters, user_requirement, director_style, **_kwargs
    ):
        return [StoryboardShot(idx=0, visual_desc=visual_desc, motion_desc=motion_desc)]

    return fake_design_storyboard


# ── a shot that shows a person but names nobody ─────────────────────────────
#
# The delivered drama that prompted these: an old bookseller walking to an
# address. Five of its eight shots were staged outdoors and written without a
# name ("the old bookseller walks the alley"), so each one took the EMPTY
# location plate as its reference and the model invented a fresh face for it --
# the protagonist appeared as a blonde woman in her forties, twice as a
# stranger in her twenties, and once as an old man.


@pytest.mark.asyncio
async def test_a_nameless_shot_with_a_person_in_it_anchors_to_the_scene_subject(
    monkeypatch, tmp_path
):
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene

    captured_refs = []
    sb_mod = _stub_generation(monkeypatch, captured_refs)
    monkeypatch.setattr(
        sb_mod.StoryboardArtist,
        "design_storyboard",
        _one_shot("The old bookseller walks the alley, her coat pulled close"),
    )

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [
        CharacterInScene(idx=0, name="Margit", static_features="woman in her seventies"),
        CharacterInScene(idx=1, name="Elias", static_features="man in his eighties"),
    ]
    result = await pipeline.run(
        # The SCENE names her even though the shot forgot to.
        script="Margit walks to the address on the envelope one last time.",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits={
            "Margit": "https://fake.cdn/margit.png",
            "Elias": "https://fake.cdn/elias.png",
        },
        location_plate_url="https://fake.cdn/empty_alley.png",
    )

    assert captured_refs == ["https://fake.cdn/margit.png"], (
        "a shot with a person in it must anchor to a face, not to the "
        f"deliberately empty set plate; got {captured_refs}"
    )
    assert result["shots"][0]["reference_character"] == "Margit"


@pytest.mark.asyncio
async def test_a_genuinely_empty_establishing_shot_still_takes_the_plate(
    monkeypatch, tmp_path
):
    """The plate branch keeps the shots it was built for. Anchoring an empty
    street to a portrait is the bug that branch exists to prevent."""
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene

    captured_refs = []
    sb_mod = _stub_generation(monkeypatch, captured_refs)
    monkeypatch.setattr(
        sb_mod.StoryboardArtist,
        "design_storyboard",
        _one_shot("The alley at dusk, lamps coming on along the wet stone"),
    )

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    result = await pipeline.run(
        script="Margit walks to the address on the envelope one last time.",
        characters=[
            CharacterInScene(idx=0, name="Margit", static_features="woman in her seventies"),
        ],
        working_dir=str(tmp_path),
        character_portraits={"Margit": "https://fake.cdn/margit.png"},
        location_plate_url="https://fake.cdn/empty_alley.png",
    )

    assert captured_refs == ["https://fake.cdn/empty_alley.png"]
    assert result["shots"][0]["reference_character"] is None


@pytest.mark.asyncio
async def test_an_unattributable_person_is_left_to_the_plate(monkeypatch, tmp_path):
    """No name in the shot, no name in the scene, and more than one candidate:
    the plate keeps the fallback. Anchoring here would be a coin toss between
    two faces, which is the failure on_screen_name_matches was narrowed to
    avoid -- a wrong anchor holds for the whole film."""
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene

    captured_refs = []
    sb_mod = _stub_generation(monkeypatch, captured_refs)
    monkeypatch.setattr(
        sb_mod.StoryboardArtist,
        "design_storyboard",
        _one_shot("She stops at the door, her hand raised to knock"),
    )

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    result = await pipeline.run(
        script="A door. A hand. Sixty years of not knocking.",
        characters=[
            CharacterInScene(idx=0, name="Margit", static_features="woman in her seventies"),
            CharacterInScene(idx=1, name="Elias", static_features="man in his eighties"),
        ],
        working_dir=str(tmp_path),
        character_portraits={
            "Margit": "https://fake.cdn/margit.png",
            "Elias": "https://fake.cdn/elias.png",
        },
        location_plate_url="https://fake.cdn/empty_alley.png",
    )

    assert captured_refs == ["https://fake.cdn/empty_alley.png"]
    assert result["shots"][0]["reference_character"] is None


def test_the_person_test_reads_presence_not_scenery():
    from pipelines.script2video import shot_shows_a_person

    assert shot_shows_a_person("the old bookseller walks the alley, her coat open")
    assert shot_shows_a_person("a hand places the letter on the counter")
    assert shot_shows_a_person("close on the face as the door opens")
    assert not shot_shows_a_person("the alley at dusk, lamps coming on")
    assert not shot_shows_a_person("the returned novel on an empty return cart")


def test_the_storyboard_is_told_to_name_everyone_it_shows():
    """The repair above is a net under the prompt, not a substitute for it:
    an anchor picked from the scene is right about WHO but blind to a shot
    that deliberately features the other character."""
    from agents.storyboard_artist import StoryboardArtist

    assert "NAME EVERY PERSON IN FRAME" in StoryboardArtist.SYSTEM_PROMPT
