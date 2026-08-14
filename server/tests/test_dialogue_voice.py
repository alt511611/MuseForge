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
    # The field MuAPI's schema declares is `dialogue`; `inputs` is rejected
    # with a 422 and silences the whole drama.
    assert "inputs" not in payload
    assert len(payload["dialogue"]) == 3
    assert payload["stability"] == 0.5

    kemal_voice = payload["dialogue"][0]["voice_id"]
    leyla_voice = payload["dialogue"][1]["voice_id"]
    assert payload["dialogue"][2]["voice_id"] == kemal_voice
    assert leyla_voice != kemal_voice
    assert kemal_voice in MuAPIVoiceGenerator.SYSTEM_VOICE_IDS

    assert tracks[0]["character"] == "Kemal"
    assert tracks[0]["voice_id"] == kemal_voice
    assert tracks[0]["audio_url"] == "https://audio/scene.mp3"
    # Combined audio only on the first track; later rows are caption-only.
    assert "audio_url" not in tracks[1]
    assert tracks[2]["voice_id"] == kemal_voice


def test_voice_ids_are_elevenlabs_ids_not_display_labels():
    """Every drama came back silent because the cast was sent as playground
    labels ("George - Warm") where the endpoint wants ElevenLabs voice IDs."""
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    ids = set(MuAPIVoiceGenerator.SYSTEM_VOICE_IDS)
    ids |= set(MuAPIVoiceGenerator.FEMALE_VOICE_IDS)
    ids |= set(MuAPIVoiceGenerator.MALE_VOICE_IDS)
    for voice_id in ids:
        assert " " not in voice_id and "-" not in voice_id, voice_id
        assert len(voice_id) == 20, voice_id
    # Female and male pools must stay disjoint, or casting is meaningless.
    assert not set(MuAPIVoiceGenerator.FEMALE_VOICE_IDS) & set(
        MuAPIVoiceGenerator.MALE_VOICE_IDS
    )


@pytest.mark.asyncio
async def test_provider_failure_reaches_the_caller():
    """Swallowing the provider error made a broken payload look exactly like
    a scene with no lines, so nothing in the logs named the real cause."""
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    generator = MuAPIVoiceGenerator("test-key")
    generator.client.generate = AsyncMock(side_effect=RuntimeError("422 unprocessable"))

    with pytest.raises(RuntimeError):
        await generator.generate_scene_dialogue(
            [{"character": "Kemal", "line": "First line."}]
        )


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

        async def generate_scene_dialogue(self, dialogue, is_cancelled=None, language="en"):
            captured["character"] = dialogue[0].character
            return [
                {
                    "character": dialogue[0].character,
                    "line": dialogue[0].line,
                    "voice_id": "JBFqnCBsd6RMkjVDRZzb",
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
    assert assembly_call["dialogue_tracks"][0]["voice_id"] == "JBFqnCBsd6RMkjVDRZzb"


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


def test_the_cast_can_be_replaced_without_a_deploy(monkeypatch):
    """The provider publishes no list of valid voice values, and a wrong one
    is only discovered by a finished drama arriving silent. When the answer
    turns up, it has to be applicable in one restart."""
    from tools.muapi_voice_generator import _voices

    monkeypatch.setenv("MUSEFORGE_VOICE_IDS", " voice-a , voice-b ")
    assert _voices("MUSEFORGE_VOICE_IDS", ("default",)) == ("voice-a", "voice-b")


def test_an_unset_or_empty_override_keeps_the_shipped_cast(monkeypatch):
    from tools.muapi_voice_generator import _voices

    monkeypatch.delenv("MUSEFORGE_VOICE_IDS", raising=False)
    assert _voices("MUSEFORGE_VOICE_IDS", ("default",)) == ("default",)

    monkeypatch.setenv("MUSEFORGE_VOICE_IDS", " , ")
    assert _voices("MUSEFORGE_VOICE_IDS", ("default",)) == ("default",)


# --- which spelling of a voice the provider wants ------------------------


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _forget_the_negotiated_form():
    """The accepted form is memoised for the whole process on purpose; tests
    must not inherit one another's answer."""
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    MuAPIVoiceGenerator._accepted_form = None
    yield
    MuAPIVoiceGenerator._accepted_form = None


class _Provider:
    """A MuAPI that accepts exactly one spelling of a voice value."""

    def __init__(self, accepts):
        self.accepts = accepts
        self.seen = []

    async def generate(self, endpoint, payload, **kwargs):
        values = [turn["voice_id"] for turn in payload["dialogue"]]
        self.seen.append(list(values))
        if not all(self.accepts(v) for v in values):
            raise RuntimeError(
                f"HTTP 400: Invalid voice parameter: {values[0]!r} is not allowed"
            )
        return "https://cdn/scene.mp3"


def _generator(provider):
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    gen = MuAPIVoiceGenerator("key")
    gen.client = provider
    return gen


LINES = [{"character": "Mara", "line": "It's warm."}]


@pytest.mark.asyncio
async def test_the_shipped_id_form_is_tried_first_and_costs_one_request():
    """Nothing changes for a provider that was always happy."""
    provider = _Provider(lambda v: len(v) == 20)
    tracks = await _generator(provider).generate_scene_dialogue(LINES)

    assert len(provider.seen) == 1
    assert tracks[0]["audio_url"] == "https://cdn/scene.mp3"


@pytest.mark.asyncio
async def test_a_rejected_voice_is_retried_in_the_other_spellings():
    """The delivered failure: every request came back "Invalid voice
    parameter", and the only way to learn what IS valid was another paid
    render."""
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    provider = _Provider(lambda v: v in MuAPIVoiceGenerator.VOICE_LABELS.values())
    tracks = await _generator(provider).generate_scene_dialogue(LINES)

    assert tracks[0]["audio_url"] == "https://cdn/scene.mp3"
    assert len(provider.seen) == 2
    assert provider.seen[0][0] in MuAPIVoiceGenerator.SYSTEM_VOICE_IDS
    assert " - " in provider.seen[1][0]


@pytest.mark.asyncio
async def test_a_bare_display_name_is_the_last_form_tried():
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    provider = _Provider(lambda v: v in MuAPIVoiceGenerator.VOICE_NAMES.values())
    tracks = await _generator(provider).generate_scene_dialogue(LINES)

    assert tracks[0]["audio_url"] == "https://cdn/scene.mp3"
    assert len(provider.seen) == 3
    assert provider.seen[2][0] in MuAPIVoiceGenerator.VOICE_NAMES.values()


@pytest.mark.asyncio
async def test_the_answer_is_paid_for_once_not_once_per_scene():
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    provider = _Provider(lambda v: v in MuAPIVoiceGenerator.VOICE_NAMES.values())
    generator = _generator(provider)

    await generator.generate_scene_dialogue(LINES)
    await generator.generate_scene_dialogue(LINES)

    # 3 to find it, then 1 per scene from then on -- not 3 per scene.
    assert len(provider.seen) == 4
    assert MuAPIVoiceGenerator._accepted_form == "name"


@pytest.mark.asyncio
async def test_a_failure_that_is_not_about_the_voice_is_not_shopped_around():
    """An outage or a bad key is not fixed by respelling anything, and each
    retry is a round trip the user waits through."""
    calls = []

    class _Down:
        async def generate(self, endpoint, payload, **kwargs):
            calls.append(payload)
            raise RuntimeError("HTTP 503: upstream unavailable")

    with pytest.raises(RuntimeError, match="upstream unavailable"):
        await _generator(_Down()).generate_scene_dialogue(LINES)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_every_form_failing_raises_the_provider_s_own_last_words():
    provider = _Provider(lambda v: False)

    with pytest.raises(RuntimeError, match="Invalid voice parameter"):
        await _generator(provider).generate_scene_dialogue(LINES)

    assert len(provider.seen) == 4


@pytest.mark.asyncio
async def test_an_opaque_4xx_is_still_treated_as_a_refused_voice():
    """The delivered failure. The provider refuses the voice at submit time
    and says only "Internal Error, Please try again later." -- no word this
    file could match. Every scene gave up after one request and the drama
    shipped silent with two working spellings never tried."""
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    class _Coy(_Provider):
        async def generate(self, endpoint, payload, **kwargs):
            try:
                return await super().generate(endpoint, payload, **kwargs)
            except RuntimeError:
                raise RuntimeError(
                    "MuAPI request failed after 1 attempt(s): "
                    "HTTP 400: Internal Error, Please try again later."
                ) from None

    provider = _Coy(lambda v: v in MuAPIVoiceGenerator.VOICE_NAMES.values())
    tracks = await _generator(provider).generate_scene_dialogue(LINES)

    assert tracks[0]["audio_url"] == "https://cdn/scene.mp3"
    assert len(provider.seen) == 3


@pytest.mark.asyncio
async def test_a_cast_no_provider_accepts_still_speaks_in_its_default_voice():
    """One voice for every character is a loss; a drama that says nothing at
    all is a bigger one. The provider's own published default is the last
    thing tried before giving up."""
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    default = MuAPIVoiceGenerator._PROVIDER_DEFAULT
    provider = _Provider(lambda v: v == default)

    tracks = await _generator(provider).generate_scene_dialogue(LINES)

    assert tracks[0]["audio_url"] == "https://cdn/scene.mp3"
    assert provider.seen[-1] == [default]


@pytest.mark.asyncio
async def test_an_operator_override_is_sent_exactly_as_written(monkeypatch):
    """Someone who set MUSEFORGE_VOICE_IDS knows something we do not; their
    value must not be translated into a form they did not ask for."""
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    generator = MuAPIVoiceGenerator("key")
    generator._character_voices = {"mara": "custom-voice-7"}
    provider = _Provider(lambda v: False)
    generator.client = provider

    with pytest.raises(RuntimeError):
        await generator.generate_scene_dialogue(LINES)

    # Sent once as written -- not three times, because "id", "label" and
    # "name" all spell an unknown value the same way -- and then only the
    # provider's own default, which is the last resort before silence.
    sent = [v for seen in provider.seen for v in seen]
    assert sent == ["custom-voice-7", MuAPIVoiceGenerator._PROVIDER_DEFAULT]
