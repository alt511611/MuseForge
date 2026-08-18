"""Lip sync and reaction shots are not a choice between two features.

plan_scene_shots refused the second angle outright whenever lip sync was on:
the sync pass drives a mouth across the clip it is given and cannot see a cut
in the middle of one. So turning lip sync on flattened every peak scene to a
single framing -- on exactly the runs that care most about performance, and
between the two things users ask for together.

The refusal was aimed at the wrong half of the cut. A reaction shot is the
other character LISTENING; there is no mouth in it to drive. The cutaway is
now held back from the sync and concatenated again afterwards, so the master
gets its mouth and the scene keeps its angle.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines.idea2video import _reaction_tail_seconds  # noqa: E402


# ── measuring the tail ──────────────────────────────────────────────────────


def test_a_scene_with_no_cutaway_reports_no_tail():
    """The overwhelming majority of scenes. This path has to stay exactly as
    it was: one clip, one sync request, no splitting."""
    assert _reaction_tail_seconds([{"role": "master", "deliver_seconds": 0.0}]) == 0.0
    assert _reaction_tail_seconds([]) == 0.0
    assert _reaction_tail_seconds(None) == 0.0


def test_a_two_angle_scene_reports_the_cutaway_s_delivered_length():
    shots = [
        {"role": "master", "deliver_seconds": 8.0},
        {"role": "reaction", "deliver_seconds": 2.0},
    ]
    assert _reaction_tail_seconds(shots) == 2.0


def test_only_the_tail_counts_not_a_reaction_anywhere_in_the_list():
    """The split is positional -- it cuts the END of the assembled clip -- so a
    reaction that is not last must not be measured as if it were."""
    shots = [
        {"role": "reaction", "deliver_seconds": 2.0},
        {"role": "master", "deliver_seconds": 8.0},
    ]
    assert _reaction_tail_seconds(shots) == 0.0


def test_a_cutaway_with_no_recorded_length_is_not_guessed():
    """Splitting on a guessed boundary would cut the master mid-word. Falling
    back to syncing the whole clip is the old behaviour, which is survivable."""
    assert _reaction_tail_seconds([
        {"role": "master", "deliver_seconds": 8.0},
        {"role": "reaction"},
    ]) == 0.0


def test_a_tail_too_short_to_be_a_shot_is_not_worth_splitting_for():
    assert _reaction_tail_seconds([
        {"role": "master", "deliver_seconds": 9.7},
        {"role": "reaction", "deliver_seconds": 0.3},
    ]) == 0.0


# ── the sync itself ─────────────────────────────────────────────────────────


class _FakeLipsync:
    def __init__(self):
        self.synced = []

    def available(self):
        return True

    async def sync(self, video, audio, is_cancelled=None):
        self.synced.append(video)
        return "https://cdn/synced.mp4"


@pytest.fixture
def lipsync_on(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")


async def _run_lipsync(pipeline, monkeypatch, tmp_path, tails, joined=None):
    import pipelines.idea2video as mod

    fake = _FakeLipsync()
    monkeypatch.setattr(mod, "make_lipsync", lambda demo=False: fake)

    async def fake_download(url, path):
        with open(path, "wb") as f:
            f.write(b"synced")
        return path

    async def fake_split(source, head_path, tail_path, tail_seconds):
        with open(head_path, "wb") as f:
            f.write(b"head")
        with open(tail_path, "wb") as f:
            f.write(b"tail")
        return head_path, tail_path

    async def fake_concat(paths, out):
        (joined if joined is not None else []).extend(paths)
        with open(out, "wb") as f:
            f.write(b"joined")
        return out

    monkeypatch.setattr(mod, "download_video", fake_download)
    monkeypatch.setattr(mod, "_split_off_tail", fake_split)
    monkeypatch.setattr(mod, "concatenate_videos", fake_concat)
    monkeypatch.setattr(mod, "_keeps_its_length", lambda a, b: True)

    clip = tmp_path / "scene0.mp4"
    clip.write_bytes(b"original")
    scene_paths = [str(clip)]
    tracks = [{"scene_index": 0, "audio_url": "https://cdn/voice.mp3"}]

    async def progress(*a, **kw):
        return None

    synced = await pipeline._lipsync_scenes(
        scene_paths=scene_paths,
        dialogue_tracks=tracks,
        working_dir=str(tmp_path),
        progress=progress,
        reaction_tails=tails,
    )
    return fake, scene_paths, synced


@pytest.mark.asyncio
async def test_only_the_master_is_sent_to_the_sync_provider(
    lipsync_on, monkeypatch, tmp_path
):
    from pipelines.idea2video import Idea2VideoPipeline

    joined = []
    pipeline = Idea2VideoPipeline("test-key")
    fake, scene_paths, synced = await _run_lipsync(
        pipeline, monkeypatch, tmp_path, {0: 2.0}, joined
    )

    assert synced == [0]
    assert fake.synced[0].endswith("scene_0_master.mp4"), fake.synced
    # And the cutaway is put back, in order, so the scene keeps its length.
    assert len(joined) == 2 and joined[1].endswith("scene_0_reaction.mp4")
    assert scene_paths[0].endswith("scene_0_lipsync_cut.mp4")


@pytest.mark.asyncio
async def test_a_single_angle_scene_is_sent_whole_exactly_as_before(
    lipsync_on, monkeypatch, tmp_path
):
    from pipelines.idea2video import Idea2VideoPipeline

    joined = []
    pipeline = Idea2VideoPipeline("test-key")
    fake, scene_paths, synced = await _run_lipsync(
        pipeline, monkeypatch, tmp_path, {0: 0.0}, joined
    )

    assert synced == [0]
    assert fake.synced[0].endswith("scene0.mp4")
    assert joined == []  # nothing was split, so nothing is rejoined
    assert scene_paths[0].endswith("scene_0_lipsync.mp4")
