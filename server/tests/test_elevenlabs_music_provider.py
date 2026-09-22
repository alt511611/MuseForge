"""ElevenLabs direct Music API provider tests (POST /v1/music)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")

AUDIO_BYTES = b"ID3-not-really-an-mp3"


class _Response:
    def __init__(self, content=b"", status=200, error_json=None):
        self.content = content
        self.status_code = status
        self.text = str(error_json or content)
        self._error_json = error_json

    def json(self):
        return self._error_json or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("boom", request=None, response=self)


class _Client:
    """Stands in for httpx.AsyncClient, recording what was sent."""

    posted = None
    response = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).posted = {"url": url, "headers": headers, "json": json}
        return type(self).response


@pytest.fixture(autouse=True)
def _clean():
    _Client.posted = None
    _Client.response = _Response(content=AUDIO_BYTES)
    yield


def _generator(tmp_path, monkeypatch):
    from tools import elevenlabs_music_generator as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", _Client)
    return mod.ElevenLabsMusicGenerator("key", working_dir=str(tmp_path))


def test_music_factory_returns_elevenlabs(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_MUSIC_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven-key")
    from pipelines.idea2video import _make_music_generator
    from tools.elevenlabs_music_generator import ElevenLabsMusicGenerator

    assert isinstance(
        _make_music_generator("k", demo=False), ElevenLabsMusicGenerator
    )


@pytest.mark.asyncio
async def test_generate_instrumental_posts_to_music_endpoint(tmp_path, monkeypatch):
    gen = _generator(tmp_path, monkeypatch)

    path = await gen.generate_instrumental(
        mood="melancholic", duration=45, style_hint="slow piano"
    )

    assert _Client.posted["url"] == "https://api.elevenlabs.io/v1/music"
    assert _Client.posted["headers"]["xi-api-key"] == "key"
    body = _Client.posted["json"]
    assert "melancholic" in body["prompt"]
    assert "slow piano" in body["prompt"]
    assert body["music_length_ms"] == 45 * 1000
    assert body["model_id"] == "music_v1"
    assert body["force_instrumental"] is True

    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == AUDIO_BYTES


@pytest.mark.asyncio
async def test_duration_clamped_to_3_600(tmp_path, monkeypatch):
    gen = _generator(tmp_path, monkeypatch)

    await gen.generate_instrumental(mood="x", duration=1)
    assert _Client.posted["json"]["music_length_ms"] == 3 * 1000

    await gen.generate_instrumental(mood="x", duration=9999)
    assert _Client.posted["json"]["music_length_ms"] == 600 * 1000


@pytest.mark.asyncio
async def test_demo_returns_empty_string():
    from tools.elevenlabs_music_generator import ElevenLabsMusicGenerator

    gen = ElevenLabsMusicGenerator(api_key="", demo=True)
    assert await gen.generate_instrumental("cinematic") == ""


@pytest.mark.asyncio
async def test_http_error_raises_elevenlabs_error(tmp_path, monkeypatch):
    from tools.elevenlabs_voice_generator import ElevenLabsError

    gen = _generator(tmp_path, monkeypatch)
    _Client.response = _Response(
        status=422, error_json={"detail": {"message": "bad prompt"}}
    )

    with pytest.raises(ElevenLabsError):
        await gen.generate_instrumental("cinematic")
