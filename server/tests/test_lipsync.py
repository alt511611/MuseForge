"""Lip sync: drive the mouth from the dialogue instead of playing it over the top.

The two things that must not regress:

1. A scene whose lips were synced must NOT also have that same speech mixed
   over it by add_background_music — the audio is baked into the clip, so
   overlaying it again plays every line twice, slightly out of phase.
2. Subtitles must survive: the caption text stays on the track even though the
   audio is handed to the picture.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as idea2video_mod  # noqa: E402
import tools.falai_lipsync as lipsync_mod  # noqa: E402


def _tracks():
    """Two scenes speak, one is silent — mirrors the voice generator's shape
    (combined audio attached to a scene's FIRST line only)."""
    return [
        {"character": "Kemal", "line": "Bu kokuyu unutma.", "audio_url": "https://cdn/s0.mp3", "scene_index": 0},
        {"character": "Deniz", "line": "Unutmam.", "scene_index": 0},
        {"character": "Deniz", "line": "Söz.", "audio_url": "https://cdn/s2.mp3", "scene_index": 2},
    ]


async def _run(monkeypatch, tmp_path, sync_results, enabled=True, demo=False):
    """sync_results: {scene_index: synced_url or None}."""
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1" if enabled else "0")
    monkeypatch.setenv("FAL_KEY", "fake-fal-key")

    sync_calls = []

    async def fake_sync(self, video_path_or_url, audio_url, is_cancelled=None):
        sync_calls.append((video_path_or_url, audio_url))
        for idx, url in sync_results.items():
            if f"scene_{idx}" in str(video_path_or_url):
                return url
        return None

    async def fake_download_video(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"synced bytes")
        return path

    monkeypatch.setattr(lipsync_mod.FalAILipsync, "sync", fake_sync)
    monkeypatch.setattr(idea2video_mod, "download_video", fake_download_video)

    scene_paths = [str(tmp_path / f"scene_{i}.mp4") for i in range(3)]
    for p in scene_paths:
        with open(p, "wb") as f:
            f.write(b"original bytes")
    tracks = _tracks()

    async def progress(*a, **kw):
        return None

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real", demo=demo)
    synced = await pipeline._lipsync_scenes(
        scene_paths=scene_paths,
        dialogue_tracks=tracks,
        working_dir=str(tmp_path),
        progress=progress,
    )
    return synced, scene_paths, tracks, sync_calls


@pytest.mark.asyncio
async def test_synced_scene_audio_is_not_mixed_a_second_time(monkeypatch, tmp_path):
    synced, scene_paths, tracks, sync_calls = await _run(
        monkeypatch, tmp_path, {0: "https://cdn/s0_synced.mp4", 2: "https://cdn/s2_synced.mp4"}
    )

    assert synced == [0, 2]
    assert len(sync_calls) == 2, "One request per SPEAKING scene, not per line"

    # The clips concatenation reads must now be the synced ones.
    assert scene_paths[0].endswith("scene_0_lipsync.mp4")
    assert scene_paths[2].endswith("scene_2_lipsync.mp4")
    assert scene_paths[1].endswith("scene_1.mp4"), "A silent scene must be left alone"

    # The mixer skips rows without audio_url — that is how double speech is avoided.
    assert all("audio_url" not in t for t in tracks if t["scene_index"] in (0, 2))
    assert all(t.get("lipsynced") for t in tracks if t["scene_index"] in (0, 2))

    # ...but the words survive for the subtitle burn-in.
    assert [t["line"] for t in tracks] == ["Bu kokuyu unutma.", "Unutmam.", "Söz."]


@pytest.mark.asyncio
async def test_one_scene_failing_does_not_cost_the_others(monkeypatch, tmp_path):
    """Fail-open is per scene: a provider hiccup on scene 0 must not silence
    scene 2, and scene 0 must keep its original clip WITH its audio still
    queued for the mixer."""
    synced, scene_paths, tracks, _ = await _run(
        monkeypatch, tmp_path, {0: None, 2: "https://cdn/s2_synced.mp4"}
    )

    assert synced == [2]
    assert scene_paths[0].endswith("scene_0.mp4"), "Unsynced scene keeps its original clip"
    scene0 = [t for t in tracks if t["scene_index"] == 0]
    assert scene0[0]["audio_url"] == "https://cdn/s0.mp3", (
        "A scene that could not be synced must still get its voice mixed over "
        "the top — otherwise the failure turns into silence"
    )
    assert scene_paths[2].endswith("scene_2_lipsync.mp4")


@pytest.mark.asyncio
async def test_disabled_and_demo_do_nothing(monkeypatch, tmp_path):
    synced, scene_paths, tracks, sync_calls = await _run(
        monkeypatch, tmp_path, {0: "https://cdn/s0_synced.mp4"}, enabled=False
    )
    assert synced == [] and sync_calls == []
    assert tracks[0]["audio_url"] == "https://cdn/s0.mp3"

    synced, _, _, sync_calls = await _run(
        monkeypatch, tmp_path, {0: "https://cdn/s0_synced.mp4"}, demo=True
    )
    assert synced == [] and sync_calls == [], "Demo mode never makes a paid call"


def test_sync_mode_preserves_clip_length_not_the_providers_default(monkeypatch):
    """cut_off (fal's default) trims the VIDEO to the audio, which would let a
    short line shorten a scene the customer already paid seconds for."""
    assert lipsync_mod.SYNC_MODE == "silence"


@pytest.mark.asyncio
async def test_missing_fal_key_skips_quietly(monkeypatch, tmp_path):
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.delenv("FAL_KEY", raising=False)

    async def progress(*a, **kw):
        return None

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    tracks = _tracks()
    synced = await pipeline._lipsync_scenes(
        scene_paths=["a.mp4", "b.mp4", "c.mp4"],
        dialogue_tracks=tracks,
        working_dir=str(tmp_path),
        progress=progress,
    )
    assert synced == []
    assert tracks[0]["audio_url"] == "https://cdn/s0.mp3", (
        "An unconfigured deployment must fall back to the mixed voice layer, "
        "not drop the dialogue entirely"
    )


@pytest.mark.asyncio
async def test_deployment_flag_alone_does_not_sync_an_unpaid_job(monkeypatch, tmp_path):
    """The env flag says the deployment CAN sync; the job's own opt-in says the
    customer paid for it. A job that did not opt in must not be synced just
    because the server has the feature switched on."""
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.setenv("FAL_KEY", "fake-fal-key")

    sync_calls = []

    async def fake_sync(self, video_path_or_url, audio_url, is_cancelled=None):
        sync_calls.append(video_path_or_url)
        return "https://cdn/synced.mp4"

    monkeypatch.setattr(lipsync_mod.FalAILipsync, "sync", fake_sync)

    async def progress(*a, **kw):
        return None

    tracks = _tracks()
    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="test-key-not-real")
    synced = await pipeline._lipsync_scenes(
        scene_paths=["a.mp4", "b.mp4", "c.mp4"],
        dialogue_tracks=tracks,
        working_dir=str(tmp_path),
        progress=progress,
        requested=False,
    )
    assert synced == [] and sync_calls == []
    assert tracks[0]["audio_url"] == "https://cdn/s0.mp3"
