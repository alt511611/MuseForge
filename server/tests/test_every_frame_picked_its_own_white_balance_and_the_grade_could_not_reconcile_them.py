"""Every frame picked its own white balance, and the grade could not reconcile them.

The film's colour was decided in one place: the grade, an ffmpeg chain run on
the finished master. Every picture before it was free to choose: one scene
warm, the next cool, a plate in daylight blue behind a face in tungsten. A
grade shifts a whole film the same way; it cannot make six frames that were
lit differently agree with each other, and at the strengths faces need it
does not try.

So the grade's look is now also said in words, where the pictures are made:
on every frame prompt (riding the style prefix) and on every plate.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.camera import DIRECTOR_STYLES  # noqa: E402
from interfaces.character import CharacterInScene, CharacterProfile, DramaScript, ScriptScene  # noqa: E402
from interfaces.color_grade import COLOR_GRADES, palette_for  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import build_frame_prompt  # noqa: E402


def test_every_grade_says_its_look_in_words():
    for name, grade in COLOR_GRADES.items():
        assert grade.palette.strip(), f"{name} has no palette"


def test_a_palette_is_short_because_a_face_pays_for_it():
    """It rides the REQUIRED style prefix, which is measured into the identity
    reserve: every character here is taken from the cast's description."""
    for name, grade in COLOR_GRADES.items():
        assert len(grade.palette) < 90, (name, len(grade.palette))


def test_every_director_style_has_a_palette():
    for name in DIRECTOR_STYLES:
        assert palette_for(name), name
    # An unknown style degrades to the house look, never to nothing.
    assert palette_for("no-such-style") == COLOR_GRADES["natural"].palette


def test_noir_asks_for_contrast_and_leaves_the_monochrome_to_the_grade():
    """A monochrome start frame beside colour portraits the model is told to
    match is two instructions about skin that cannot both be kept."""
    palette = palette_for("noir_mystery").lower()
    assert "contrast" in palette
    assert "black and white" not in palette and "black-and-white" not in palette


def _shot():
    return StoryboardShot(
        idx=0, visual_desc="Vera reads the letter at the desk.", motion_desc="",
        expression_desc="jaw set", shot_type="medium", lens="35mm",
    )


def test_the_palette_rides_the_style_prefix():
    vera = CharacterInScene(idx=0, name="Vera", static_features="woman, 40s", is_visible=True)
    prompt = build_frame_prompt(
        "Cinematic", _shot(), characters=[vera], matched_char=vera,
        palette=palette_for("intimate_closeup"),
    )
    assert prompt.startswith("Cinematic style. Warm soft palette")


def test_a_caller_that_names_no_palette_gets_the_prompt_it_always_got():
    prompt = build_frame_prompt("Cinematic", _shot())
    assert prompt.startswith("Cinematic style. Vera reads the letter")


RICH = (
    "a woman in her early thirties, sharp cheekbones, dark hair pulled back "
    "in a wet knot, tired grey eyes, lean build, a faded scar across her left eyebrow"
)


def test_a_crowded_frame_still_keeps_every_face_with_the_longest_palette():
    longest = max((g.palette for g in COLOR_GRADES.values()), key=len)
    cast = [
        CharacterInScene(
            idx=i, name=f"Character{i}", static_features=RICH, is_visible=True,
            wardrobe="a soaked navy dock parka over a charcoal crew-neck sweater",
        )
        for i in range(5)
    ]
    prompt = build_frame_prompt(
        "Sci-Fi", _shot(),
        setting_location="a rain-soaked cargo harbour, container stacks and gantry cranes",
        setting_time_of_day="night", setting_era="present day",
        has_dialogue=True, lipsync_enabled=True,
        characters=cast, matched_char=cast[0], palette=longest,
    )
    assert longest in prompt
    assert "FIXED in every scene" in prompt
    for c in cast:
        assert c.name in prompt


# --- the render --------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_plate_and_the_frames_are_drawn_in_the_film_s_palette(monkeypatch, tmp_path):
    plates, frames = [], []

    async def fake_generate_image(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        if "Empty location plate" in prompt:
            plates.append(prompt)
            return "https://cdn/office.png"
        return "https://cdn/vera.png"

    async def fake_ref(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        frames.append(prompt)
        return "https://cdn/frame.png"

    async def fake_video(self, prompt, image_url, duration=5, aspect_ratio="16:9", plan="free",
                         is_cancelled=None, shot_profile=None):
        return "https://cdn/video.mp4"

    class _Shot:
        def __init__(self, text):
            self.idx = 0
            self.visual_desc = text
            self.motion_desc = ""
            self.audio_desc = ""
            self.shot_type = "medium shot"
            self.camera_movement = "static"
            self.lens = "35mm"
            self.duration_seconds = 5.0
            self.frame_url = None
            self.video_url = None

        def model_dump(self, **kw):
            return {"idx": 0, "visual_desc": self.visual_desc, "motion_desc": "",
                    "duration_seconds": 5.0, "frame_url": self.frame_url,
                    "video_url": self.video_url}

    async def fake_storyboard(self, script, characters, *a, **kw):
        return [_Shot(script)]

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(path, "wb").write(b"v")
        return path

    async def fake_concat(paths, out_path):
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        open(out_path, "wb").write(b"c")
        return out_path

    import agents.storyboard_artist as storyboard_mod
    import pipelines.idea2video as idea2video_mod
    import pipelines.script2video as script2video_mod
    import tools.muapi_image_generator as image_mod
    import tools.muapi_video_generator as video_mod

    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image", fake_generate_image)
    monkeypatch.setattr(image_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_ref)
    monkeypatch.setattr(video_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_video)
    monkeypatch.setattr(storyboard_mod.StoryboardArtist, "design_storyboard", fake_storyboard)
    monkeypatch.setattr(script2video_mod, "download_video", fake_download)
    monkeypatch.setattr(script2video_mod, "concatenate_videos", fake_concat)
    monkeypatch.setattr(idea2video_mod, "concatenate_videos", fake_concat)

    script = DramaScript(
        title="Harbour",
        logline="x",
        setting_location="harbour office with a steel desk",
        setting_time_of_day="dusk",
        characters=[CharacterProfile(name="Vera", description="woman, 40s", role="protagonist")],
        scenes=[ScriptScene(action="Vera reads the letter at the desk.")],
    )
    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    await pipeline.continue_from_script(
        script=script, working_dir=str(tmp_path / "job"), director_style="intimate_closeup"
    )

    palette = palette_for("intimate_closeup")
    assert plates and all(palette in p for p in plates)
    assert frames and all(palette in p for p in frames)
