"""Verify the MuAPI-first LLM fallback chain never breaks generation,
even if MuAPI's exact LLM endpoint/schema guess is wrong.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


@pytest.mark.asyncio
async def test_screenwriter_falls_back_to_template_when_muapi_and_claude_fail(monkeypatch):
    from agents.screenwriter import ScreenwriterAgent

    async def broken_muapi(*args, **kwargs):
        raise RuntimeError("simulated wrong endpoint slug / schema mismatch")

    monkeypatch.setattr("agents.screenwriter.complete_via_muapi", broken_muapi)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    agent = ScreenwriterAgent()
    result = await agent.write_script("A lonely lighthouse keeper finds a message in a bottle.")

    # Must not raise, and must still produce a usable script via the
    # template fallback.
    assert result.title
    assert len(result.scenes) >= 2


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

    agent = ScreenwriterAgent()
    result = await agent.write_script("A lonely lighthouse keeper finds a message in a bottle.")

    assert result.title == "The Bottle"
    assert len(result.scenes) == 3


@pytest.mark.asyncio
async def test_storyboard_falls_back_to_template_when_muapi_and_claude_fail(monkeypatch):
    from agents.storyboard_artist import StoryboardArtist
    from interfaces.character import CharacterInScene

    async def broken_muapi(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr("agents.storyboard_artist.complete_via_muapi", broken_muapi)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    artist = StoryboardArtist()
    chars = [CharacterInScene(idx=0, name="Sam", static_features="grizzled keeper", is_visible=True)]
    shots = await artist.design_storyboard("Sam finds a bottle on the shore.", chars)

    assert len(shots) >= 1
