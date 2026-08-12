"""Setting lock: DramaScript fields + frame_prompt injection + QA fail-open."""
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _qa_message(text):
    """One text block, as `thinking: {"type": "disabled"}` returns.

    These fixtures used to be raw `{"content": [{"type": "text", ...}]}`
    dicts fed through a mocked httpx client — which is why they kept passing
    while production died on `content[0]["text"]`: the mock never produced
    the leading thinking block a real Sonnet 5 response carries. They now go
    through the SDK client the code actually calls.
    """
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason="end_turn",
    )


def _patch_qa_client(result):
    """Patch anthropic.AsyncAnthropic; `result` is a message or an exception."""
    import anthropic

    async def fake_create(*args, **kwargs):
        if isinstance(result, Exception):
            raise result
        return result

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = SimpleNamespace(create=fake_create)

    return patch.object(anthropic, "AsyncAnthropic", _FakeClient)



def test_drama_script_setting_defaults_empty():
    from interfaces.character import DramaScript

    script = DramaScript(title="T", logline="L", scenes=["s1"])
    assert script.setting_location == ""
    assert script.setting_time_of_day == ""
    assert script.setting_era == ""


def test_write_template_sets_neutral_setting():
    from agents.screenwriter import ScreenwriterAgent

    script = ScreenwriterAgent(demo=True)._write_template("Maya walks alone", "Cinematic", 3)
    assert script.setting_time_of_day == "midday"
    assert script.setting_location
    assert script.setting_era == "present day"


def test_build_frame_prompt_empty_setting_matches_legacy_shape():
    """Empty setting must not inject a broken 'Setting: , .' clause."""
    from pipelines.script2video import build_frame_prompt

    shot = SimpleNamespace(
        visual_desc="Maya walks the pier",
        shot_type="medium shot",
        lens="50mm",
    )
    prompt = build_frame_prompt("Cinematic", shot)
    assert prompt.startswith("Cinematic style. Maya walks the pier.")
    assert "Shot type: medium shot. Lens: 50mm." in prompt
    assert "Setting:" not in prompt
    # No characters passed -> no identity clause to inject.
    assert "Character appearance is FIXED" not in prompt


def test_build_frame_prompt_injects_setting_when_present():
    from pipelines.script2video import build_frame_prompt

    shot = SimpleNamespace(
        visual_desc="Maya walks the pier",
        shot_type="medium shot",
        lens="50mm",
    )
    prompt = build_frame_prompt(
        "Cinematic",
        shot,
        setting_location="coastal village, wooden pier",
        setting_time_of_day="sunset",
        setting_era="present day",
    )
    assert "Setting: coastal village, wooden pier, sunset, present day." in prompt
    assert "Maya walks the pier" in prompt


def test_storyboard_setting_line_omitted_when_empty():
    from agents.storyboard_artist import StoryboardArtist

    assert StoryboardArtist._format_setting_line("", "", "") == ""
    line = StoryboardArtist._format_setting_line("harbor", "night", "")
    assert "LOCKED" in line
    assert "harbor" in line
    assert "night" in line


@pytest.mark.asyncio
async def test_verify_frame_fail_open_without_key():
    from tools.character_qa import verify_frame

    result = await verify_frame(
        frame_url="https://example.com/f.jpg",
        expected_character_desc="woman, dark hair",
        expected_setting="coastal village, sunset",
        anthropic_api_key="",
    )
    assert result == {"character_ok": True, "setting_ok": True, "issue": ""}


@pytest.mark.asyncio
async def test_verify_frame_fail_open_on_http_error():
    from tools import character_qa as qa_mod

    with _patch_qa_client(RuntimeError("network down")):
        result = await qa_mod.verify_frame(
            frame_url="https://example.com/f.jpg",
            expected_character_desc="woman",
            expected_setting="harbor, night",
            anthropic_api_key="fake-key",
        )
    assert result == {"character_ok": True, "setting_ok": True, "issue": ""}


@pytest.mark.asyncio
async def test_verify_frame_parses_both_flags():
    from tools import character_qa as qa_mod

    with _patch_qa_client(_qa_message(
        '{"character_ok": false, "setting_ok": true, '
        '"issue": "the coat color doesn\'t match the reference"}'
    )):
        result = await qa_mod.verify_frame(
            frame_url="https://example.com/f.jpg",
            expected_character_desc="woman",
            expected_setting="harbor, night",
            anthropic_api_key="fake-key",
        )
    assert result == {
        "character_ok": False,
        "setting_ok": True,
        "issue": "the coat color doesn't match the reference",
    }


@pytest.mark.asyncio
async def test_verify_frame_omits_issue_when_both_ok():
    """issue must stay empty when there's nothing to repair, even if the
    model includes stray text in that field."""
    from tools import character_qa as qa_mod

    with _patch_qa_client(_qa_message(
        '{"character_ok": true, "setting_ok": true, "issue": "looks fine"}'
    )):
        result = await qa_mod.verify_frame(
            frame_url="https://example.com/f.jpg",
            expected_character_desc="woman",
            expected_setting="harbor, night",
            anthropic_api_key="fake-key",
        )
    assert result == {"character_ok": True, "setting_ok": True, "issue": ""}


@pytest.mark.asyncio
async def test_verify_frame_truncates_overlong_issue():
    """A misbehaving model returning a long issue string must be capped to
    <=15 words before it's usable in a downstream repair prompt."""
    from tools import character_qa as qa_mod

    long_issue = " ".join(f"word{i}" for i in range(40))
    with _patch_qa_client(_qa_message(
        json.dumps({"character_ok": False, "setting_ok": True, "issue": long_issue})
    )):
        result = await qa_mod.verify_frame(
            frame_url="https://example.com/f.jpg",
            expected_character_desc="woman",
            expected_setting="harbor, night",
            anthropic_api_key="fake-key",
        )
    assert len(result["issue"].split()) == 15
