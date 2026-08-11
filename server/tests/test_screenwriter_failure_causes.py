"""The screenwriter must name the cause it actually hit.

Every failure used to surface as "the script model is unavailable", which is
true of an outage and misleading of everything else: a truncated response
sent operators hunting for a dead API when the fix was the token budget, and
a bad API key told the user to "try again shortly" forever.
"""

import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest

from agents.screenwriter import ScreenwriterAgent, ScriptGenerationFailed

VALID_SCRIPT = {
    "title": "The Tell",
    "logline": "A dealer meets her own tell.",
    "setting_location": "a basement card room",
    "characters": [{"name": "Mira", "description": "sharp-eyed dealer, 30s"}],
    "scenes": [{"action": "She deals.", "emotion": "wary"}],
}


class _FakeStream:
    """Stands in for `client.messages.stream(...)`'s context manager."""

    def __init__(self, message):
        self._message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self._message


def _message(text, stop_reason="end_turn", thinking_first=True):
    """Sonnet 5 runs adaptive thinking by default, so a real response leads
    with a thinking block and the text block comes after it. Reproduced here
    by default because reading `content[0]` cost production every job."""
    blocks = []
    if thinking_first:
        blocks.append(SimpleNamespace(type="thinking", thinking=""))
    blocks.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        content=blocks,
        stop_reason=stop_reason,
        stop_details=None,
        usage=SimpleNamespace(output_tokens=16000),
    )


def _patch_stream(monkeypatch, result):
    """Point AsyncAnthropic at `result` — a message, or an exception to raise."""

    def fake_stream(*args, **kwargs):
        if isinstance(result, Exception):
            raise result
        return _FakeStream(result)

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = SimpleNamespace(stream=fake_stream)

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _FakeClient)


async def _write(agent):
    return await agent._write_with_claude("A dealer's tell", "Noir", 3, "")


@pytest.mark.asyncio
async def test_valid_response_produces_a_script(monkeypatch):
    _patch_stream(monkeypatch, _message(json.dumps(VALID_SCRIPT)))
    script = await _write(ScreenwriterAgent(api_key="test"))
    assert script.title == "The Tell"
    assert script.user_brief == "A dealer's tell"


@pytest.mark.asyncio
async def test_thinking_block_first_does_not_break_parsing(monkeypatch):
    """The production failure: `KeyError: 'text'`.

    Sonnet 5 has adaptive thinking on by default, so content[0] is a thinking
    block. Code that read content[0]["text"] failed on every job. Blocks must
    be selected by type, never by position.
    """
    message = _message(json.dumps(VALID_SCRIPT), thinking_first=True)
    assert message.content[0].type == "thinking"  # the shape that broke it
    _patch_stream(monkeypatch, message)

    script = await _write(ScreenwriterAgent(api_key="test"))
    assert script.title == "The Tell"


@pytest.mark.asyncio
async def test_truncated_response_says_it_was_cut_off(monkeypatch):
    """The model answered; the budget ran out. Not an outage."""
    truncated = json.dumps(VALID_SCRIPT)[:120]
    _patch_stream(monkeypatch, _message(truncated, stop_reason="max_tokens"))

    with pytest.raises(ScriptGenerationFailed) as err:
        await _write(ScreenwriterAgent(api_key="test"))
    assert "cut off" in str(err.value)
    assert "unavailable" not in str(err.value)


@pytest.mark.asyncio
async def test_bad_api_key_tells_the_user_to_contact_support(monkeypatch):
    """401 never clears on its own — "try again shortly" is a wall."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(401, request=request, json={"error": {"type": "authentication_error"}})
    _patch_stream(
        monkeypatch,
        anthropic.AuthenticationError("bad key", response=response, body=None),
    )

    with pytest.raises(ScriptGenerationFailed) as err:
        await _write(ScreenwriterAgent(api_key="bad"))
    assert "contact support" in str(err.value)


@pytest.mark.asyncio
async def test_rate_limit_says_wait_a_minute(monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request, json={"error": {"type": "rate_limit_error"}})
    _patch_stream(
        monkeypatch,
        anthropic.RateLimitError("slow down", response=response, body=None),
    )

    with pytest.raises(ScriptGenerationFailed) as err:
        await _write(ScreenwriterAgent(api_key="test"))
    assert "wait a minute" in str(err.value)


@pytest.mark.asyncio
async def test_unparseable_response_is_reported_as_such(monkeypatch):
    _patch_stream(monkeypatch, _message("I'd rather write a poem about it."))

    with pytest.raises(ScriptGenerationFailed) as err:
        await _write(ScreenwriterAgent(api_key="test"))
    assert "could not read" in str(err.value)


@pytest.mark.asyncio
async def test_no_provider_configured_still_fails_loudly(monkeypatch):
    """Never the deterministic template on a paid render."""
    agent = ScreenwriterAgent(api_key="")
    agent.muapi_key = ""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ScriptGenerationFailed):
        await agent.write_script("A dealer's tell")


# --- storyboard artist: the same bug, the same fix ----------------------


@pytest.mark.asyncio
async def test_storyboard_survives_a_leading_thinking_block(monkeypatch):
    """The storyboard agent read content[0]["text"] too. There the failure
    was silent: it swallowed the exception and returned [], so every scene
    quietly fell back to the template shot list."""
    from agents.storyboard_artist import StoryboardArtist
    from interfaces.character import CharacterInScene

    shots = [{
        "idx": 0,
        "visual_desc": "Her hands squaring the deck under a single lamp.",
        "motion_desc": "slow push in",
    }]
    _patch_stream(monkeypatch, _message(json.dumps(shots), thinking_first=True))

    artist = StoryboardArtist(api_key="test")
    result = await artist._design_with_claude(
        script="She deals.",
        characters=[CharacterInScene(idx=0, name="Mira", static_features="dealer",
                                     dynamic_features="", is_visible=True)],
        user_requirement="",
        guidance="hold on her hands",
        default_lens="50mm",
    )
    assert len(result) == 1, "a leading thinking block must not empty the shot list"
    assert result[0].motion_desc == "slow push in"
