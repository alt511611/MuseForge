"""fal.ai Kling O3 Pro alternative video provider (MUSEFORGE_VIDEO_PROVIDER
=falai). The default ("muapi") path must remain completely unaffected.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


def test_factory_defaults_to_muapi_when_env_unset(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_VIDEO_PROVIDER", raising=False)
    from pipelines.script2video import _make_video_generator
    from tools.muapi_video_generator import MuAPIVideoGenerator

    gen = _make_video_generator("test-key", demo=False)
    assert isinstance(gen, MuAPIVideoGenerator)


def test_factory_returns_falai_when_env_set(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import _make_video_generator
    from tools.falai_video_generator import FalAIVideoGenerator

    gen = _make_video_generator("test-key", demo=False)
    assert isinstance(gen, FalAIVideoGenerator)


def test_pipeline_construction_unaffected_by_default_provider(monkeypatch):
    """The full Script2VideoPipeline must still build a MuAPIVideoGenerator
    when MUSEFORGE_VIDEO_PROVIDER is unset -- existing behavior untouched."""
    monkeypatch.delenv("MUSEFORGE_VIDEO_PROVIDER", raising=False)
    from pipelines.script2video import Script2VideoPipeline
    from tools.muapi_video_generator import MuAPIVideoGenerator

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    assert isinstance(pipeline.video_gen, MuAPIVideoGenerator)


def test_duration_clamped_to_3_15_string_enum():
    from tools.falai_video_generator import _duration_str

    assert _duration_str(5) == "5"
    assert _duration_str(1) == "3"      # below range -> clamped up
    assert _duration_str(30) == "15"    # above range -> clamped down
    assert _duration_str("bad") == "5"  # unparsable -> safe default


@pytest.mark.asyncio
async def test_demo_mode_returns_placeholder_without_network():
    from tools.falai_video_generator import FalAIVideoGenerator, DEMO_VIDEO_URL

    gen = FalAIVideoGenerator(api_key="", demo=True)
    url = await gen.generate_video_from_image("pan left", "https://cdn.example/f.jpg")
    assert url == DEMO_VIDEO_URL


@pytest.mark.asyncio
async def test_submits_confirmed_schema_and_returns_video_url(monkeypatch):
    """Payload must be exactly {prompt, image_url, duration (as a STRING,
    not limited to 5/10 like MuAPI's Kling O1 endpoint)} -- confirmed
    against fal.ai's own kling-video/o3/pro/image-to-video API docs."""
    import fal_client
    from tools.falai_video_generator import FalAIVideoGenerator

    submitted = {}

    class FakeHandle:
        request_id = "req-123"

    class FakeAsyncClient:
        def __init__(self, key=None):
            self.key = key

        async def submit(self, application, arguments):
            submitted["application"] = application
            submitted["arguments"] = arguments
            return FakeHandle()

        async def status(self, application, request_id, with_logs=False):
            return fal_client.Completed(logs=None, metrics={}, error=None)

        async def result(self, application, request_id):
            return {"video": {"url": "https://fal.media/output.mp4"}}

        async def cancel(self, application, request_id):
            pass

    monkeypatch.setattr(fal_client, "AsyncClient", FakeAsyncClient)

    gen = FalAIVideoGenerator(api_key="test-fal-key", demo=False)
    url = await gen.generate_video_from_image(
        prompt="A character walking forward.",
        image_url="https://example.com/start.png",
        duration=14,
    )

    assert url == "https://fal.media/output.mp4"
    assert submitted["application"] == "fal-ai/kling-video/o3/pro/image-to-video"
    assert submitted["arguments"] == {
        "prompt": "A character walking forward.",
        "image_url": "https://example.com/start.png",
        "duration": "14",
    }


@pytest.mark.asyncio
async def test_api_key_is_stripped_before_use(monkeypatch):
    """A trailing newline/whitespace in FAL_KEY (easy to introduce when
    pasting into Render's dashboard) must never reach the real request --
    it would otherwise cause an opaque 'Illegal header value' error."""
    import fal_client
    from tools.falai_video_generator import FalAIVideoGenerator

    seen_keys = []
    submitted = {}

    class FakeHandle:
        request_id = "req-strip"

    class FakeAsyncClient:
        def __init__(self, key=None):
            seen_keys.append(key)

        async def submit(self, application, arguments):
            submitted["arguments"] = arguments
            return FakeHandle()

        async def status(self, application, request_id, with_logs=False):
            return fal_client.Completed(logs=None, metrics={}, error=None)

        async def result(self, application, request_id):
            return {"video": {"url": "https://fal.media/output.mp4"}}

        async def cancel(self, application, request_id):
            pass

    monkeypatch.setattr(fal_client, "AsyncClient", FakeAsyncClient)

    gen = FalAIVideoGenerator(api_key="abc123\n", demo=False)
    assert gen.api_key == "abc123"
    assert seen_keys == ["abc123"]

    await gen.generate_video_from_image("prompt", "https://example.com/f.png")
    # Confirms the cleaned key is what actually backs the client used for
    # the real request, not just the stored attribute.
    assert seen_keys == ["abc123"]
    assert submitted["arguments"]["prompt"] == "prompt"


@pytest.mark.asyncio
async def test_completed_with_error_raises(monkeypatch):
    import fal_client
    from tools.falai_video_generator import FalAIVideoGenerator

    class FakeHandle:
        request_id = "req-err"

    class FakeAsyncClient:
        def __init__(self, key=None):
            pass

        async def submit(self, application, arguments):
            return FakeHandle()

        async def status(self, application, request_id, with_logs=False):
            return fal_client.Completed(logs=None, metrics={}, error="model overloaded")

        async def result(self, application, request_id):
            raise AssertionError("result() should not be called after a failed status")

        async def cancel(self, application, request_id):
            pass

    monkeypatch.setattr(fal_client, "AsyncClient", FakeAsyncClient)

    gen = FalAIVideoGenerator(api_key="test-fal-key", demo=False)
    with pytest.raises(RuntimeError, match="model overloaded"):
        await gen.generate_video_from_image("prompt", "https://example.com/f.png")


@pytest.mark.asyncio
async def test_cancellation_mid_poll_cancels_remote_job_and_raises(monkeypatch):
    from tools.muapi_client import MuAPICancelled
    import fal_client
    from tools.falai_video_generator import FalAIVideoGenerator

    cancel_calls = []

    class FakeHandle:
        request_id = "req-cancel"

    class FakeAsyncClient:
        def __init__(self, key=None):
            pass

        async def submit(self, application, arguments):
            return FakeHandle()

        async def status(self, application, request_id, with_logs=False):
            return fal_client.InProgress(logs=None)

        async def result(self, application, request_id):
            raise AssertionError("result() should not be called when cancelled")

        async def cancel(self, application, request_id):
            cancel_calls.append(request_id)

    monkeypatch.setattr(fal_client, "AsyncClient", FakeAsyncClient)

    gen = FalAIVideoGenerator(api_key="test-fal-key", demo=False)
    with pytest.raises(MuAPICancelled):
        await gen.generate_video_from_image(
            "prompt", "https://example.com/f.png", is_cancelled=lambda: True
        )
    assert cancel_calls == ["req-cancel"]
