"""A stage that only speaks when it finishes is billed to the stage before it.

JobStore._record_stage_timing closes a stage when a DIFFERENT one is emitted,
so elapsed time belongs to whichever stage spoke last. The lip-sync pass had
exactly one emit and it fired on completion, which meant that from the moment
the scene loop stopped talking until the first provider replied -- the whole
wait, and it is the longest wait in the film -- the clock was running against
`video`.

Delivered job 82e03154-12c reported:

    render profile — total 993s: video 603s (61%), finishing 177s (18%),
    lipsync 91s (9%), ...

Its 350.5s `video` stage generated no video. It was this wait. The 91s left
over is not the cost of lip sync either; it is only the gap between the first
scene coming back and the last, the scenes being synced concurrently.

A profile that names the wrong stage is worse than no profile, because it is
what the next performance change is aimed by -- and the client, reading the
same events, sat on "Generating video" for six minutes with nothing moving.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")


class _SlowLipsync:
    """Answers only after the caller has had a chance to say what it is doing."""

    def available(self):
        return True

    async def sync(self, video, audio, is_cancelled=None):
        return "https://cdn/synced.mp4"


@pytest.fixture
def lipsync_on(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")


async def _stages(monkeypatch, tmp_path, tracks):
    import pipelines.idea2video as mod
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setattr(mod, "make_lipsync", lambda demo=False: _SlowLipsync())
    monkeypatch.setattr(mod, "_keeps_its_length", lambda a, b: True)

    async def fake_download(url, path):
        with open(path, "wb") as f:
            f.write(b"synced")
        return path

    monkeypatch.setattr(mod, "download_video", fake_download)

    clip = tmp_path / "scene0.mp4"
    clip.write_bytes(b"original")

    seen = []

    async def progress(stage, message, pct, data=None):
        seen.append((stage, message))

    await Idea2VideoPipeline("test-key")._lipsync_scenes(
        scene_paths=[str(clip)],
        dialogue_tracks=tracks,
        working_dir=str(tmp_path),
        progress=progress,
    )
    return seen


@pytest.mark.asyncio
async def test_the_pass_says_it_has_started_before_it_waits(
    lipsync_on, monkeypatch, tmp_path
):
    """The first emit must land BEFORE the provider is waited on, or the wait
    is charged to whatever the scene loop said last."""
    seen = await _stages(
        monkeypatch, tmp_path, [{"scene_index": 0, "audio_url": "https://cdn/v.mp3"}]
    )

    assert seen, "the lip-sync pass emitted nothing at all"
    assert seen[0][0] == "lipsync"
    assert "0/1" in seen[0][1], seen[0][1]


@pytest.mark.asyncio
async def test_completion_is_still_reported_after_it(
    lipsync_on, monkeypatch, tmp_path
):
    """The opening emit adds to the pass, it does not replace what was there:
    the client's per-stage message count is how its progress bar advances."""
    seen = await _stages(
        monkeypatch, tmp_path, [{"scene_index": 0, "audio_url": "https://cdn/v.mp3"}]
    )

    assert [stage for stage, _ in seen] == ["lipsync", "lipsync"]
    assert "1/1" in seen[-1][1]


@pytest.mark.asyncio
async def test_a_drama_with_no_speech_still_says_nothing(
    lipsync_on, monkeypatch, tmp_path
):
    """Naming a stage that is not going to run would put the film in `lipsync`
    for the rest of the render -- the same fault, pointed the other way."""
    assert await _stages(monkeypatch, tmp_path, []) == []
