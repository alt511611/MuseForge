"""Post-production on a finished drama: continuity edits and re-cuts.

Both build on the retake machinery, and both have a cost story that has to
hold: a global edit may only re-render the scenes its target actually appears
in, and a timeline edit may not call a generation model at all.
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
    """Stub every paid call; keep all real orchestration and file plumbing."""
    calls = {"frames": 0, "videos": 0, "edit_prompts": []}

    async def fake_generate_image(self, prompt, aspect_ratio="1:1", is_cancelled=None):
        return (
            "https://fake.cdn/plate.png"
            if "Empty location plate" in prompt
            else "https://fake.cdn/portrait.png"
        )

    async def fake_generate_image_with_reference(
        self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None
    ):
        calls["frames"] += 1
        if "CHANGE TO APPLY" in prompt:
            calls["edit_prompts"].append(prompt)
            return f"https://fake.cdn/edited_{calls['frames']}.png"
        return f"https://fake.cdn/frame_{calls['frames']}.png"

    async def fake_generate_video(
        self, prompt, image_url, duration=5, aspect_ratio="16:9", plan="free",
        is_cancelled=None, shot_profile=None,
    ):
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
    monkeypatch.setattr(
        image_mod.MuAPIImageGenerator,
        "generate_image_with_reference",
        fake_generate_image_with_reference,
    )
    monkeypatch.setattr(
        video_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video
    )
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
        characters=[
            CharacterProfile(name="Kemal", description="70s man", role="protagonist"),
        ],
        scenes=[
            {"action": "Kemal lights the stove.", "tension": 3},
            {"action": "Kemal pours the coffee.", "tension": 7},
            {"action": "Kemal sets the cup down.", "tension": 5},
        ],
    )


async def _render(tmp_path, name="job-edit"):
    import pipelines.idea2video as idea2video_mod

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    working_dir = str(tmp_path / name)
    result = await pipeline.continue_from_script(
        script=_script(), working_dir=working_dir, aspect_ratio="16:9"
    )
    return pipeline, working_dir, result


@pytest.mark.asyncio
async def test_global_edit_moves_the_lock_then_re_renders_every_affected_scene(
    fake_providers, tmp_path
):
    pipeline, working_dir, result = await _render(tmp_path)
    original_portrait = result["portraits"]["Kemal"]
    videos_after_render = fake_providers["videos"]

    edited = await pipeline.apply_global_edit(
        previous_result=result,
        instruction="put him in a red coat",
        target="Kemal",
        working_dir=working_dir,
    )

    # The lock itself moved — that is what makes the change consistent rather
    # than three scenes independently reinventing a red coat.
    assert edited["portraits"]["Kemal"] != original_portrait
    assert any("red coat" in p for p in fake_providers["edit_prompts"])

    # Kemal is in all three scenes, so all three are re-rendered — and no more.
    assert fake_providers["videos"] == videos_after_render + 3
    spliced = json.load(open(edited["video_path"]))
    assert len(spliced) == 3
    assert all("take2" in path for path in spliced)

    # The script's own description carries the change too, or the identity
    # clause restated in every frame prompt would fight the new reference.
    kemal = edited["_render_state"]["script"]["characters"][0]
    assert "red coat" in kemal["description"]


@pytest.mark.asyncio
async def test_global_edit_only_touches_the_scenes_the_character_is_in(
    fake_providers, tmp_path
):
    pipeline, working_dir, result = await _render(tmp_path)

    # Pretend the middle scene was an insert with nobody in it.
    result["scenes"][1]["shots"] = [
        {**result["scenes"][1]["shots"][0], "reference_character": None}
    ]
    videos_after_render = fake_providers["videos"]

    edited = await pipeline.apply_global_edit(
        previous_result=result,
        instruction="give him a scar",
        target="Kemal",
        working_dir=working_dir,
    )

    assert fake_providers["videos"] == videos_after_render + 2, (
        "Charging for a scene the character never appears in is charging for nothing"
    )
    spliced = json.load(open(edited["video_path"]))
    assert "take2" in spliced[0] and "take2" in spliced[2]
    assert "take2" not in spliced[1], "The untouched scene must be the original file"


@pytest.mark.asyncio
async def test_unknown_character_is_refused_before_anything_is_generated(
    fake_providers, tmp_path
):
    from pipelines.idea2video import SceneRegenerationUnavailable

    pipeline, working_dir, result = await _render(tmp_path)
    videos_after_render = fake_providers["videos"]

    with pytest.raises(SceneRegenerationUnavailable):
        await pipeline.apply_global_edit(
            previous_result=result,
            instruction="give her a hat",
            target="Ayşe",
            working_dir=working_dir,
        )
    assert fake_providers["videos"] == videos_after_render


@pytest.mark.asyncio
async def test_timeline_edit_reorders_and_drops_without_generating_anything(
    fake_providers, tmp_path
):
    pipeline, working_dir, result = await _render(tmp_path)
    spent = (fake_providers["videos"], fake_providers["frames"])

    recut = await pipeline.apply_timeline_edit(
        previous_result=result,
        timeline=[{"scene_index": 2}, {"scene_index": 0}],
        working_dir=working_dir,
    )

    assert (fake_providers["videos"], fake_providers["frames"]) == spent, (
        "A re-cut uses clips the customer already paid for — it must not call "
        "a generation model"
    )
    spliced = json.load(open(recut["video_path"]))
    assert len(spliced) == 2, "The dropped scene must not be in the cut"
    assert "scene_2" in spliced[0] and "scene_0" in spliced[1], "Order must follow the timeline"
    assert recut["scene_count"] == 2
    assert recut["timeline"] == [
        {"scene_index": 2, "trim_start": 0.0, "trim_end": 0.0},
        {"scene_index": 0, "trim_start": 0.0, "trim_end": 0.0},
    ]

    # The source scenes survive the cut, so it can be revised or reverted
    # without re-rendering anything.
    assert len(recut["scenes"]) == 3


@pytest.mark.asyncio
async def test_re_cut_can_be_revised_again_from_its_own_result(fake_providers, tmp_path):
    pipeline, working_dir, result = await _render(tmp_path)

    once = await pipeline.apply_timeline_edit(
        previous_result=result,
        timeline=[{"scene_index": 1}, {"scene_index": 0}],
        working_dir=working_dir,
    )
    twice = await pipeline.apply_timeline_edit(
        previous_result=once,
        timeline=[{"scene_index": 0}, {"scene_index": 1}, {"scene_index": 2}],
        working_dir=working_dir,
    )

    spliced = json.load(open(twice["video_path"]))
    assert len(spliced) == 3, "Restoring a dropped scene must not need a re-render"
    assert twice["cut_version"] == once["cut_version"] + 1, (
        "Each cut needs its own object key, or already-issued URLs would "
        "silently start playing a different video"
    )


@pytest.mark.asyncio
async def test_empty_timeline_is_refused(fake_providers, tmp_path):
    from pipelines.idea2video import SceneRegenerationUnavailable

    pipeline, working_dir, result = await _render(tmp_path)
    with pytest.raises(SceneRegenerationUnavailable):
        await pipeline.apply_timeline_edit(
            previous_result=result, timeline=[], working_dir=working_dir
        )
