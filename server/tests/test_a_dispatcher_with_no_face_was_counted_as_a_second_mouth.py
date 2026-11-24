"""Job bb6c6f1f: "Lena, Mira" was read as two visible speakers.

Lena is a dispatcher "heard only over a radio and never seen". The writer gave
her lines but no cast entry (a cast entry is a portrait), so every place that
asked the cast who is off-screen came back empty: lip sync refused the scene as
a two-hander and refunded it, and the storyboard was told nothing about her.
A speaker with no portrait cannot be shown.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines.idea2video import (  # noqa: E402
    _has_one_visible_speaker,
    _heard_only_names,
)

CAST = [
    SimpleNamespace(name="Mira", is_visible=True),
    SimpleNamespace(name="Tomas", is_visible=True),
]
LINES = [
    {"character": "Lena", "line": "Refuge, this is dispatch."},
    {"character": "Mira", "line": "I'm here."},
]


def test_a_speaker_with_no_cast_entry_is_heard_only():
    assert _heard_only_names(CAST, LINES) == {"lena"}


def test_the_scene_with_her_voice_has_one_mouth_to_drive():
    heard = _heard_only_names(CAST, LINES)
    assert not _has_one_visible_speaker(LINES, set())  # the old answer
    assert _has_one_visible_speaker(LINES, heard)


def test_a_marker_on_the_name_does_not_make_a_stranger():
    marked = [{"character": "Lena (O.S.)", "line": "x"}, {"character": "Mira", "line": "y"}]
    assert _heard_only_names(CAST, marked) == {"lena"}


def test_hidden_cast_members_still_count_and_a_visible_one_does_not():
    cast = CAST + [SimpleNamespace(name="Arif", is_visible=False)]
    assert _heard_only_names(cast, [{"character": "Tomas", "line": "x"}]) == {"arif"}


def test_with_no_cast_at_all_nothing_is_guessed():
    assert _heard_only_names([], LINES) == set()


import pytest  # noqa: E402


class _Syncer:
    def __init__(self):
        self.calls = 0

    def available(self):
        return True

    async def sync(self, video, audio, is_cancelled=None):
        self.calls += 1
        return "https://cdn/synced.mp4"


@pytest.mark.asyncio
async def test_the_pass_syncs_the_one_face_when_the_other_speaker_has_no_portrait(
    monkeypatch, tmp_path
):
    import pipelines.idea2video as mod
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    fake = _Syncer()
    monkeypatch.setattr(mod, "make_lipsync", lambda demo=False: fake)
    clip = tmp_path / "scene0.mp4"
    clip.write_bytes(b"original")
    tracks = [
        {"scene_index": 0, "character": "Lena", "line": "Refuge, this is dispatch.",
         "audio_url": "https://cdn/a.mp3", "start_seconds": 0.0, "end_seconds": 2.0},
        {"scene_index": 0, "character": "Mira", "line": "I'm here.",
         "audio_url": "https://cdn/b.mp3", "start_seconds": 2.5, "end_seconds": 3.5},
    ]

    async def progress(*a, **k):
        pass

    await Idea2VideoPipeline("test-key")._lipsync_scenes(
        scene_paths=[str(clip)], dialogue_tracks=[dict(t) for t in tracks],
        working_dir=str(tmp_path), progress=progress, characters=CAST,
    )
    assert fake.calls == 1
