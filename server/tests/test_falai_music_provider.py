"""fal.ai Beatoven music provider tests."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


def test_music_factory_defaults_to_muapi(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_MUSIC_PROVIDER", raising=False)
    from pipelines.idea2video import _make_music_generator
    from tools.muapi_music_generator import MuAPIMusicGenerator

    assert isinstance(_make_music_generator("k", demo=False), MuAPIMusicGenerator)


def test_music_factory_returns_falai(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_MUSIC_PROVIDER", "falai")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.idea2video import _make_music_generator
    from tools.falai_music_generator import FalAIMusicGenerator

    assert isinstance(_make_music_generator("k", demo=False), FalAIMusicGenerator)


@pytest.mark.asyncio
async def test_beatoven_payload_matches_confirmed_openapi(monkeypatch):
    """Endpoint id is beatoven/music-generation (no fal-ai/ prefix).
    Output field is audio.url (not audio_file).
    """
    import tools.falai_music_generator as mod
    from tools.falai_music_generator import FalAIMusicGenerator

    captured = {}

    async def fake_fal_generate(client, endpoint, arguments, **_kwargs):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {"audio": {"url": "https://fal.media/track.wav"}, "prompt": "x", "metadata": {}}

    monkeypatch.setattr(mod, "fal_generate", fake_fal_generate)

    gen = FalAIMusicGenerator(api_key="k", demo=False)
    url = await gen.generate_instrumental(mood="melancholic", duration=45)

    assert url == "https://fal.media/track.wav"
    assert captured["endpoint"] == "beatoven/music-generation"
    args = captured["arguments"]
    assert "melancholic" in args["prompt"]
    assert args["duration"] == 45
    assert "negative_prompt" in args


@pytest.mark.asyncio
async def test_duration_clamped_to_5_150(monkeypatch):
    import tools.falai_music_generator as mod
    from tools.falai_music_generator import FalAIMusicGenerator

    captured = {}

    async def fake_fal_generate(client, endpoint, arguments, **_kwargs):
        captured["arguments"] = arguments
        return {"audio": {"url": "https://fal.media/t.wav"}, "prompt": "", "metadata": {}}

    monkeypatch.setattr(mod, "fal_generate", fake_fal_generate)

    gen = FalAIMusicGenerator(api_key="k", demo=False)
    await gen.generate_instrumental(mood="x", duration=1)
    assert captured["arguments"]["duration"] == 5
    await gen.generate_instrumental(mood="x", duration=999)
    assert captured["arguments"]["duration"] == 150


@pytest.mark.asyncio
async def test_demo_returns_empty_string():
    from tools.falai_music_generator import FalAIMusicGenerator

    gen = FalAIMusicGenerator(api_key="", demo=True)
    assert await gen.generate_instrumental("cinematic") == ""
