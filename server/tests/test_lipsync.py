"""Lip sync: drive the mouth from the dialogue instead of playing it over the top.

The two things that must not regress:

1. A scene whose lips were synced must still have its speech MIXED. The clip
   comes back with the line baked into its own audio track, and this file used
   to assert that the mixer therefore skipped the row — on the theory that
   overlaying it again would play every line twice. Nothing downstream can
   deliver that baked audio: every tier of concatenate_videos drops audio on
   purpose, and mix_audio_layers maps the master's video stream alone. So the
   row being skipped did not stop the line playing twice, it stopped it
   playing at all.
2. Subtitles must survive: the caption text stays on the track, as does the
   voice the mouth was driven from.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as idea2video_mod  # noqa: E402
import tools.muapi_lipsync as lipsync_mod  # noqa: E402


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
    # MuAPI is the default backend; fal.ai stays selectable (tested below).
    monkeypatch.delenv("MUSEFORGE_LIPSYNC_PROVIDER", raising=False)
    monkeypatch.setenv("MUAPI_KEY", "fake-muapi-key")

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

    monkeypatch.setattr(lipsync_mod.MuAPILipsync, "sync", fake_sync)
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
async def test_a_synced_scene_still_has_its_speech_mixed(monkeypatch, tmp_path):
    synced, scene_paths, tracks, sync_calls = await _run(
        monkeypatch, tmp_path, {0: "https://cdn/s0_synced.mp4", 2: "https://cdn/s2_synced.mp4"}
    )

    assert synced == [0, 2]
    assert len(sync_calls) == 2, "One request per SPEAKING scene, not per line"

    # The clips concatenation reads must now be the synced ones.
    assert scene_paths[0].endswith("scene_0_lipsync.mp4")
    assert scene_paths[2].endswith("scene_2_lipsync.mp4")
    assert scene_paths[1].endswith("scene_1.mp4"), "A silent scene must be left alone"

    # The mixer reads audio_url and nothing else. Assembly cannot carry the
    # clip's own audio to the master, so a row without it is a scene that
    # ships silent behind a mouth that is moving.
    voiced = [t for t in tracks if t["scene_index"] in (0, 2) and t.get("synced_audio_url")]
    assert len(voiced) == 2
    assert all(t.get("audio_url") for t in voiced), (
        "the synced scene's line was dropped from the mix and nothing else "
        "delivers it"
    )
    assert all(t.get("lipsynced") for t in voiced)

    # ...and the words survive for the subtitle burn-in.
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


def test_muapi_is_the_default_backend_and_fal_stays_selectable(monkeypatch):
    """Lip sync was the last reason a deployment needed a second vendor: video,
    images, voice and music all run on MuAPI, and this one call forced a fal.ai
    key on top."""
    from tools.falai_lipsync import FalAILipsync

    monkeypatch.setenv("MUAPI_KEY", "k")
    monkeypatch.delenv("MUSEFORGE_LIPSYNC_PROVIDER", raising=False)
    assert isinstance(lipsync_mod.make_lipsync(), lipsync_mod.MuAPILipsync)

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_PROVIDER", "falai")
    assert isinstance(lipsync_mod.make_lipsync(), FalAILipsync)


def test_a_shortened_clip_is_rejected(tmp_path):
    """Sync Labs' own default trims the VIDEO down to the audio, which would
    let a short line shorten a scene the customer already paid seconds for.
    The fal backend pins sync_mode to stop that; MuAPI's endpoint exposes no
    such knob, so the length is verified after the fact instead."""
    from unittest.mock import patch

    original, candidate = str(tmp_path / "a.mp4"), str(tmp_path / "b.mp4")

    def _durations(path):
        return {original: 8.0, candidate: 3.0}.get(path)

    with patch.object(idea2video_mod, "_clip_duration", _durations):
        assert not idea2video_mod._keeps_its_length(original, candidate)

    # A re-encode moves the last frame by a hair; that is not a trim.
    with patch.object(idea2video_mod, "_clip_duration", lambda p: 8.0 if p == original else 7.9):
        assert idea2video_mod._keeps_its_length(original, candidate)


def test_the_length_check_fails_open_when_it_cannot_measure(tmp_path):
    """Refusing every sync on a probe failure would quietly disable a feature
    the customer paid for. The check exists to catch a provider that trims to
    the audio -- unmistakable -- not to police rounding."""
    from unittest.mock import patch

    with patch.object(idea2video_mod, "_clip_duration", lambda p: None):
        assert idea2video_mod._keeps_its_length("a.mp4", "b.mp4")


@pytest.mark.asyncio
async def test_missing_provider_key_skips_quietly(monkeypatch, tmp_path):
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.delenv("MUSEFORGE_LIPSYNC_PROVIDER", raising=False)
    monkeypatch.setenv("MUAPI_KEY", "")
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

    monkeypatch.setattr(lipsync_mod.MuAPILipsync, "sync", fake_sync)

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
