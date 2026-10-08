"""fal.ai Vidu Q4 reference-to-video provider.

Present so Vidu can be measured against Kling on the same shot, not because it
has been shown better. What is pinned here is the wire shape (confirmed against
fal's OpenAPI) and the ways a deployment could select it wrongly.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


def test_factory_returns_the_vidu_generator(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_vidu")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import _make_video_generator
    from tools.falai_vidu_video_generator import FalAIViduVideoGenerator

    gen = _make_video_generator("test-key", demo=False)
    assert isinstance(gen, FalAIViduVideoGenerator)
    assert gen.uses_character_reference_to_video is True


def test_the_selector_is_normalised_like_every_other_value(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", " Falai_Vidu\n")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import _make_video_generator
    from tools.falai_vidu_video_generator import FalAIViduVideoGenerator

    assert isinstance(_make_video_generator("k", demo=False), FalAIViduVideoGenerator)


def test_vidu_is_not_a_one_take_backend(monkeypatch):
    """No cut control in its schema, so the estimate must not price a take the
    render will not make."""
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_vidu")
    from pipelines.script2video import configured_scene_take_backend

    assert configured_scene_take_backend() is None


def test_existing_selectors_are_untouched(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import VIDEO_PROVIDERS, _make_video_generator
    from tools.falai_reference_video_generator import FalAIReferenceVideoGenerator

    assert VIDEO_PROVIDERS[:4] == ("muapi", "falai", "falai_reference", "falai_multishot")
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_reference")
    assert isinstance(_make_video_generator("k", demo=False), FalAIReferenceVideoGenerator)


async def _call(monkeypatch, **kwargs):
    import tools.falai_vidu_video_generator as mod

    captured = {}

    async def fake_fal_generate(client, endpoint, arguments, **_kwargs):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {"video": {"url": "https://fal.media/vidu.mp4"}}

    monkeypatch.setattr(mod, "fal_generate", fake_fal_generate)
    gen = mod.FalAIViduVideoGenerator(api_key="k", demo=False)
    url = await gen.generate_video_from_image(
        image_url="https://example.com/portrait.png", **kwargs
    )
    return url, captured


@pytest.mark.asyncio
async def test_payload_matches_the_confirmed_schema(monkeypatch):
    monkeypatch.delenv("FALAI_VIDU_RESOLUTION", raising=False)
    monkeypatch.delenv("FALAI_VIDU_VIDEO_MODEL", raising=False)
    url, captured = await _call(
        monkeypatch, prompt="walks toward the camera", duration=8, aspect_ratio="9:16"
    )
    assert url == "https://fal.media/vidu.mp4"
    assert captured["endpoint"] == "fal-ai/vidu/q4/reference-to-video"
    args = captured["arguments"]
    assert args["prompt"] == "[@reference_image_1] walks toward the camera"
    assert args["reference_image_urls"] == ["https://example.com/portrait.png"]
    # An INTEGER, unlike Kling's string enum -- sending "8" is a 422.
    assert args["duration"] == 8 and isinstance(args["duration"], int)
    assert args["aspect_ratio"] == "9:16"
    assert args["resolution"] == "720p"
    # The dialogue is voiced and mixed afterwards; a model track would double it.
    assert "audio" not in args
    # The fields of the OTHER providers' schemas must not leak in.
    assert "elements" not in args and "image_url" not in args


@pytest.mark.asyncio
async def test_duration_is_clamped_to_what_the_endpoint_takes(monkeypatch):
    _, low = await _call(monkeypatch, prompt="p", duration=1)
    _, high = await _call(monkeypatch, prompt="p", duration=40)
    assert low["arguments"]["duration"] == 3
    assert high["arguments"]["duration"] == 16


@pytest.mark.asyncio
async def test_square_is_a_ratio_this_endpoint_accepts_and_an_odd_one_is_not_sent(monkeypatch):
    _, square = await _call(monkeypatch, prompt="p", aspect_ratio="1:1")
    _, odd = await _call(monkeypatch, prompt="p", aspect_ratio="21:9")
    assert square["arguments"]["aspect_ratio"] == "1:1"
    assert odd["arguments"]["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_resolution_is_configurable_and_a_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("FALAI_VIDU_RESOLUTION", "1080P")
    _, ok = await _call(monkeypatch, prompt="p")
    monkeypatch.setenv("FALAI_VIDU_RESOLUTION", "8k")
    _, bad = await _call(monkeypatch, prompt="p")
    assert ok["arguments"]["resolution"] == "1080p"
    # An unknown value would be a 422 on every shot of every job.
    assert bad["arguments"]["resolution"] == "720p"


@pytest.mark.asyncio
async def test_a_long_prompt_is_cut_to_the_schema_limit(monkeypatch):
    _, captured = await _call(monkeypatch, prompt="x" * 9000)
    assert len(captured["arguments"]["prompt"]) == 5000


@pytest.mark.asyncio
async def test_the_acted_peak_is_accepted_and_ignored(monkeypatch):
    """The schema has no end frame; the pipeline may still pass one."""
    _, captured = await _call(monkeypatch, prompt="p", last_image="https://x/peak.png")
    assert "end_image_url" not in captured["arguments"]
    assert "https://x/peak.png" not in str(captured["arguments"])


@pytest.mark.asyncio
async def test_the_endpoint_can_be_overridden(monkeypatch):
    monkeypatch.setenv("FALAI_VIDU_VIDEO_MODEL", "fal-ai/vidu/q5/reference-to-video")
    _, captured = await _call(monkeypatch, prompt="p")
    assert captured["endpoint"] == "fal-ai/vidu/q5/reference-to-video"


@pytest.mark.asyncio
async def test_a_result_without_a_video_raises(monkeypatch):
    import tools.falai_vidu_video_generator as mod

    async def empty(*a, **k):
        return {"cover_image": {"url": "https://x/c.jpg"}}

    monkeypatch.setattr(mod, "fal_generate", empty)
    gen = mod.FalAIViduVideoGenerator(api_key="k", demo=False)
    with pytest.raises(RuntimeError, match="no video URL"):
        await gen.generate_video_from_image("p", "https://x/portrait.png")


@pytest.mark.asyncio
async def test_demo_mode_skips_the_network():
    from tools.falai_reference_video_generator import DEMO_VIDEO_URL
    from tools.falai_vidu_video_generator import FalAIViduVideoGenerator

    gen = FalAIViduVideoGenerator(api_key="", demo=True)
    assert await gen.generate_video_from_image("p", "https://x") == DEMO_VIDEO_URL
