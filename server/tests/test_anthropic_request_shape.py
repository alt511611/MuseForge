"""Drive the real Anthropic SDK against a fake HTTP transport.

The other tests stub the SDK out, so they prove our branching but not our
SDK usage. Here the genuine client builds the request and parses the SSE
stream — a wrong keyword, a bad model id, or a block assumption fails here
the way it would in production, with no API key and no network.

The fixtures deliberately lead with a **thinking block**, because that is
the shape Sonnet 5 actually returns (adaptive thinking is on by default) and
reading `content[0]["text"]` against it took down every job in production.
"""

import json
import os
import sys

import anthropic
import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.screenwriter import ScreenwriterAgent, ScriptGenerationFailed  # noqa: E402
from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from tools import character_qa  # noqa: E402

#: Captured before any test patches the module attribute — subclassing
#: whatever is currently there would nest the wrappers across tests.
_REAL_ASYNC_ANTHROPIC = anthropic.AsyncAnthropic

SCRIPT = {
    "title": "Neon Harbour",
    "logline": "A dock worker opens a humming container.",
    "setting_location": "a rain-soaked cargo harbour at night",
    "characters": [{"name": "Deniz", "description": "dock worker, 30s, soaked parka"}],
    "scenes": [{"action": "She cuts the seal.", "emotion": "dread"}],
}

SHOTS = [{"idx": 0, "visual_desc": "Her hands on the seal.", "motion_desc": "slow push in"}]


def _sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def _stream_body(text, stop_reason="end_turn"):
    """A Sonnet 5-shaped streamed response: thinking block, then the text."""
    events = [
        {
            "type": "message_start",
            "message": {
                "id": "msg_1", "type": "message", "role": "assistant",
                "model": "claude-sonnet-5", "content": [],
                "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 1},
            },
        },
        {"type": "content_block_start", "index": 0,
         "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "thinking_delta", "thinking": "weighing the beats"}},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "signature_delta", "signature": "abc123"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1,
         "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 1,
         "delta": {"type": "text_delta", "text": text}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta",
         "delta": {"stop_reason": stop_reason, "stop_sequence": None},
         "usage": {"output_tokens": 120}},
        {"type": "message_stop"},
    ]
    return _sse(events)


@pytest.fixture
def wire(monkeypatch):
    """Patch AsyncAnthropic onto a mock transport; yields captured requests."""
    captured = []

    def install(response_for_request):
        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            captured.append(payload)
            body = response_for_request(payload)
            if payload.get("stream"):
                return httpx.Response(
                    200, headers={"content-type": "text/event-stream"}, text=body
                )
            return httpx.Response(200, json=body)

        transport = httpx.MockTransport(handler)

        class _Client(_REAL_ASYNC_ANTHROPIC):
            def __init__(self, *a, **k):
                k.pop("api_key", None)
                super().__init__(
                    api_key="sk-ant-test",
                    http_client=httpx.AsyncClient(transport=transport),
                    **k,
                )

        monkeypatch.setattr(anthropic, "AsyncAnthropic", _Client)
        return captured

    return install


# --- screenwriter -------------------------------------------------------


@pytest.mark.asyncio
async def test_screenwriter_parses_a_real_streamed_response(wire):
    captured = wire(lambda p: _stream_body(json.dumps(SCRIPT)))

    script = await ScreenwriterAgent(api_key="k")._write_with_claude(
        "A dock worker finds a humming container", "Sci-Fi", 3, ""
    )

    assert script.title == "Neon Harbour"
    assert script.user_brief.startswith("A dock worker")

    req = captured[0]
    assert req["stream"] is True, "streaming avoids the flat HTTP deadline"
    assert req["model"] == "claude-sonnet-5"
    assert req["max_tokens"] == ScreenwriterAgent.MAX_SCRIPT_TOKENS
    assert "award-winning writer-director" in req["system"]
    # Sonnet 5 rejects non-default sampling params outright.
    assert not {"temperature", "top_p", "top_k"} & set(req)


@pytest.mark.asyncio
async def test_screenwriter_reports_truncation_as_truncation(wire):
    wire(lambda p: _stream_body(json.dumps(SCRIPT)[:80], stop_reason="max_tokens"))

    with pytest.raises(ScriptGenerationFailed) as err:
        await ScreenwriterAgent(api_key="k")._write_with_claude("x", "Noir", 3, "")

    assert "cut off" in str(err.value)
    assert "unavailable" not in str(err.value)


# --- storyboard ---------------------------------------------------------


@pytest.mark.asyncio
async def test_storyboard_parses_a_real_streamed_response(wire):
    captured = wire(lambda p: _stream_body(json.dumps(SHOTS)))

    shots = await StoryboardArtist(api_key="k")._design_with_claude(
        script="She cuts the seal.",
        characters=[CharacterInScene(idx=0, name="Deniz", static_features="dock worker",
                                     dynamic_features="", is_visible=True)],
        user_requirement="",
        guidance="hold on her hands",
        default_lens="50mm",
    )

    # An empty list here is the silent template fallback -- the exact
    # symptom the leading thinking block used to cause.
    assert len(shots) == 1
    assert shots[0].motion_desc == "slow push in"

    req = captured[0]
    assert req["stream"] is True
    assert req["max_tokens"] == StoryboardArtist.MAX_SHOT_TOKENS


# --- character QA -------------------------------------------------------


@pytest.mark.asyncio
async def test_character_qa_reads_the_verdict_with_thinking_off(wire):
    captured = wire(lambda p: {
        "id": "msg_2", "type": "message", "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text",
                     "text": '{"character_ok": false, "setting_ok": true, '
                             '"issue": "the parka colour does not match"}'}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 900, "output_tokens": 30},
    })

    result = await character_qa.verify_frame(
        frame_url="https://example.com/frame.jpg",
        expected_character_desc="dock worker in a soaked parka",
        expected_setting="cargo harbour, night",
        anthropic_api_key="k",
    )

    # This QA fails open, so a broken call looks like a clean pass. Assert
    # the verdict actually came back.
    assert result["character_ok"] is False
    assert "parka" in result["issue"]

    req = captured[0]
    assert req["thinking"] == {"type": "disabled"}, (
        "a per-frame yes/no check should not pay for thinking"
    )
    assert req["max_tokens"] >= 512, "thinking + text share this budget"
    assert any(b.get("type") == "image" for b in req["messages"][0]["content"])
