"""A scene that cannot be rendered must fail loudly and stop spending.

Two ways the shot loop could end a job badly, both found while auditing the
production path for a release:

1. The shot-level ``asyncio.gather`` had no sibling cancellation. gather()
   propagates the first failure but leaves the other tasks running, so a
   two-shot scene whose first shot failed kept the second one polling the
   video endpoint -- which bills per generation whether or not the job that
   asked for it still exists. The scene-level gather in idea2video already
   cancelled its siblings for exactly this reason.

2. With no usable shot video, the scene returned a path naming a file nothing
   had written. The path is a truthy string, so it was appended to the
   concatenation list and the failure surfaced much later as an unreadable
   master, with nothing in the log pointing back at the scene that caused it.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


def _shots(*descriptions):
    from interfaces.shot import StoryboardShot

    async def fake_design_storyboard(
        self, script, characters, user_requirement, director_style, **_kwargs
    ):
        return [
            StoryboardShot(idx=i, visual_desc=d, motion_desc="static")
            for i, d in enumerate(descriptions)
        ]

    return fake_design_storyboard


def _common_stubs(monkeypatch):
    import agents.storyboard_artist as sb_mod
    import tools.muapi_image_generator as img_mod
    import pipelines.script2video as s2v_mod

    async def fake_frame(self, prompt, *a, **kw):
        return "https://fake.cdn/frame.png"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    monkeypatch.setattr(
        img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_frame
    )
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image", fake_frame)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)
    return sb_mod


@pytest.mark.asyncio
async def test_a_failed_shot_stops_its_siblings_spending(monkeypatch, tmp_path):
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    import tools.muapi_video_generator as vid_mod

    sb_mod = _common_stubs(monkeypatch)
    monkeypatch.setattr(
        sb_mod.StoryboardArtist,
        "design_storyboard",
        _shots("Margit at the counter", "Margit in the doorway"),
    )
    # Both shots must be in flight at once for there to be a sibling to strand.
    monkeypatch.setenv("MUSEFORGE_SHOT_CONCURRENCY", "2")

    entered = []
    sibling_is_polling = asyncio.Event()
    sibling_was_cancelled = False

    async def fake_generate_video(self, prompt, image_url, duration, **kwargs):
        # Keyed on arrival order rather than on the prompt text: the prompt is
        # built by the pipeline and carries no reliable marker of which shot
        # it belongs to.
        nonlocal sibling_was_cancelled
        mine = len(entered)
        entered.append(mine)

        if mine == 0:
            # Fail, but not before the sibling is actually mid-poll -- a
            # failure that lands first would prove nothing about stranding.
            try:
                await asyncio.wait_for(sibling_is_polling.wait(), 2)
            except asyncio.TimeoutError:
                pass
            raise RuntimeError("the video endpoint refused this shot")

        sibling_is_polling.set()
        try:
            # Stands in for a poll loop against the provider.
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            sibling_was_cancelled = True
            raise
        return "https://fake.cdn/clip.mp4"

    monkeypatch.setattr(
        vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video
    )

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    with pytest.raises(RuntimeError, match="refused this shot"):
        await asyncio.wait_for(
            pipeline.run(
                script="Margit closes the shop.",
                characters=[
                    CharacterInScene(
                        idx=0, name="Margit", static_features="woman in her seventies"
                    )
                ],
                working_dir=str(tmp_path),
                character_portraits={"Margit": "https://fake.cdn/margit.png"},
            ),
            timeout=5,
        )

    assert sibling_was_cancelled, (
        "the surviving shot kept polling a paid endpoint behind a failed job"
    )


@pytest.mark.asyncio
async def test_a_scene_with_no_usable_shot_fails_instead_of_naming_a_missing_file(
    monkeypatch, tmp_path
):
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene

    sb_mod = _common_stubs(monkeypatch)
    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", _shots())

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    with pytest.raises(RuntimeError, match="no usable shot"):
        await pipeline.run(
            script="Margit closes the shop.",
            characters=[
                CharacterInScene(
                    idx=0, name="Margit", static_features="woman in her seventies"
                )
            ],
            working_dir=str(tmp_path),
            character_portraits={"Margit": "https://fake.cdn/margit.png"},
        )

    assert not os.path.exists(os.path.join(str(tmp_path), "scene_output.mp4"))
