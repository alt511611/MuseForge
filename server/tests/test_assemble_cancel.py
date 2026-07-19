"""Cancel checkpoints in _assemble_final_drama.

Guarantees that once a job is cancelled, no ffmpeg/moviepy/MuAPI work
starts during the final assembly stage. Checks fire BEFORE each step;
once a render has begun we intentionally do not abort mid-write.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_assemble_raises_cancelled_before_any_work(tmp_path, monkeypatch):
    """is_cancelled=True at entry → PipelineCancelled, zero side-effect calls."""
    from pipelines.idea2video import Idea2VideoPipeline
    from pipelines.script2video import PipelineCancelled

    calls = {"concat": 0, "music": 0, "watermark": 0}

    async def _fake_concat(*_a, **_k):
        calls["concat"] += 1
        raise AssertionError("concatenate_videos must not run after cancel")

    async def _fake_music(*_a, **_k):
        calls["music"] += 1
        raise AssertionError("add_background_music must not run after cancel")

    async def _fake_watermark(*_a, **_k):
        calls["watermark"] += 1
        raise AssertionError("add_watermark must not run after cancel")

    monkeypatch.setattr("pipelines.idea2video.concatenate_videos", _fake_concat)
    monkeypatch.setattr("pipelines.idea2video.add_background_music", _fake_music)
    monkeypatch.setattr("pipelines.idea2video.add_watermark", _fake_watermark)

    pipeline = Idea2VideoPipeline(api_key="", demo=False)

    with pytest.raises(PipelineCancelled):
        await pipeline._assemble_final_drama(
            scene_paths=["scene0.mp4"],
            working_dir=str(tmp_path / "job"),
            music_url=None,
            plan="free",
            is_cancelled=lambda: True,
        )

    assert calls == {"concat": 0, "music": 0, "watermark": 0}


@pytest.mark.asyncio
async def test_assemble_cancels_before_music_after_concat(tmp_path, monkeypatch):
    """Cancel arriving after concat but before music → no music/watermark work."""
    from pipelines.idea2video import Idea2VideoPipeline
    from pipelines.script2video import PipelineCancelled

    state = {"phase": "pre_concat"}
    calls = {"concat": 0, "music": 0, "watermark": 0}

    async def _fake_concat(scene_paths, output_path):
        calls["concat"] += 1
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"concatenated")
        # Flip cancel flag only after concat has completed — simulates a
        # cancel arriving between assemble steps.
        state["phase"] = "post_concat"

    async def _fake_music(*_a, **_k):
        calls["music"] += 1
        raise AssertionError("music must not start after mid-assemble cancel")

    async def _fake_watermark(*_a, **_k):
        calls["watermark"] += 1
        raise AssertionError("watermark must not start after mid-assemble cancel")

    monkeypatch.setattr("pipelines.idea2video.concatenate_videos", _fake_concat)
    monkeypatch.setattr("pipelines.idea2video.add_background_music", _fake_music)
    monkeypatch.setattr("pipelines.idea2video.add_watermark", _fake_watermark)

    pipeline = Idea2VideoPipeline(api_key="", demo=False)

    with pytest.raises(PipelineCancelled):
        await pipeline._assemble_final_drama(
            scene_paths=["scene0.mp4"],
            working_dir=str(tmp_path / "job"),
            plan="creator",
            is_cancelled=lambda: state["phase"] == "post_concat",
        )

    assert calls["concat"] == 1
    assert calls["music"] == 0
    assert calls["watermark"] == 0
