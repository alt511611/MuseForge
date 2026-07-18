"""Storyboard artist cost-control tests."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402


def _three_shots():
    return [
        StoryboardShot(
            idx=i,
            visual_desc=f"Shot {i}",
            motion_desc="pan",
            audio_desc="ambient",
            shot_type="medium",
            camera_movement="static",
            lens="50mm",
            duration_seconds=5.0,
        )
        for i in range(3)
    ]


@pytest.mark.asyncio
async def test_design_storyboard_hard_caps_to_one_shot(monkeypatch):
    """Even if the LLM returns 3 shots, design_storyboard must return exactly 1."""
    artist = StoryboardArtist(api_key="fake-key-for-test")

    async def fake_claude(*_args, **_kwargs):
        return _three_shots()

    monkeypatch.setattr(artist, "_design_with_claude", fake_claude)

    chars = [
        CharacterInScene(
            idx=0,
            name="Maya",
            is_visible=True,
            static_features="dark hair",
            dynamic_features="determined",
        )
    ]
    result = await artist.design_storyboard(
        script="Maya opens the door and steps into the rain.",
        characters=chars,
        director_style="slow_cinematic",
    )

    assert len(result) == 1
    assert result[0].idx == 0
    assert result[0].visual_desc == "Shot 0"


@pytest.mark.asyncio
async def test_design_template_still_returns_one_shot():
    """Template fallback remains a single shot (unchanged)."""
    artist = StoryboardArtist(api_key="")  # forces template path
    chars = [
        CharacterInScene(
            idx=0,
            name="Alex",
            is_visible=True,
            static_features="tall",
            dynamic_features="calm",
        )
    ]
    result = await artist.design_storyboard(
        script="Alex walks through the empty hall.",
        characters=chars,
    )
    assert len(result) == 1
