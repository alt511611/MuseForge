"""Jobs 82c56e88 and 8e1a8dc7: the same four-scene brief, 14365 then 24000+ tokens.

Thinking is adaptive and shares the output ceiling with the JSON. The job that
drew a long thinking pass was cut off mid-JSON after 296 s and thrown away,
with nothing to show. The cut-off now earns one retry with thinking disabled,
so the whole budget goes to the script.
"""
import json

import pytest

from agents.screenwriter import ScreenwriterAgent, ScriptGenerationFailed
from tests.test_anthropic_request_shape import SCRIPT, _stream_body, wire  # noqa: F401


@pytest.mark.asyncio
async def test_a_truncated_script_is_retried_once_with_thinking_off(wire):  # noqa: F811
    def respond(payload):
        if "thinking" in payload:
            return _stream_body(json.dumps(SCRIPT))
        return _stream_body(json.dumps(SCRIPT)[:80], stop_reason="max_tokens")

    captured = wire(respond)

    script = await ScreenwriterAgent(api_key="k")._write_with_claude(
        "A dock worker finds a humming container", "Sci-Fi", 3, ""
    )

    assert script.title == "Neon Harbour"
    assert len(captured) == 2
    assert "thinking" not in captured[0]
    assert captured[1]["thinking"] == {"type": "disabled"}
    assert captured[1]["max_tokens"] == ScreenwriterAgent.MAX_SCRIPT_TOKENS


@pytest.mark.asyncio
async def test_a_script_that_fits_is_asked_for_exactly_once(wire):  # noqa: F811
    captured = wire(lambda p: _stream_body(json.dumps(SCRIPT)))

    await ScreenwriterAgent(api_key="k")._write_with_claude("x", "Noir", 3, "")

    assert len(captured) == 1
    assert "thinking" not in captured[0]


@pytest.mark.asyncio
async def test_a_script_truncated_twice_still_fails_as_truncation(wire):  # noqa: F811
    captured = wire(lambda p: _stream_body(json.dumps(SCRIPT)[:80], stop_reason="max_tokens"))

    with pytest.raises(ScriptGenerationFailed) as err:
        await ScreenwriterAgent(api_key="k")._write_with_claude("x", "Noir", 3, "")

    assert len(captured) == 2
    assert "longer than the limit" in str(err.value)


@pytest.mark.asyncio
async def test_a_model_that_refuses_the_retry_still_reports_truncation(monkeypatch, wire):  # noqa: F811
    import httpx
    import anthropic
    import tests.test_anthropic_request_shape as shape

    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload)
        if "thinking" in payload:
            return httpx.Response(400, json={"type": "error", "error": {"type": "invalid_request_error", "message": "thinking not allowed"}})
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              text=_stream_body(json.dumps(SCRIPT)[:80], stop_reason="max_tokens"))

    class _Client(shape._REAL_ASYNC_ANTHROPIC):
        def __init__(self, *a, **k):
            k.pop("api_key", None)
            super().__init__(api_key="sk-ant-test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **k)

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _Client)

    with pytest.raises(ScriptGenerationFailed) as err:
        await ScreenwriterAgent(api_key="k")._write_with_claude("x", "Noir", 3, "")

    assert "longer than the limit" in str(err.value)
    assert len(calls) == 2
