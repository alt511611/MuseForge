"""Verify the LLM fallback chain: MuAPI (opt-in) -> Anthropic -> refuse.

The chain must never end in a silently-generic script. A template script
ignores the user's idea, so producing one for a paid render is worse than
failing, and the screenwriter raises instead.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


@pytest.mark.asyncio
async def test_screenwriter_refuses_when_muapi_and_claude_both_fail(monkeypatch):
    """No provider answered -> raise, do NOT return the template.

    The template is a generic drama about a character extracted from the
    first capitalised word, in a "generic cinematic location", with no
    dialogue and no wardrobe. Rendering it spends the user's credits on a
    video that matches none of their prompt -- a real, reported failure.
    """
    from agents.screenwriter import ScreenwriterAgent, ScriptGenerationFailed

    async def broken_muapi(*args, **kwargs):
        raise RuntimeError("simulated wrong endpoint slug / schema mismatch")

    monkeypatch.setattr("agents.screenwriter.complete_via_muapi", broken_muapi)
    monkeypatch.setenv("MUAPI_LLM_MODEL", "test-llm-slug")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    agent = ScreenwriterAgent()
    agent.api_key = ""
    with pytest.raises(ScriptGenerationFailed):
        await agent.write_script(
            "A lonely lighthouse keeper finds a message in a bottle."
        )


@pytest.mark.asyncio
async def test_muapi_llm_path_is_skipped_unless_a_model_is_configured(monkeypatch):
    """The MuAPI LLM slug was always a guess, so it must not sit in front of
    the Anthropic path by default -- a guaranteed-failing first hop that also
    makes a downstream misconfiguration land on the template."""
    from agents.screenwriter import ScreenwriterAgent, ScriptGenerationFailed

    called = False

    async def spy_muapi(*args, **kwargs):
        nonlocal called
        called = True
        return "{}"

    monkeypatch.setattr("agents.screenwriter.complete_via_muapi", spy_muapi)
    monkeypatch.delenv("MUAPI_LLM_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    agent = ScreenwriterAgent()
    agent.api_key = ""
    with pytest.raises(ScriptGenerationFailed):
        await agent.write_script("A keeper finds a bottle.")
    assert called is False


@pytest.mark.asyncio
async def test_screenwriter_uses_muapi_when_it_succeeds(monkeypatch):
    from agents.screenwriter import ScreenwriterAgent
    import json

    fake_response = json.dumps({
        "title": "The Bottle",
        "logline": "A keeper finds a message.",
        "mood": "melancholic",
        "estimated_duration_seconds": 24,
        "characters": [{"name": "Sam", "description": "grizzled keeper", "role": "protagonist"}],
        "scenes": ["Sam finds the bottle.", "Sam reads the note.", "Sam looks at the horizon."],
    })

    async def fake_muapi(*args, **kwargs):
        return fake_response

    monkeypatch.setattr("agents.screenwriter.complete_via_muapi", fake_muapi)
    monkeypatch.setenv("MUAPI_LLM_MODEL", "test-llm-slug")

    idea = "A lonely lighthouse keeper finds a message in a bottle."
    agent = ScreenwriterAgent()
    result = await agent.write_script(idea)

    assert result.title == "The Bottle"
    assert len(result.scenes) == 3
    # The user's own words ride along with the script -- the storyboard step
    # is held to them, not just to the screenwriter's paraphrase.
    assert result.user_brief == idea


@pytest.mark.asyncio
async def test_storyboard_falls_back_to_template_when_muapi_and_claude_fail(monkeypatch):
    from agents.storyboard_artist import StoryboardArtist
    from interfaces.character import CharacterInScene

    async def broken_muapi(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr("agents.storyboard_artist.complete_via_muapi", broken_muapi)
    monkeypatch.setenv("MUAPI_LLM_MODEL", "test-llm-slug")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    artist = StoryboardArtist()
    artist.api_key = ""
    chars = [CharacterInScene(idx=0, name="Sam", static_features="grizzled keeper", is_visible=True)]
    shots = await artist.design_storyboard("Sam finds a bottle on the shore.", chars)

    assert len(shots) >= 1
