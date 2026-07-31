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
    generator.client.generate = AsyncMock(return_value="https://audio/scene.mp3")

    tracks = await generator.generate_scene_dialogue(
        [
            {"character": "Kemal", "line": "First line."},
            {"character": "Leyla", "line": "Reply."},
            {"character": "Kemal", "line": "Second line."},
        ]
    )

    # One batch request for the whole scene (ElevenLabs dialogue v3).
    assert generator.client.generate.await_count == 1
    call = generator.client.generate.await_args
    assert call.args[0] == "elevenlabs-text-to-dialogue-v3"
    payload = call.args[1]
    assert "inputs" in payload
    assert len(payload["inputs"]) == 3
    assert payload["stability"] == 0.5

    kemal_voice = payload["inputs"][0]["voice_id"]
    leyla_voice = payload["inputs"][1]["voice_id"]
    assert payload["inputs"][2]["voice_id"] == kemal_voice
    assert leyla_voice != kemal_voice
    assert kemal_voice in MuAPIVoiceGenerator.SYSTEM_VOICE_IDS

    assert tracks[0]["character"] == "Kemal"
    assert tracks[0]["voice_id"] == kemal_voice
    assert tracks[0]["audio_url"] == "https://audio/scene.mp3"
    # Combined audio only on the first track; later rows are caption-only.
    assert "audio_url" not in tracks[1]
    assert tracks[2]["voice_id"] == kemal_voice


@pytest.mark.asyncio
async def test_pipeline_routes_structured_dialogue_to_voice_layer(tmp_path, monkeypatch):
    from interfaces.character import DramaScript
    from pipelines import idea2video as pipeline_mod

    captured = {}

    class FakeVoiceGenerator:
        def __init__(self, api_key, demo=False):
            pass

        def cast_characters(self, characters):
            return {}

        async def generate_scene_dialogue(self, dialogue, is_cancelled=None):
            captured["character"] = dialogue[0].character
            return [
                {
                    "character": dialogue[0].character,
                    "line": dialogue[0].line,
                    "voice_id": "George - Warm",
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
    assert assembly_call["dialogue_tracks"][0]["voice_id"] == "George - Warm"


# --- the UI gate --------------------------------------------------------


def test_health_exposes_dialogue_availability(monkeypatch):
    """The client cannot infer the server feature flag from the plan alone,
    so /api/health must surface it -- otherwise the toggle would offer
    something the server silently drops (and bills for)."""
    import api as _api
    from fastapi.testclient import TestClient

    tc = TestClient(_api.app, raise_server_exceptions=False)

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")
    assert tc.get("/api/health").json()["dialogue_available"] is True

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "0")
    assert tc.get("/api/health").json()["dialogue_available"] is False


def test_dialogue_stays_pro_only_and_flag_gated(monkeypatch):
    """Both gates must hold: the server drops dialogue for a non-Pro plan
    and when the feature flag is off, regardless of what the client sends."""
    import api as _api

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")
    with_pro = _api.estimate_generation_seconds(
        3, dialogue_enabled=True, plan="pro", demo=False
    )
    without = _api.estimate_generation_seconds(
        3, dialogue_enabled=False, plan="pro", demo=False
    )
    assert with_pro > without, "Pro + flag on must cost extra wall-clock"

    # Non-Pro plan: silently ignored.
    assert _api.estimate_generation_seconds(
        3, dialogue_enabled=True, plan="creator", demo=False
    ) == _api.estimate_generation_seconds(
        3, dialogue_enabled=False, plan="creator", demo=False
    )

    # Flag off: ignored even for Pro.
    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "0")
    assert _api.estimate_generation_seconds(
        3, dialogue_enabled=True, plan="pro", demo=False
    ) == without
