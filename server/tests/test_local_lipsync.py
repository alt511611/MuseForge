"""The self-hosted lip-sync backend: MUSEFORGE_LIPSYNC_PROVIDER=local.

What has to hold for this to be safe to switch a deployment onto:

1. It is SELECTABLE without disturbing the other two. The default is still
   MuAPI and fal.ai is still one env var away.
2. Readiness is its BASE URL, not a key. It authenticates with nothing, and
   api._lipsync_configured used to answer with a key name -- which would have
   let a local deployment advertise (and charge for) a stage it had nowhere to
   send, and hidden the toggle from one that could run it perfectly well.
3. It returns a URL. The caller hands the result straight to download_video(),
   which fetches over HTTP; a filesystem path here reads as success and then
   fails in the caller on every scene that speaks.
4. Concurrency is capped. idea2video syncs scenes concurrently, which is right
   against a hosted fleet and wrong against one GPU.
5. Every failure is still a lost mouth, never a lost job.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import tools.local_lipsync as local_mod  # noqa: E402
import tools.muapi_lipsync as lipsync_mod  # noqa: E402

BASE = "http://gpu-box:8189"


@pytest.fixture(autouse=True)
def _clean_slot():
    """The semaphore is module state shared across instances on purpose (one
    box), so a test that fills it must not leak into the next one."""
    local_mod._gpu_slot = None
    yield
    local_mod._gpu_slot = None


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    """Stands in for httpx.AsyncClient as an async context manager."""

    def __init__(self, posts=None, gets=None, on_post=None):
        self.posts = list(posts or [])
        self.gets = list(gets or [])
        self.post_calls = []
        self.get_calls = []
        self._on_post = on_post

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data=None, files=None, json=None):
        self.post_calls.append({"url": url, "data": data, "files": files, "json": json})
        if self._on_post:
            await self._on_post()
        if not self.posts:
            return _FakeResponse({})
        return self.posts.pop(0)

    async def get(self, url):
        self.get_calls.append(url)
        return self.gets.pop(0)


def _install(monkeypatch, client):
    monkeypatch.setattr(local_mod.httpx, "AsyncClient", lambda **kw: client)
    return client


# ── selection ────────────────────────────────────────────────────────────────


def test_local_is_selectable_without_disturbing_the_other_two(monkeypatch):
    from tools.falai_lipsync import FalAILipsync

    monkeypatch.setenv("MUAPI_KEY", "k")
    monkeypatch.setenv("MUSEFORGE_LOCAL_LIPSYNC_URL", BASE)

    monkeypatch.delenv("MUSEFORGE_LIPSYNC_PROVIDER", raising=False)
    assert isinstance(lipsync_mod.make_lipsync(), lipsync_mod.MuAPILipsync)

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_PROVIDER", "falai")
    assert isinstance(lipsync_mod.make_lipsync(), FalAILipsync)

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_PROVIDER", "local")
    made = lipsync_mod.make_lipsync()
    assert isinstance(made, local_mod.LocalLipsync)
    assert made.base_url == BASE


def test_readiness_is_the_base_url_not_a_key(monkeypatch):
    """A backend that authenticates with nothing cannot be gated on a key.

    Answering with MUAPI_KEY here would let a local deployment holding a stale
    MuAPI key advertise a stage it has nowhere to send, and hide the toggle
    from one that has a GPU but no vendor account at all.
    """
    import api

    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_PROVIDER", "local")

    monkeypatch.setenv("MUAPI_KEY", "a-key-this-provider-never-calls")
    monkeypatch.delenv("MUSEFORGE_LOCAL_LIPSYNC_URL", raising=False)
    assert not api._lipsync_configured(), "A key is not a service"

    monkeypatch.setenv("MUAPI_KEY", "")
    monkeypatch.setenv("MUSEFORGE_LOCAL_LIPSYNC_URL", BASE)
    assert api._lipsync_configured(), "No vendor key is needed to drive a mouth here"


def test_an_unconfigured_url_is_unavailable_rather_than_an_error(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_LOCAL_LIPSYNC_URL", raising=False)
    assert not local_mod.LocalLipsync("").available()
    assert not local_mod.LocalLipsync(BASE, demo=True).available(), "Demo pays nothing"
    assert local_mod.LocalLipsync(BASE).available()


# ── the happy paths ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_finished_run_comes_back_as_a_url(monkeypatch, tmp_path):
    """download_video() fetches over HTTP, so a path here would fail in the
    caller on every scene that speaks."""
    video = tmp_path / "scene_0.mp4"
    video.write_bytes(b"take")

    client = _install(
        monkeypatch,
        _FakeClient(posts=[_FakeResponse({"video_url": f"{BASE}/outputs/0.mp4"})]),
    )

    got = await local_mod.LocalLipsync(BASE).sync(str(video), "https://cdn/s0.mp3")

    assert got == f"{BASE}/outputs/0.mp4"
    assert got.startswith("http"), "The caller downloads this, it cannot be a path"
    # The clip was on disk and went as a file; the voice was already a URL and
    # was passed by reference rather than round-tripped through this process.
    sent = client.post_calls[0]
    assert "video" in sent["files"] and "audio" not in (sent["files"] or {})
    assert sent["data"]["audio_url"] == "https://cdn/s0.mp3"
    assert sent["data"]["sync_mode"] == local_mod.SYNC_MODE


@pytest.mark.asyncio
async def test_a_relative_result_is_resolved_against_the_service(monkeypatch, tmp_path):
    """A service answering "/outputs/x.mp4" should need no extra configuration."""
    video = tmp_path / "scene_1.mp4"
    video.write_bytes(b"take")

    _install(monkeypatch, _FakeClient(posts=[_FakeResponse({"video_url": "/outputs/x.mp4"})]))

    got = await local_mod.LocalLipsync(BASE).sync(str(video), "https://cdn/a.mp3")
    assert got == f"{BASE}/outputs/x.mp4"


@pytest.mark.asyncio
async def test_a_queued_run_is_polled_until_it_finishes(monkeypatch, tmp_path):
    video = tmp_path / "scene_2.mp4"
    video.write_bytes(b"take")

    client = _install(
        monkeypatch,
        _FakeClient(
            posts=[_FakeResponse({"job_id": "j-7"})],
            gets=[
                _FakeResponse({"status": "queued"}),
                _FakeResponse({"status": "processing"}),
                _FakeResponse({"status": "completed", "video_url": "/outputs/2.mp4"}),
            ],
        ),
    )
    # Patch through the module's own reference, and keep a handle on the real
    # sleep first: `local_mod.asyncio` IS asyncio, so a replacement that called
    # `asyncio.sleep` would call itself.
    real_sleep = asyncio.sleep
    monkeypatch.setattr(local_mod.asyncio, "sleep", lambda *_: real_sleep(0))

    got = await local_mod.LocalLipsync(BASE).sync(str(video), "https://cdn/a.mp3")

    assert got == f"{BASE}/outputs/2.mp4"
    assert client.get_calls == [f"{BASE}/lipsync/j-7"] * 3


@pytest.mark.asyncio
async def test_a_voice_on_disk_is_uploaded_too(monkeypatch, tmp_path):
    """The ElevenLabs voice backend returns BYTES and writes them into the job
    directory, so audio_url carries a LOCAL PATH on that deployment. Passed as
    a URL it would fail every time, fail open, and lip sync would silently
    never happen -- the same trap tools/muapi_lipsync documents."""
    video = tmp_path / "scene_0.mp4"
    video.write_bytes(b"take")
    audio = tmp_path / "scene_0.mp3"
    audio.write_bytes(b"line")

    client = _install(
        monkeypatch, _FakeClient(posts=[_FakeResponse({"video_url": "/o/0.mp4"})])
    )

    got = await local_mod.LocalLipsync(BASE).sync(str(video), str(audio))

    assert got == f"{BASE}/o/0.mp4"
    assert set(client.post_calls[0]["files"]) == {"video", "audio"}


# ── the failures, all of which keep the job ──────────────────────────────────


@pytest.mark.asyncio
async def test_a_service_that_is_down_costs_a_mouth_not_a_job(monkeypatch, tmp_path):
    video = tmp_path / "scene_0.mp4"
    video.write_bytes(b"take")

    class _Dead(_FakeClient):
        async def post(self, *a, **kw):
            raise ConnectionError("connection refused")

    _install(monkeypatch, _Dead())

    assert await local_mod.LocalLipsync(BASE).sync(str(video), "https://cdn/a.mp3") is None


@pytest.mark.asyncio
async def test_a_failed_run_returns_none(monkeypatch, tmp_path):
    video = tmp_path / "scene_0.mp4"
    video.write_bytes(b"take")

    _install(
        monkeypatch,
        _FakeClient(
            posts=[_FakeResponse({"job_id": "j-9"})],
            gets=[_FakeResponse({"status": "failed", "error": "CUDA out of memory"})],
        ),
    )

    assert await local_mod.LocalLipsync(BASE).sync(str(video), "https://cdn/a.mp3") is None


@pytest.mark.asyncio
async def test_an_answer_with_neither_url_nor_job_id_returns_none(monkeypatch, tmp_path):
    video = tmp_path / "scene_0.mp4"
    video.write_bytes(b"take")

    _install(monkeypatch, _FakeClient(posts=[_FakeResponse({"ok": True})]))

    assert await local_mod.LocalLipsync(BASE).sync(str(video), "https://cdn/a.mp3") is None


@pytest.mark.asyncio
async def test_a_missing_clip_is_skipped_before_anything_is_sent(monkeypatch, tmp_path):
    client = _install(monkeypatch, _FakeClient(posts=[_FakeResponse({"video_url": "/o/0.mp4"})]))

    got = await local_mod.LocalLipsync(BASE).sync(
        str(tmp_path / "never-written.mp4"), "https://cdn/a.mp3"
    )

    assert got is None
    assert client.post_calls == [], "Nothing to sync is not a request to make"


@pytest.mark.asyncio
async def test_cancelling_stops_a_scene_that_was_still_queued(monkeypatch, tmp_path):
    """A scene can wait minutes behind others for its turn on the GPU. One
    cancelled while it waited must not then start a run."""
    video = tmp_path / "scene_0.mp4"
    video.write_bytes(b"take")

    client = _install(monkeypatch, _FakeClient(posts=[_FakeResponse({"video_url": "/o/0.mp4"})]))

    got = await local_mod.LocalLipsync(BASE).sync(
        str(video), "https://cdn/a.mp3", is_cancelled=lambda: True
    )

    assert got is None
    assert client.post_calls == []


# ── the reason this backend needs a cap at all ───────────────────────────────


@pytest.mark.asyncio
async def test_one_gpu_takes_one_scene_at_a_time(monkeypatch, tmp_path):
    """idea2video syncs scenes CONCURRENTLY, which is right against a hosted
    fleet and wrong against one box: three LatentSync runs sharing 16GB do not
    go three times faster, and past a certain resolution they go out of memory
    and lose all three mouths at once.
    """
    for i in range(3):
        (tmp_path / f"scene_{i}.mp4").write_bytes(b"take")

    inflight = 0
    peak = 0

    async def _occupy():
        nonlocal inflight, peak
        inflight += 1
        peak = max(peak, inflight)
        await asyncio.sleep(0)
        inflight -= 1

    client = _FakeClient(
        posts=[_FakeResponse({"video_url": f"/o/{i}.mp4"}) for i in range(3)],
        on_post=_occupy,
    )
    _install(monkeypatch, client)
    monkeypatch.setattr(local_mod, "CONCURRENCY", 1)

    provider = local_mod.LocalLipsync(BASE)
    results = await asyncio.gather(
        *(
            provider.sync(str(tmp_path / f"scene_{i}.mp4"), "https://cdn/a.mp3")
            for i in range(3)
        )
    )

    assert peak == 1, f"{peak} runs were inside the service at once"
    assert all(r and r.startswith(BASE) for r in results), "All three still got synced"
