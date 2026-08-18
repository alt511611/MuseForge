"""What a delivered drama got wrong, turned into tests.

A 24-second harbour drama came back with four separate faults, all of them
invisible to the existing suite:

  1. It was silent. Dialogue was switched on, the script came back with no
     spoken lines, and with music off the master carried no audio stream at
     all -- delivered without a word of explanation.
  2. The brief's one stated event ("the city's power dies the moment she opens
     it") never happened on screen; the closing shot showed a fully lit
     skyline.
  3. The opening shot was the payoff: the container already open and glowing
     behind her, before any scene had opened it.
  4. The protagonist's costume changed three times and she appeared twice in
     one frame, beside a near-copy of herself.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import CharacterInScene, DramaScript  # noqa: E402
from pipelines.idea2video import _format_story_state  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    build_cast_closure_clause,
    build_character_identity_clause,
)


def _scenes():
    return [
        {"action": "Maya walks the pier.", "turn": "Maya notices the humming container"},
        {"action": "She works the seal.", "turn": "Maya decides to open it"},
        {"action": "The door swings.", "turn": "the city's power dies as the door opens"},
    ]


# --- 1. no scene may film a later scene's beat ------------------------------


def test_the_opening_scene_is_told_what_has_not_happened_yet():
    story_so_far, not_yet = _format_story_state(_scenes(), 0)

    assert story_so_far == "", "nothing has happened before the first scene"
    assert "the city's power dies" in not_yet
    assert "Maya decides to open it" in not_yet


def test_the_closing_scene_is_told_what_already_happened():
    story_so_far, not_yet = _format_story_state(_scenes(), 2)

    assert "Maya notices the humming container" in story_so_far
    assert "Maya decides to open it" in story_so_far
    assert not_yet == "", "nothing is left after the last scene"


def test_a_scene_without_a_turn_still_reports_its_beat():
    """A missing turn must not silently re-open the fence: falling back to the
    action line keeps the later scene's content on the do-not-show list."""
    scenes = [{"action": "Maya opens the container."}, {"action": "Later."}]

    _, not_yet = _format_story_state(scenes, 0)

    assert "Later." in not_yet


@pytest.mark.asyncio
async def test_story_state_reaches_the_shot_designer(tmp_path):
    from unittest.mock import AsyncMock

    from pipelines import idea2video as pipeline_mod

    pipeline = pipeline_mod.Idea2VideoPipeline("test-key", demo=True)
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline.script2video.run = AsyncMock(return_value={"path": "scene.mp4", "shots": []})

    await pipeline.continue_from_script(
        DramaScript(title="Harbour", logline="A container hums.", scenes=_scenes()),
        working_dir=str(tmp_path / "job"),
    )

    first_scene = pipeline.script2video.run.await_args_list[0].kwargs
    assert first_scene["story_so_far"] == ""
    assert "the city's power dies" in first_scene["not_yet"]


def test_the_shot_designer_is_told_the_ban_covers_the_aftermath():
    """"Don't show the blackout" is not enough on its own -- the failure mode
    is a shot of the world AFTER the blackout, staged as scene one."""
    block = StoryboardArtist._format_story_state(
        story_so_far="Scene 1: Maya notices the container",
        not_yet="Scene 3: the city's power dies",
    )

    assert "ALREADY HAPPENED" in block
    assert "HAS NOT HAPPENED YET" in block
    assert "aftermath" in block
    assert "DO NOT FILM THE FUTURE" in StoryboardArtist.SYSTEM_PROMPT


# --- 2. the brief's stated event has to actually happen ---------------------


def test_the_screenwriter_is_told_the_brief_s_event_is_the_climax():
    prompt = ScreenwriterAgent().SYSTEM_PROMPT

    assert "THE BRIEF'S EVENT IS THE CLIMAX" in prompt
    assert "DO NOT PRE-EMPT THE EVENT" in prompt


# --- 3. a voiced run may not be written as a silent film --------------------


def test_a_voiced_run_demands_dialogue():
    """Keyed on the section, not on one sentence of it: the rule inside has
    since been bounded (one scene may be silent -- see
    test_silence_is_a_choice), and this test is about WHICH runs get the rule
    at all."""
    agent = ScreenwriterAgent()

    assert "SPOKEN DRAMA" in agent._system_prompt("en", require_dialogue=True)
    # Unvoiced runs keep the base prompt, where silence is a valid choice.
    assert "SPOKEN DRAMA" not in agent._system_prompt("en")


def test_the_language_clause_and_the_dialogue_clause_coexist():
    prompt = ScreenwriterAgent()._system_prompt("tr", require_dialogue=True)

    assert "Turkish" in prompt
    assert "SPOKEN DRAMA" in prompt


@pytest.mark.asyncio
async def test_the_dialogue_toggle_reaches_the_screenwriter(monkeypatch):
    """Otherwise the screenwriter is free to write a silent film on the very
    run the user paid for voices."""
    captured = {}

    async def fake_write_script(self, idea, style="Cinematic", num_scenes=3,
                                user_requirement="", preset_characters=None,
                                language="en", require_dialogue=False, **_):
        captured["require_dialogue"] = require_dialogue
        return DramaScript(title="T", logline="L", scenes=[{"action": "A."}])

    from agents import screenwriter as screenwriter_mod
    from pipelines import idea2video as pipeline_mod

    monkeypatch.setattr(
        screenwriter_mod.ScreenwriterAgent, "write_script", fake_write_script
    )
    pipeline = pipeline_mod.Idea2VideoPipeline("test-key", demo=True)

    await pipeline.write_script_only("idea", dialogue_enabled=True)

    assert captured["require_dialogue"] is True


# --- 4. silence is reported, never just delivered ---------------------------


@pytest.mark.asyncio
async def test_a_silent_script_on_a_voiced_run_is_reported(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from pipelines import idea2video as pipeline_mod

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")
    pipeline = pipeline_mod.Idea2VideoPipeline("test-key")
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline._lock_location_plate = AsyncMock(return_value=None)
    pipeline.script2video.run = AsyncMock(return_value={"path": "scene.mp4", "shots": []})
    pipeline._assemble_final_drama = AsyncMock(return_value=str(tmp_path / "out.mp4"))

    result = await pipeline.continue_from_script(
        DramaScript(title="T", logline="L", scenes=[{"action": "She waits.", "dialogue": []}]),
        working_dir=str(tmp_path / "job"),
        dialogue_enabled=True,
    )

    assert any("no spoken lines" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_dialogue_switched_off_on_the_server_is_reported(tmp_path, monkeypatch):
    """The user is charged nothing for it, but they still asked -- and a
    silent video with no explanation reads as a broken feature."""
    from unittest.mock import AsyncMock

    from pipelines import idea2video as pipeline_mod

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "0")
    pipeline = pipeline_mod.Idea2VideoPipeline("test-key")
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline._lock_location_plate = AsyncMock(return_value=None)
    pipeline.script2video.run = AsyncMock(return_value={"path": "scene.mp4", "shots": []})
    pipeline._assemble_final_drama = AsyncMock(return_value=str(tmp_path / "out.mp4"))

    result = await pipeline.continue_from_script(
        DramaScript(
            title="T",
            logline="L",
            scenes=[{"action": "She waits.", "dialogue": [{"character": "Maya", "line": "Hi."}]}],
        ),
        working_dir=str(tmp_path / "job"),
        dialogue_enabled=True,
    )

    assert any("switched off on this server" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_a_fully_delivered_run_carries_no_warnings(tmp_path):
    from unittest.mock import AsyncMock

    from pipelines import idea2video as pipeline_mod

    pipeline = pipeline_mod.Idea2VideoPipeline("test-key", demo=True)
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline.script2video.run = AsyncMock(return_value={"path": "scene.mp4", "shots": []})

    result = await pipeline.continue_from_script(
        DramaScript(title="T", logline="L", scenes=[{"action": "She waits."}]),
        working_dir=str(tmp_path / "job"),
    )

    assert result["warnings"] == []


# --- 5. one cast, one costume ----------------------------------------------


def test_the_cast_is_closed_to_the_named_characters():
    clause = build_cast_closure_clause(
        [
            CharacterInScene(idx=0, name="Maya", static_features="woman, 30s"),
            CharacterInScene(idx=1, name="Voice", static_features="unseen", is_visible=False),
            CharacterInScene(idx=2, name="Blank", static_features="  "),
        ]
    )

    assert "Maya" in clause
    assert "Voice" not in clause
    assert "Blank" not in clause
    # The delivered drama put the protagonist on screen twice at once.
    assert "never show the same character twice in one frame" in clause


def test_an_undescribed_cast_produces_no_roll_call():
    assert build_cast_closure_clause([]) == ""
    assert build_cast_closure_clause(
        [CharacterInScene(idx=0, name="Blank", static_features="")]
    ) == ""


def test_the_costume_is_locked_even_when_the_wardrobe_is_named():
    """A stated wardrobe used to be considered self-enforcing. It was not:
    the same character's yellow overalls became a slicker, then a hoodie."""
    clause = build_character_identity_clause(
        [
            CharacterInScene(
                idx=0,
                name="Maya",
                static_features="woman, 30s",
                wardrobe="yellow bib overalls, grey beanie",
            )
        ]
    )

    assert "yellow bib overalls" in clause
    assert "Costume is LOCKED" in clause
