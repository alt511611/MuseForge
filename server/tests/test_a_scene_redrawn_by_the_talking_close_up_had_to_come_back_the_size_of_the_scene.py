"""MUSEFORGE_LIPSYNC_PROVIDER=falai_h3: the scene is redrawn from a still.

Measured against the three backends that edit the clip they are handed, this
one followed the voice (mouth motion vs audio r=+0.59 against +0.11..+0.21) and
came back in 18 s instead of 66-206 s. What it costs is that it does not edit
the take, it makes a new one -- so three things that the editing backends never
had to do are tested here: hand over a STILL, pad a short line to the
endpoint's 5 s floor, and give back a clip the SIZE of the scene (the join
copies packets on the assumption that every clip shares dimensions).
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fal_client

import tools.falai_h3_lipsync as h3
import tools.muapi_lipsync as lipsync_mod

SCENE = "/jobs/x/scene_0.mp4"
LINE = "https://fal/line.mp3"
H3_CLIP = "https://fal/h3.mp4"


class _Handle:
    request_id = "req-h3"


class _Client:
    """Just enough of fal_client.AsyncClient for fal_generate to run for real."""

    def __init__(self):
        self.uploads = []
        self.submitted = []

    async def upload_file(self, path):
        self.uploads.append(path)
        return f"https://fal/uploaded/{os.path.basename(path)}"

    async def submit(self, endpoint, arguments):
        self.submitted.append((endpoint, arguments))
        return _Handle()

    async def status(self, endpoint, request_id, with_logs=False):
        return fal_client.Completed(logs=None, metrics={})

    async def result(self, endpoint, request_id):
        return {"video": {"url": H3_CLIP}}


@pytest.fixture
def provider(monkeypatch, tmp_path):
    p = h3.FalAIH3Lipsync("key")
    p.client = _Client()

    async def first_frame(video, out):
        open(out, "wb").write(b"png")
        return True

    async def seconds(path):
        return 9.0

    async def size(path):
        return (1280, 720)

    monkeypatch.setattr(h3, "_first_frame", first_frame)
    monkeypatch.setattr(h3, "_probe_seconds", seconds)
    monkeypatch.setattr(h3, "_probe_size", size)
    monkeypatch.setattr(os.path, "isfile", lambda p_: True if p_ == SCENE else os.path.exists(p_))
    return p


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


def test_the_scene_is_redrawn_from_its_first_frame_and_the_line(provider):
    url = _run(provider.sync(SCENE, LINE))
    endpoint, payload = provider.client.submitted[0]
    assert endpoint == "minimax/h3-max/lip-sync/image-to-video"
    assert payload["image_url"].endswith("first_frame.png")
    assert payload["audio_url"] == LINE
    assert payload["resolution"] == "768P"
    assert payload["enable_transcription"] is True
    assert url == H3_CLIP


def test_a_line_shorter_than_the_floor_is_padded_not_refused(provider, monkeypatch):
    padded = []

    async def short(path):
        return 3.2

    async def pad(audio, out, seconds):
        padded.append((audio, seconds))
        open(out, "wb").write(b"mp3")
        return True

    monkeypatch.setattr(h3, "_probe_seconds", short)
    monkeypatch.setattr(h3, "_pad_audio", pad)
    _run(provider.sync(SCENE, LINE))
    assert padded == [(LINE, 5.0)]
    assert provider.client.submitted[0][1]["audio_url"].endswith("audio_padded.mp3")


def test_a_line_that_already_clears_the_floor_is_sent_as_it_is(provider, monkeypatch):
    async def no_pad(*a):
        raise AssertionError("padded a 9 s line")

    monkeypatch.setattr(h3, "_pad_audio", no_pad)
    _run(provider.sync(SCENE, LINE))
    assert provider.client.submitted[0][1]["audio_url"] == LINE


def test_a_clip_in_another_size_is_conformed_to_the_scenes_size(provider, monkeypatch):
    sizes = {SCENE: (1280, 720), H3_CLIP: (1344, 768)}
    conformed = []

    async def size(path):
        return sizes[path]

    async def conform(video, want, out):
        conformed.append((video, want))
        open(out, "wb").write(b"mp4")
        return True

    monkeypatch.setattr(h3, "_probe_size", size)
    monkeypatch.setattr(h3, "_conform", conform)
    url = _run(provider.sync(SCENE, LINE))
    assert conformed == [(H3_CLIP, (1280, 720))]
    assert url.endswith("conformed.mp4")  # the re-upload, not the stranger


def test_a_clip_already_the_scenes_size_is_returned_untouched(provider):
    assert _run(provider.sync(SCENE, LINE)) == H3_CLIP
    assert all(not u.endswith("conformed.mp4") for u in provider.client.uploads)


def test_a_clip_that_cannot_be_conformed_keeps_the_take(provider, monkeypatch):
    async def size(path):
        return (1280, 720) if path == SCENE else (1344, 768)

    async def conform(*a):
        return False

    monkeypatch.setattr(h3, "_probe_size", size)
    monkeypatch.setattr(h3, "_conform", conform)
    assert _run(provider.sync(SCENE, LINE)) is None


def test_the_ticket_reaches_the_ledger_before_the_poll(provider):
    seen = []
    _run(provider.sync(SCENE, LINE, on_submitted=seen.append))
    assert seen == ["req-h3"]


def test_every_failure_is_a_lost_mouth_not_a_lost_job(provider, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("fal is down")

    monkeypatch.setattr(h3, "fal_generate", boom)
    assert _run(provider.sync(SCENE, LINE)) is None


def test_no_key_means_the_scene_keeps_its_take(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    p = h3.FalAIH3Lipsync("")
    assert p.available() is False
    assert _run(p.sync(SCENE, LINE)) is None


def test_an_unknown_resolution_falls_back_instead_of_422ing_every_scene(monkeypatch):
    monkeypatch.setenv("FALAI_H3_LIPSYNC_RESOLUTION", "4k-ultra")
    assert h3._resolution() == "768P"
    monkeypatch.setenv("FALAI_H3_LIPSYNC_RESOLUTION", "1080p")
    assert h3._resolution() == "1080P"


# ── selection ────────────────────────────────────────────────────────────────


def test_it_is_selectable_without_disturbing_the_others(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "k")
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_PROVIDER", "falai_h3")
    assert type(lipsync_mod.make_lipsync()).__name__ == "FalAIH3Lipsync"
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_PROVIDER", "falai")
    assert type(lipsync_mod.make_lipsync()).__name__ == "FalAILipsync"
    monkeypatch.delenv("MUSEFORGE_LIPSYNC_PROVIDER")
    assert type(lipsync_mod.make_lipsync()).__name__ == "MuAPILipsync"


def test_every_selection_point_reads_the_same_list():
    assert "falai_h3" in lipsync_mod.LIPSYNC_PROVIDERS
    import pipelines.idea2video as pipeline

    assert pipeline.LIPSYNC_PROVIDERS is lipsync_mod.LIPSYNC_PROVIDERS


def test_readiness_is_the_fal_key_not_the_muapi_key(monkeypatch):
    # Imported here, not at the top: this file is collected early, and api reads
    # its environment at import -- before the modules that set it have run.
    import api

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_PROVIDER", "falai_h3")
    monkeypatch.setenv("MUAPI_KEY", "present")
    monkeypatch.delenv("FAL_KEY", raising=False)
    assert api._lipsync_configured() is False
    monkeypatch.setenv("FAL_KEY", "present")
    assert api._lipsync_configured() is True
