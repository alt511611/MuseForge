"""Claude was billed to a second account, and when it ran dry QA went quiet.

Job bb6c6f1f: the Anthropic credit was exhausted, so every frame went through
the QA unchecked -- the one account in the pipeline that was not the fal
balance everything else spends. `MUSEFORGE_LLM_PROVIDER=falai` moves every
Claude call onto fal's chat-completions route, measured on the real endpoint
before this was written ($0.0025 for a JSON answer, $0.0031 for a vision call,
$0.0597 for a four-scene screenplay with reasoning, all valid JSON).

The callers keep their hard-won handling of the SDK's surface, so the fal
client has to speak it: the same message shape, and the SDK's own exception
classes, or `classify` and every `except anthropic.APIStatusError` would stop
meaning what they mean.
"""

import json
import os
import sys

import anthropic
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import llm_provider  # noqa: E402
from tools.anthropic_request import classify  # noqa: E402


@pytest.fixture
def on_fal(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_LLM_PROVIDER", "falai")
    monkeypatch.setenv("FAL_KEY", "fal-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.delenv("FALAI_LLM_MODEL", raising=False)


def _completion(text, finish="stop", **usage):
    return {
        "choices": [{"finish_reason": finish, "message": {"content": text}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "cost": 0.01, **usage},
    }


def test_nothing_changes_until_the_provider_is_chosen(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("FAL_KEY", "fal-key")
    assert llm_provider.provider() == "anthropic"
    assert llm_provider.api_key() == "sk-ant"
    assert isinstance(llm_provider.make_client("sk-ant"), anthropic.AsyncAnthropic)


def test_the_key_guard_looks_at_fal_when_claude_runs_there(on_fal):
    # A deployment that moved to fal has no Anthropic key, and every caller
    # reads "no key" as "no LLM": QA skipped, template script.
    assert llm_provider.api_key() == "fal-key"


def test_a_system_prompt_sent_as_cache_blocks_arrives_as_one_system_message(on_fal):
    payload = llm_provider.build_payload(
        model="claude-sonnet-5",
        max_tokens=4000,
        system=[{"type": "text", "text": "Be brief.", "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": "hi"}],
    )
    assert payload["model"] == "anthropic/claude-sonnet-5"
    assert payload["messages"][0] == {"role": "system", "content": "Be brief."}
    assert "cache_control" not in json.dumps(payload)


def test_a_frame_goes_as_image_urls_and_the_schema_is_said_in_the_prompt(on_fal):
    payload = llm_provider.build_payload(
        model="claude-sonnet-5",
        max_tokens=512,
        thinking={"type": "disabled"},
        output_config={
            "effort": "low",
            "format": {"type": "json_schema", "schema": {"type": "object", "properties": {"ok": {"type": "boolean"}}}},
        },
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "url", "url": "https://x/f.png"}},
                {"type": "text", "text": "Is it fine?"},
            ],
        }],
    )
    assert payload["image_urls"] == ["https://x/f.png"]
    assert payload["response_format"] == {"type": "json_object"}
    last = payload["messages"][-1]["content"]
    assert last.startswith("Is it fine?") and '"ok"' in last
    assert "reasoning" not in payload  # thinking was switched off


def test_the_screenwriter_still_thinks_but_never_more_than_the_answer_can_afford(on_fal):
    big = llm_provider.build_payload(
        model="claude-sonnet-5", max_tokens=32000,
        messages=[{"role": "user", "content": "x"}],
    )
    assert big["reasoning"] == {"max_tokens": 4000}
    small = llm_provider.build_payload(
        model="claude-sonnet-5", max_tokens=1200,
        messages=[{"role": "user", "content": "x"}],
    )
    assert "reasoning" not in small


def test_a_json_answer_in_a_code_fence_reaches_the_caller_bare():
    message = llm_provider.parse_response(_completion('```json\n{"a": 1}\n```'))
    text = next(b.text for b in message.content if b.type == "text")
    assert json.loads(text) == {"a": 1}


def test_running_out_of_tokens_reads_as_max_tokens_not_as_an_answer():
    message = llm_provider.parse_response(_completion("{\"a\":", finish="length"))
    assert message.stop_reason == "max_tokens"
    assert message.usage.output_tokens == 20


def test_a_content_filter_stop_is_a_refusal_the_callers_already_understand():
    from tools.anthropic_request import refusal_of

    message = llm_provider.parse_response(_completion("", finish="content_filter"))
    assert refusal_of(message) == "unspecified"


@pytest.mark.parametrize(
    "error, kind, retryable",
    [
        (RuntimeError("fal.ai job x failed: 401 Unauthorized"), "auth", False),
        (RuntimeError("HTTP 429 rate limit"), "rate_limit", True),
        (RuntimeError("upstream exploded"), "server", True),
    ],
)
def test_a_fal_failure_is_sorted_the_way_an_anthropic_one_is(error, kind, retryable):
    failure = classify(llm_provider.translate(error))
    assert (failure.kind, failure.retryable) == (kind, retryable)


async def test_a_busy_minute_is_retried_and_a_dead_key_is_not(on_fal, monkeypatch):
    calls = []

    async def flaky(client, endpoint, payload, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("429 rate limit")
        return _completion('{"ok": true}')

    async def no_sleep(_):
        return None

    monkeypatch.setattr("tools.falai_common.fal_generate", flaky)
    monkeypatch.setattr(llm_provider.asyncio, "sleep", no_sleep)
    client = llm_provider.make_client("fal-key")
    message = await client.messages.create(
        model="claude-sonnet-5", max_tokens=100,
        messages=[{"role": "user", "content": "x"}],
    )
    assert len(calls) == 2 and message.stop_reason == "end_turn"

    calls.clear()

    async def dead(client, endpoint, payload, **kw):
        calls.append(1)
        raise RuntimeError("401 Unauthorized")

    monkeypatch.setattr("tools.falai_common.fal_generate", dead)
    with pytest.raises(anthropic.AuthenticationError):
        await client.messages.create(
            model="claude-sonnet-5", max_tokens=100,
            messages=[{"role": "user", "content": "x"}],
        )
    assert len(calls) == 1


async def test_the_streaming_callers_get_their_final_message(on_fal, monkeypatch):
    async def ok(client, endpoint, payload, **kw):
        return _completion('{"title": "t"}')

    monkeypatch.setattr("tools.falai_common.fal_generate", ok)
    client = llm_provider.make_client("fal-key")
    async with client.messages.stream(
        model="claude-sonnet-5", max_tokens=100,
        messages=[{"role": "user", "content": "x"}],
    ) as stream:
        message = await stream.get_final_message()
    assert message.stop_reason == "end_turn"
    assert json.loads(message.content[0].text) == {"title": "t"}


async def test_the_frame_judge_scores_a_frame_without_an_anthropic_account(on_fal, monkeypatch):
    from tools.frame_judge import judge_frame

    seen = {}

    async def judge(client, endpoint, payload, **kw):
        seen.update(payload)
        return _completion(json.dumps(
            {"identity": 3, "outfit": 3, "setting": 2, "face_readable": 3,
             "cast_closed": 3, "note": ""}
        ))

    monkeypatch.setattr("tools.falai_common.fal_generate", judge)
    verdict = await judge_frame(
        "https://x/frame.png", ["https://x/ref.png"], "a man", "a coat",
        "a hut", llm_provider.api_key(),
    )
    assert verdict is not None and verdict["scores"]["setting"] == 2
    assert seen["image_urls"] == ["https://x/ref.png", "https://x/frame.png"]
