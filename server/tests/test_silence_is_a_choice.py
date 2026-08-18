"""Silence is an instrument, and it has to be spent deliberately.

DIALOGUE_CLAUSE used to ban the silent SCENE in order to prevent the silent
FILM. That bought a technical guarantee -- an audio stream, captions, voice
tracks -- with a real dramatic instrument: a look held instead of an answer, a
door closed on a sentence nobody finishes. Banned outright, every beat gets
discharged through speech, which is the flattest way to play a scene.

So one scene may be silent and the rest must speak. The scenes that do speak
carry the audio stream and the captions, so the failure the ban existed for
cannot come back; and a script that spends silence more than once is reported
rather than quietly delivered, because from the finished video it just looks
like scenes where nobody bothered to speak.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.character import DramaScript  # noqa: E402


def _spoken(action="She waits.", who="Margit", line="Not tonight."):
    return {"action": action, "dialogue": [{"character": who, "line": line}]}


def _silent(action="She holds the look."):
    return {"action": action, "dialogue": []}


# ── what the writer is told ─────────────────────────────────────────────────


def test_the_clause_allows_exactly_one_silent_scene():
    agent = ScreenwriterAgent(demo=True)
    clause = agent._system_prompt("en", require_dialogue=True)

    assert "SPOKEN DRAMA" in clause
    # The instrument is restored...
    assert "at most once" in clause
    assert "silence is the dramatic point" in clause
    # ...and bounded, in both directions.
    assert "Never leave two scenes silent" in clause
    assert "could not think of a line" in clause


def test_a_run_with_no_voices_is_never_told_about_silent_scenes():
    """The clause is the voiced run's rule. A silent film is still a
    legitimate thing to write, and the base prompt still says so."""
    agent = ScreenwriterAgent(demo=True)
    assert "SPOKEN DRAMA" not in agent._system_prompt("en")


# ── what happens when the writer ignores it ─────────────────────────────────


async def _run_with(scenes, tmp_path, monkeypatch, dialogue=True):
    from unittest.mock import AsyncMock

    from pipelines import idea2video as pipeline_mod

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")
    pipeline = pipeline_mod.Idea2VideoPipeline("test-key")
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline._lock_location_plate = AsyncMock(return_value=None)
    pipeline.script2video.run = AsyncMock(
        return_value={"path": "scene.mp4", "shots": []}
    )
    pipeline._assemble_final_drama = AsyncMock(return_value=str(tmp_path / "out.mp4"))
    pipeline._generate_dialogue = AsyncMock(return_value=None)

    return await pipeline.continue_from_script(
        DramaScript(title="T", logline="L", scenes=scenes),
        working_dir=str(tmp_path / "job"),
        dialogue_enabled=dialogue,
    )


@pytest.mark.asyncio
async def test_one_silent_scene_passes_without_a_word_of_complaint(
    tmp_path, monkeypatch
):
    """The whole point of the change: this is a director's choice, and a
    product that warns about it has not actually restored the instrument."""
    result = await _run_with(
        [_spoken(), _silent(), _spoken()], tmp_path, monkeypatch
    )

    assert not any("play silent" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_two_silent_scenes_are_reported(tmp_path, monkeypatch):
    """Invisible from the finished video, which just looks like scenes where
    nobody bothered to speak -- on a run the dialogue surcharge was paid for."""
    result = await _run_with(
        [_spoken(), _silent(), _silent(), _spoken()], tmp_path, monkeypatch
    )

    notice = [w for w in result["warnings"] if "play silent" in w]
    assert notice, result["warnings"]
    assert "2 of 4 scenes" in notice[0]


@pytest.mark.asyncio
async def test_a_wholly_silent_script_still_raises_the_original_alarm(
    tmp_path, monkeypatch
):
    """The failure the ban existed for. Still caught, and still named for what
    it is rather than as a count of silent scenes."""
    result = await _run_with([_silent(), _silent()], tmp_path, monkeypatch)

    assert any("no spoken lines" in w for w in result["warnings"])


@pytest.mark.asyncio
async def test_an_unvoiced_run_is_not_warned_about_silence_at_all(
    tmp_path, monkeypatch
):
    """Nobody asked for voices, so every scene being silent is the product
    working. A warning here would be noise on the most common configuration."""
    result = await _run_with(
        [_silent(), _silent(), _silent()], tmp_path, monkeypatch, dialogue=False
    )

    assert not any("play silent" in w for w in result["warnings"])
