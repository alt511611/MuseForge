"""Job e85c3f62, scene 2: the central event of the film was replaced by a still.

"What is that--" is 0.88 s. The redraw backend pads it to the endpoint's 5 s
floor and redraws the take from its first frame, so the seconds in which she
heaves the container open became five seconds of a woman frozen mid-pull with a
fixed grin while the door stayed where it was.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")


class _Syncer:
    def __init__(self, redraws):
        self.redraws_the_take = redraws
        self.calls = 0

    def available(self):
        return True

    async def sync(self, video, audio, is_cancelled=None):
        self.calls += 1
        return "https://cdn/synced.mp4"


async def _run(monkeypatch, tmp_path, redraws, seconds):
    import pipelines.idea2video as mod
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    fake = _Syncer(redraws)
    monkeypatch.setattr(mod, "make_lipsync", lambda demo=False: fake)
    clip = tmp_path / "scene0.mp4"
    clip.write_bytes(b"original")
    tracks = [{
        "scene_index": 0, "character": "Mira", "line": "What is that--",
        "audio_url": "https://cdn/a.mp3", "start_seconds": 0.0, "end_seconds": seconds,
    }]

    async def progress(*a, **k):
        pass

    await Idea2VideoPipeline("test-key")._lipsync_scenes(
        scene_paths=[str(clip)], dialogue_tracks=tracks,
        working_dir=str(tmp_path), progress=progress, characters=None,
    )
    return fake.calls


@pytest.mark.asyncio
async def test_a_redraw_is_not_spent_on_a_one_second_line(monkeypatch, tmp_path):
    assert await _run(monkeypatch, tmp_path, redraws=True, seconds=0.9) == 0


@pytest.mark.asyncio
async def test_a_redraw_is_still_made_for_a_line_that_fills_the_take(monkeypatch, tmp_path):
    assert await _run(monkeypatch, tmp_path, redraws=True, seconds=6.4) == 1


@pytest.mark.asyncio
async def test_an_editing_backend_syncs_a_short_line_as_ever(monkeypatch, tmp_path):
    assert await _run(monkeypatch, tmp_path, redraws=False, seconds=0.9) == 1
