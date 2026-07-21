"""Optional dialogue schema, prompting, and character voice locking."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_drama_script_accepts_structured_and_legacy_scenes():
    from interfaces.character import DramaScript

    script = DramaScript(
        title="Harbor",
        logline="A farewell",
        scenes=[
            {
                "action": "Kemal looks toward the sea.",
                "dialogue": [{"character": "Kemal", "line": "I will return."}],
            },
            "Legacy silent scene.",
        ],
    )

    assert script.scenes[0].action == "Kemal looks toward the sea."
    assert script.scenes[0].dialogue[0].character == "Kemal"
    assert script.scenes[1] == "Legacy silent scene."


def test_dialogue_frame_prompt_avoids_visible_lip_sync_focus():
    from pipelines.script2video import build_frame_prompt

    shot = SimpleNamespace(
        visual_desc="Kemal speaks beside the window",
        shot_type="medium shot",
        lens="50mm",
    )

    plain = build_frame_prompt("Cinematic", shot)
    dialogue = build_frame_prompt("Cinematic", shot, has_dialogue=True)

    assert "mouth should be naturally obscured" not in plain
    assert "mouth should be naturally obscured" in dialogue
    assert "shown in profile" in dialogue


@pytest.mark.asyncio
async def test_empty_dialogue_makes_no_voice_generation_call():
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    generator = MuAPIVoiceGenerator("test-key")
    generator.client.generate = AsyncMock()

    tracks = await generator.generate_scene_dialogue([])

    assert tracks == []
    generator.client.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_character_voice_ids_are_locked_and_reused():
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    generator = MuAPIVoiceGenerator("test-key")
    generator.client.generate = AsyncMock(
        side_effect=["https://audio/1.mp3", "https://audio/2.mp3", "https://audio/3.mp3"]
    )

    tracks = await generator.generate_scene_dialogue(
        [
            {"character": "Kemal", "line": "First line."},
            {"character": "Leyla", "line": "Reply."},
            {"character": "Kemal", "line": "Second line."},
        ]
    )

    calls = generator.client.generate.await_args_list
    kemal_voice = calls[0].args[1]["voice_id"]
    leyla_voice = calls[1].args[1]["voice_id"]

    assert calls[2].args[1]["voice_id"] == kemal_voice
    assert leyla_voice != kemal_voice
    assert tracks[0]["character"] == "Kemal"
    assert tracks[0]["voice_id"] == kemal_voice
    assert tracks[2]["voice_id"] == kemal_voice
    assert all(call.args[0] == "minimax-speech-2.6-hd" for call in calls)


@pytest.mark.asyncio
async def test_pipeline_routes_structured_dialogue_to_voice_layer(tmp_path, monkeypatch):
    from interfaces.character import DramaScript
    from pipelines import idea2video as pipeline_mod

    captured = {}

    class FakeVoiceGenerator:
        def __init__(self, api_key, demo=False):
            pass

        async def generate_scene_dialogue(self, dialogue, is_cancelled=None):
            captured["character"] = dialogue[0].character
            return [
                {
                    "character": dialogue[0].character,
                    "line": dialogue[0].line,
                    "voice_id": "Friendly_Person",
                    "audio_url": "https://audio/line.mp3",
                }
            ]

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")
    monkeypatch.setattr(pipeline_mod, "MuAPIVoiceGenerator", FakeVoiceGenerator)

    pipeline = pipeline_mod.Idea2VideoPipeline("test-key")
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline.script2video.run = AsyncMock(return_value={"path": "scene.mp4", "shots": []})
    pipeline._assemble_final_drama = AsyncMock(
        return_value=str(tmp_path / "not-written-in-unit-test.mp4")
    )
    script = DramaScript(
        title="Harbor",
        logline="A farewell",
        scenes=[
            {
                "action": "Kemal faces the sea.",
                "dialogue": [{"character": "Kemal", "line": "I will return."}],
            }
        ],
    )

    await pipeline.continue_from_script(
        script,
        working_dir=str(tmp_path / "job"),
        dialogue_enabled=True,
    )

    scene_call = pipeline.script2video.run.await_args.kwargs
    assembly_call = pipeline._assemble_final_drama.await_args.kwargs
    assert scene_call["script"] == "Kemal faces the sea."
    assert scene_call["has_dialogue"] is True
    assert captured["character"] == "Kemal"
    assert assembly_call["dialogue_tracks"][0]["scene_index"] == 0
    assert assembly_call["dialogue_tracks"][0]["voice_id"] == "Friendly_Person"
