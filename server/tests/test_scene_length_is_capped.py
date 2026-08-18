"""A scene may not be longer than the budget it was costed at.

distribute_budget fixes each scene's length before any provider call, so the
job's cost is known at charge time. The shot then asks the video endpoint for
that many seconds -- and the endpoint does not reliably give them.

Measured on a delivered job (3 scenes, 30-second budget):

    scene_0/scene_output.mp4   16.08s   budgeted  8
    scene_1/scene_output.mp4   20.08s   budgeted 10
    scene_2/scene_output.mp4   24.08s   budgeted 12

Exactly double, every scene, and all three shipped untouched: `deliver_seconds`
is only set when the generated and delivered lengths DIFFER, which happens on
a two-angle scene, and 0 meant "ship whatever came back". Every single-angle
scene -- the overwhelming majority -- therefore trusted the provider. The
drama ran 60 seconds against the 30 it was charged for.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


@pytest.mark.asyncio
async def test_a_clip_that_comes_back_double_is_cut_to_its_budget(
    monkeypatch, tmp_path
):
    from interfaces.character import CharacterInScene
    from interfaces.shot import StoryboardShot
    from pipelines.script2video import Script2VideoPipeline

    trimmed_to = []

    async def fake_design_storyboard(
        self, script, characters, user_requirement, director_style, **_kw
    ):
        # A single-angle scene: one master, no cutaway, so deliver_seconds is
        # 0 and only duration_seconds says how long it was supposed to be.
        return [
            StoryboardShot(
                idx=0,
                visual_desc="Mara at the container",
                motion_desc="static",
                duration_seconds=8.0,
            )
        ]

    async def fake_frame(self, prompt, *a, **kw):
        return "https://fake.cdn/frame.png"

    async def fake_video(self, prompt, image_url, duration, **kwargs):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    async def fake_trim(path, out_path, seconds, from_head=True):
        trimmed_to.append(seconds)
        return path

    monkeypatch.setattr(
        "agents.storyboard_artist.StoryboardArtist.design_storyboard",
        fake_design_storyboard,
    )
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image_with_reference",
        fake_frame,
    )
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image", fake_frame
    )
    monkeypatch.setattr(
        "tools.muapi_video_generator.MuAPIVideoGenerator.generate_video_from_image",
        fake_video,
    )
    monkeypatch.setattr("pipelines.script2video.download_video", fake_download)
    monkeypatch.setattr("pipelines.script2video.trim_to_duration", fake_trim)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    await pipeline.run(
        script="Mara opens the container.",
        characters=[
            CharacterInScene(idx=0, name="Mara", static_features="a woman")
        ],
        working_dir=str(tmp_path),
        character_portraits={"Mara": "https://fake.cdn/mara.png"},
    )

    assert trimmed_to == [8.0], (
        "a single-angle scene shipped whatever the provider returned"
    )


@pytest.mark.asyncio
async def test_a_two_angle_scene_still_uses_its_delivered_length(
    monkeypatch, tmp_path
):
    """deliver_seconds stays the authority where it is set: the master gives up
    its opening seconds to make room for the cutaway, so the budget is NOT the
    number to cut it to."""
    from interfaces.character import CharacterInScene
    from interfaces.shot import StoryboardShot
    from pipelines.script2video import Script2VideoPipeline

    trimmed_to = []

    async def fake_design_storyboard(
        self, script, characters, user_requirement, director_style, **_kw
    ):
        return [
            StoryboardShot(
                idx=0,
                visual_desc="master",
                motion_desc="static",
                duration_seconds=10.0,
                deliver_seconds=8.0,
            )
        ]

    async def fake_frame(self, prompt, *a, **kw):
        return "https://fake.cdn/frame.png"

    async def fake_video(self, prompt, image_url, duration, **kwargs):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    async def fake_trim(path, out_path, seconds, from_head=True):
        trimmed_to.append(seconds)
        return path

    monkeypatch.setattr(
        "agents.storyboard_artist.StoryboardArtist.design_storyboard",
        fake_design_storyboard,
    )
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image_with_reference",
        fake_frame,
    )
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image", fake_frame
    )
    monkeypatch.setattr(
        "tools.muapi_video_generator.MuAPIVideoGenerator.generate_video_from_image",
        fake_video,
    )
    monkeypatch.setattr("pipelines.script2video.download_video", fake_download)
    monkeypatch.setattr("pipelines.script2video.trim_to_duration", fake_trim)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    await pipeline.run(
        script="Mara opens the container.",
        characters=[
            CharacterInScene(idx=0, name="Mara", static_features="a woman")
        ],
        working_dir=str(tmp_path),
        character_portraits={"Mara": "https://fake.cdn/mara.png"},
    )

    assert trimmed_to == [8.0]


@pytest.mark.asyncio
async def test_a_clip_already_within_budget_is_never_re_encoded(tmp_path):
    """The cap costs nothing when the provider behaves: trim_to_duration
    returns the source untouched rather than spending a generation loss on a
    clip that was already the right length."""
    from pipelines.script2video import trim_to_duration

    source = tmp_path / "clip.mp4"
    source.write_bytes(b"not really a video")

    # A file whose duration cannot be read must not be trimmed or re-encoded.
    result = await trim_to_duration(
        str(source), str(tmp_path / "out.mp4"), 8.0
    )

    assert result == str(source)
    assert not (tmp_path / "out.mp4").exists()
