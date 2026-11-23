"""ElevenLabs allows three dialogue requests at a time and answers a fourth with a 429.

Job d7fde8c8 (2026-11-22) rendered its scenes' speech together, one scene got
"maximum 3 concurrent requests", and the pipeline -- which treats a scene with
no voice as a silent scene -- delivered the film with that line gone and
nothing on screen to say so. Two things stop it: no more than two requests in
flight per process (the account's allowance is shared), and a 429 is asked
again once the requests ahead have finished.
"""
import asyncio
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tools.elevenlabs_voice_generator as mod

AUDIO = base64.b64encode(b"ID3-not-really-an-mp3").decode()
LINES = [{"character": "Mara", "line": "Priya, you seeing this?"}]


class _Response:
    def __init__(self, status=200, headers=None, body=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body if body is not None else {
            "audio_base64": AUDIO,
            "voice_segments": [
                {"dialogue_input_index": 0, "start_time_seconds": 0.0, "end_time_seconds": 1.0}
            ],
        }
        self.text = str(self._body)

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("boom", request=None, response=self)


@pytest.fixture
def server(monkeypatch):
    """A fake ElevenLabs: scripted answers, and a record of how many were in flight."""

    class State:
        answers = []  # popped per request; empty means 200
        in_flight = 0
        peak = 0
        posts = 0
        slept = []

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            State.posts += 1
            State.in_flight += 1
            State.peak = max(State.peak, State.in_flight)
            try:
                await asyncio.sleep(0.01)  # long enough for the others to pile up
                return State.answers.pop(0) if State.answers else _Response()
            finally:
                State.in_flight -= 1

    async def no_sleep(seconds):
        State.slept.append(seconds)

    monkeypatch.setattr(mod.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(mod, "_sleep", no_sleep)
    monkeypatch.setattr(mod, "_SLOTS", __import__("weakref").WeakKeyDictionary())
    monkeypatch.delenv("ELEVENLABS_MAX_CONCURRENCY", raising=False)
    return State


def _generator():
    g = mod.ElevenLabsVoiceGenerator(api_key="k")
    g.voices = {"Mara": "voice-1"} if hasattr(g, "voices") else None
    return g


async def _speak(generator):
    return await generator.generate_scene_dialogue(LINES)


@pytest.fixture(autouse=True)
def _voice_cast(monkeypatch):
    # The cast is not what is under test; give the line a voice without a catalogue call.
    monkeypatch.setattr(
        mod.ElevenLabsVoiceGenerator, "_parse_lines",
        lambda self, dialogue, emotion="": [
            {"character": "Mara", "line": "Priya, you seeing this?", "voice_id": "v1"}
        ],
    )


@pytest.mark.asyncio
async def test_six_scenes_at_once_never_have_more_than_two_requests_in_flight(server):
    g = _generator()
    await asyncio.gather(*(_speak(g) for _ in range(6)))
    assert server.posts == 6
    assert server.peak == 2


@pytest.mark.asyncio
async def test_the_ceiling_can_be_set_from_the_environment(server, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_MAX_CONCURRENCY", "1")
    g = _generator()
    await asyncio.gather(*(_speak(g) for _ in range(4)))
    assert server.peak == 1


@pytest.mark.asyncio
async def test_a_nonsense_ceiling_falls_back_instead_of_deadlocking(server, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_MAX_CONCURRENCY", "zero")
    g = _generator()
    await asyncio.gather(*(_speak(g) for _ in range(3)))
    assert server.peak == 2
    monkeypatch.setenv("ELEVENLABS_MAX_CONCURRENCY", "0")
    mod._SLOTS.clear()
    server.peak = 0
    await asyncio.gather(*(_speak(g) for _ in range(3)))
    assert server.peak == 1  # a zero is clamped to one slot, never zero slots


@pytest.mark.asyncio
async def test_a_429_is_asked_again_and_the_scene_keeps_its_voice(server):
    server.answers = [_Response(429)]
    tracks = await _speak(_generator())
    assert server.posts == 2
    assert tracks and tracks[0]["audio_url"]


@pytest.mark.asyncio
async def test_the_providers_retry_after_is_what_is_waited(server):
    server.answers = [_Response(429, headers={"retry-after": "7"})]
    await _speak(_generator())
    assert server.slept == [7.0]


@pytest.mark.asyncio
async def test_without_a_retry_after_the_wait_grows(server):
    server.answers = [_Response(429), _Response(429), _Response(429)]
    await _speak(_generator())
    assert server.slept == list(mod.RATE_LIMIT_BACKOFF_SECONDS)


@pytest.mark.asyncio
async def test_a_429_that_never_clears_is_raised_in_the_providers_words(server):
    body = {"detail": {"status": "too_many_concurrent_requests", "message": "maximum 3 concurrent requests"}}
    server.answers = [_Response(429, body=body) for _ in range(mod.RATE_LIMIT_ATTEMPTS)]
    with pytest.raises(mod.ElevenLabsError) as err:
        await _speak(_generator())
    assert server.posts == mod.RATE_LIMIT_ATTEMPTS
    assert "429" in str(err.value) and "concurrent" in str(err.value)


@pytest.mark.asyncio
async def test_any_other_refusal_is_raised_at_once_not_retried(server):
    server.answers = [_Response(401, body={"detail": "invalid api key"})]
    with pytest.raises(mod.ElevenLabsError):
        await _speak(_generator())
    assert server.posts == 1 and server.slept == []


@pytest.mark.asyncio
async def test_a_job_cancelled_while_waiting_does_not_ask_again(server):
    server.answers = [_Response(429)]
    with pytest.raises(mod.ElevenLabsError, match="cancelled"):
        await _generator().generate_scene_dialogue(LINES, is_cancelled=lambda: bool(server.slept))
    assert server.posts == 1
