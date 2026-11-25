"""Job 3570bab0: a two-hander lost lip sync on all three scenes.

``falai_h3`` redraws a scene from its first frame, so a scene with two people is
skipped and the fee refunded -- correct, and the customer got no lip sync in the
most common dialogue format. An editing backend keeps every shot. It is unproven
(a red mark above the lip appeared in the one clip tried), so it stands in only
when ``MUSEFORGE_LIPSYNC_MULTI_FALLBACK`` is on, and only for a redrawing backend.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as mod  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.idea2video import Idea2VideoPipeline, _edit_backend_for_crowded_scenes  # noqa: E402

CAST = [CharacterInScene(idx=i, name=n, static_features="a player", wardrobe="suit") for i, n in enumerate(["Elena", "Dorian"])]


class _Backend:
    def __init__(self, redraws):
        self.redraws_the_take = redraws
        self.calls = 0

    def available(self):
        return True

    async def sync(self, video, audio, is_cancelled=None):
        self.calls += 1
        return "https://cdn/synced.mp4"


def _two_hander():
    return [StoryboardShot(idx=0, visual_desc="Elena deals while Dorian watches", motion_desc="x",
                           shot_type="close-up", duration_seconds=4.0)]


async def _run(monkeypatch, tmp_path, redrawer, editor, flag):
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.setenv("FAL_KEY", "k")
    if flag:
        monkeypatch.setenv("MUSEFORGE_LIPSYNC_MULTI_FALLBACK", "1")
    else:
        monkeypatch.delenv("MUSEFORGE_LIPSYNC_MULTI_FALLBACK", raising=False)
    monkeypatch.setattr(mod, "make_lipsync", lambda demo=False: redrawer)
    import tools.falai_lipsync as fl
    monkeypatch.setattr(fl, "FalAILipsync", lambda key, demo=False: editor)
    clip = tmp_path / "scene0.mp4"
    clip.write_bytes(b"original")

    async def progress(*a, **k):
        pass

    await Idea2VideoPipeline("test-key")._lipsync_scenes(
        scene_paths=[str(clip)],
        dialogue_tracks=[{"scene_index": 0, "character": "Elena", "line": "Two hundred is in.",
                          "audio_url": "https://cdn/a.mp3", "start_seconds": 0.0, "end_seconds": 4.0}],
        working_dir=str(tmp_path), progress=progress,
        shots_by_clip={0: _two_hander()}, characters=CAST,
    )


@pytest.mark.asyncio
async def test_off_by_default_a_two_hander_keeps_its_unsynced_take(monkeypatch, tmp_path):
    redrawer, editor = _Backend(True), _Backend(False)
    await _run(monkeypatch, tmp_path, redrawer, editor, flag=False)
    assert redrawer.calls == 0 and editor.calls == 0


@pytest.mark.asyncio
async def test_with_the_flag_the_editing_backend_takes_the_two_hander(monkeypatch, tmp_path):
    redrawer, editor = _Backend(True), _Backend(False)
    await _run(monkeypatch, tmp_path, redrawer, editor, flag=True)
    assert redrawer.calls == 0 and editor.calls == 1


def test_the_fallback_never_replaces_a_backend_that_already_edits(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_MULTI_FALLBACK", "1")
    assert _edit_backend_for_crowded_scenes(_Backend(False)) is None
