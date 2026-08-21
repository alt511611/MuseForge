"""A line shorter than its scene must not cost the whole sync.

MuAPI's Sync Labs endpoint exposes no ``sync_mode`` and the provider's default
(cut_off) returns a clip as long as the AUDIO. The pipeline guarded the
runtime by discarding anything that came back short -- and a line is shorter
than its scene in nearly every scene ever written, so on the DEFAULT backend
that rejected the sync essentially every time. Measured on a delivered job:

    scene 0   take 16.08s   synced clip 4.96s   rejected
    scene 1   take 20.08s   synced clip 6.00s   rejected
    scene 2   take 24.08s   synced clip 3.92s   rejected

Three syncs bought, 633 seconds of render spent, no mouth driven, and the
delivered drama's only sign of it was three warnings in a log.

The seconds that came back missing are the END of the take, which the pipeline
still holds and which has nothing to sync anyway -- the line has stopped. They
are cut off the original and joined behind the synced head, so the scene keeps
the runtime it was costed at AND the mouth moves while there are words.

The second half of the same failure is in test_lipsync: the speech has to stay
in the MIX, because no tier of the assembly carries a clip's own audio to the
master.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as mod  # noqa: E402


DURATIONS = {}


@pytest.fixture
def measured(monkeypatch):
    """Stub the clip prober: these are byte files, not video."""
    DURATIONS.clear()
    monkeypatch.setattr(mod, "_clip_duration", lambda path: DURATIONS.get(path))
    return DURATIONS


@pytest.fixture
def editor(monkeypatch, tmp_path):
    """Record what the trim and the join were asked to do."""
    calls = {"trims": [], "joins": []}

    async def fake_trim(source, out, trim_start=0.0, trim_end=0.0):
        calls["trims"].append((source, trim_start, trim_end))
        with open(out, "wb") as f:
            f.write(b"remainder")
        DURATIONS[out] = DURATIONS[source] - trim_start
        return out

    async def fake_concat(paths, out):
        calls["joins"].append(list(paths))
        with open(out, "wb") as f:
            f.write(b"joined")
        DURATIONS[out] = sum(DURATIONS[p] for p in paths)
        return out

    monkeypatch.setattr(mod, "trim_clip", fake_trim)
    monkeypatch.setattr(mod, "concatenate_videos", fake_concat)
    return calls


def _clip(tmp_path, name, seconds):
    path = tmp_path / name
    path.write_bytes(b"clip")
    DURATIONS[str(path)] = seconds
    return str(path)


# ── restoring the take's own tail ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_seconds_the_provider_trimmed_come_back(measured, editor, tmp_path):
    """Scene 0 of the delivered job: a 4.96s line under a 16.08s take."""
    take = _clip(tmp_path, "scene_0.mp4", 16.08)
    synced = _clip(tmp_path, "scene_0_lipsync.mp4", 4.96)

    restored = await mod._restore_trimmed_length(
        take, synced, str(tmp_path / "rest.mp4"), str(tmp_path / "full.mp4")
    )

    assert restored is not None
    assert measured[restored] == pytest.approx(16.08), (
        "the scene came back at the length the customer was charged for"
    )
    # Cut from the point the sync stopped, and joined BEHIND the synced head.
    assert editor["trims"] == [(take, 4.96, 0.0)]
    assert editor["joins"] == [[synced, str(tmp_path / "rest.mp4")]]


@pytest.mark.asyncio
async def test_a_clip_that_kept_its_length_never_reaches_this_path(
    measured, editor, tmp_path
):
    """The fal backend pins sync_mode and comes back whole; so does a line that
    happens to run the length of its scene. Nothing to repair, nothing to join
    -- and _keeps_its_length lets those through before this is called."""
    take = _clip(tmp_path, "scene_0.mp4", 10.0)
    synced = _clip(tmp_path, "scene_0_lipsync.mp4", 10.0)

    assert mod._keeps_its_length(take, synced) is True
    assert await mod._restore_trimmed_length(
        take, synced, str(tmp_path / "rest.mp4"), str(tmp_path / "full.mp4")
    ) is None


@pytest.mark.asyncio
async def test_a_clip_that_is_not_a_short_head_is_refused(measured, editor, tmp_path):
    """Longer than the take, or a few frames of nothing: that is not the
    trim-to-audio this repairs, and assembling a scene out of it would deliver
    footage nobody chose."""
    take = _clip(tmp_path, "scene_0.mp4", 10.0)

    longer = _clip(tmp_path, "longer.mp4", 12.0)
    assert await mod._restore_trimmed_length(
        take, longer, str(tmp_path / "r1.mp4"), str(tmp_path / "f1.mp4")
    ) is None

    sliver = _clip(tmp_path, "sliver.mp4", 0.2)
    assert await mod._restore_trimmed_length(
        take, sliver, str(tmp_path / "r2.mp4"), str(tmp_path / "f2.mp4")
    ) is None

    assert editor["joins"] == []


@pytest.mark.asyncio
async def test_an_unmeasurable_clip_is_left_alone(measured, editor, tmp_path):
    take = _clip(tmp_path, "scene_0.mp4", 10.0)
    unknown = str(tmp_path / "unknown.mp4")

    assert await mod._restore_trimmed_length(
        take, unknown, str(tmp_path / "rest.mp4"), str(tmp_path / "full.mp4")
    ) is None


@pytest.mark.asyncio
async def test_a_trim_that_fails_open_does_not_play_the_scene_twice(
    measured, editor, tmp_path, monkeypatch
):
    """trim_clip returns its SOURCE when it cannot cut. Joining that behind the
    synced head would ship the whole scene a second time."""
    take = _clip(tmp_path, "scene_0.mp4", 16.0)
    synced = _clip(tmp_path, "scene_0_lipsync.mp4", 5.0)

    async def failing_trim(source, out, trim_start=0.0, trim_end=0.0):
        return source

    monkeypatch.setattr(mod, "trim_clip", failing_trim)

    assert await mod._restore_trimmed_length(
        take, synced, str(tmp_path / "rest.mp4"), str(tmp_path / "full.mp4")
    ) is None
    assert editor["joins"] == []


@pytest.mark.asyncio
async def test_a_join_that_comes_out_short_is_not_shipped(
    measured, editor, tmp_path, monkeypatch
):
    """The guarantee this whole path exists to protect: whatever happens, the
    scene handed back is as long as the take it replaces."""
    take = _clip(tmp_path, "scene_0.mp4", 16.0)
    synced = _clip(tmp_path, "scene_0_lipsync.mp4", 5.0)

    async def short_concat(paths, out):
        with open(out, "wb") as f:
            f.write(b"joined")
        DURATIONS[out] = 9.0
        return out

    monkeypatch.setattr(mod, "concatenate_videos", short_concat)

    assert await mod._restore_trimmed_length(
        take, synced, str(tmp_path / "rest.mp4"), str(tmp_path / "full.mp4")
    ) is None


# ── and end to end through the sync pass ────────────────────────────────────


class _TrimmingLipsync:
    """A provider that behaves like MuAPI's default: video cut to the line."""

    def available(self):
        return True

    async def sync(self, video, audio, is_cancelled=None):
        return "https://cdn/synced.mp4"


@pytest.mark.asyncio
async def test_the_scene_is_synced_instead_of_discarded(
    measured, editor, tmp_path, monkeypatch
):
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.setattr(mod, "make_lipsync", lambda demo=False: _TrimmingLipsync())

    take = _clip(tmp_path, "scene_0.mp4", 12.0)

    async def fake_download(url, path):
        with open(path, "wb") as f:
            f.write(b"synced")
        DURATIONS[path] = 4.0  # the provider trimmed it to the line
        return path

    monkeypatch.setattr(mod, "download_video", fake_download)

    scene_paths = [take]
    tracks = [{"scene_index": 0, "line": "Söz.", "audio_url": "https://cdn/voice.mp3"}]

    async def progress(*a, **kw):
        return None

    pipeline = mod.Idea2VideoPipeline("test-key-not-real")
    synced = await pipeline._lipsync_scenes(
        scene_paths=scene_paths,
        dialogue_tracks=tracks,
        working_dir=str(tmp_path),
        progress=progress,
    )

    assert synced == [0], "the sync was paid for and thrown away"
    assert scene_paths[0].endswith("scene_0_lipsync_full.mp4")
    assert measured[scene_paths[0]] == pytest.approx(12.0)
    assert tracks[0].get("audio_url"), "the line still has to be mixed"
