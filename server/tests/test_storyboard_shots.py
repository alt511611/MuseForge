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
    # Force the direct-Anthropic fallback path regardless of whether
    # MUAPI_KEY leaked into os.environ from another test module's
    # os.environ.setdefault() (several sibling test files do this at
    # import time, and it persists for the rest of the pytest session).
    artist.muapi_key = ""

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
async def test_design_storyboard_caps_muapi_path_too(monkeypatch):
    """Regression test: the MuAPI path (tried FIRST, before the direct-
    Anthropic fallback) was previously missing the same 1-shot cap,
    silently defeating the cost-control fix for the primary code path.
    """
    import json as json_mod
    import agents.storyboard_artist as sb_mod

    artist = StoryboardArtist(api_key="")
    artist.muapi_key = "fake-muapi-key"  # force the MuAPI branch to be taken

    three_shots_json = json_mod.dumps(
        [
            {
                "idx": i,
                "visual_desc": f"Shot {i}",
                "motion_desc": "pan",
                "audio_desc": "ambient",
                "shot_type": "medium",
                "camera_movement": "static",
                "lens": "50mm",
                "duration_seconds": 5.0,
            }
            for i in range(3)
        ]
    )

    async def fake_complete_via_muapi(*_args, **_kwargs):
        return three_shots_json

    monkeypatch.setattr(sb_mod, "complete_via_muapi", fake_complete_via_muapi)

    chars = [
        CharacterInScene(
            idx=0, name="Maya", is_visible=True,
            static_features="dark hair", dynamic_features="determined",
        )
    ]
    result = await artist.design_storyboard(
        script="Maya opens the door and steps into the rain.",
        characters=chars,
        director_style="slow_cinematic",
    )

    assert len(result) == 1, (
        f"MuAPI path returned {len(result)} shots -- the 1-shot cost cap "
        "isn't being applied to the PRIMARY (MuAPI) code path"
    )


@pytest.mark.asyncio
async def test_design_template_still_returns_one_shot():
    """Template fallback remains a single shot (unchanged)."""
    artist = StoryboardArtist(api_key="")  # forces template path
    artist.muapi_key = ""  # avoid a real network attempt if MUAPI_KEY leaked
    # in from another test module's os.environ.setdefault() call
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
