"""A returning character has to sound like themselves.

Casting is a deterministic hash of the character's NAME, which sounds like it
is already stable across episodes and is not: _assign walks past a voice
another character already holds, so the voice a name lands on depends on who
else is in the cast and in what order they were cast. Add one character to
episode two and the returning lead can be bumped to the next free voice --
same locked face, same wardrobe, same portrait, different person speaking.

Nothing derived can fix that, because the collision is real: two characters
cannot share a voice inside one drama. The only thing that survives a change
of cast is a decision that was written down, so the library entry now carries
its voice and the pipeline reads it back before casting anyone.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene, DramaScript  # noqa: E402
from tools.elevenlabs_voice_generator import ElevenLabsVoiceGenerator  # noqa: E402


def _char(idx, name, features="woman in her seventies"):
    return CharacterInScene(idx=idx, name=name, static_features=features)


def _gen():
    return ElevenLabsVoiceGenerator(api_key="test-key", working_dir="/tmp")


# ── the drift this exists to stop ───────────────────────────────────────────


def test_the_bug_a_castmate_holding_her_slot_moves_the_returning_lead():
    """Demonstrates the mechanism rather than hoping a random cast trips it:
    the hash is stable, the ASSIGNMENT is not. Whoever already holds the voice
    a name hashes to sends that name to the next slot -- which is why a stored
    decision is necessary and a better hash would not help."""
    solo = _gen()
    solo.cast_characters([_char(0, "Margit")])
    alone = solo.voice_id_for_character("Margit")

    # Someone else arrives holding exactly the voice Margit hashes to. Nothing
    # about Margit changed; her name, her description and the hash of both are
    # identical to the run above.
    episode_two = _gen()
    episode_two.lock_voices({"Noor": alone})
    episode_two.cast_characters([_char(0, "Noor"), _char(1, "Margit")])

    assert episode_two.voice_id_for_character("Margit") != alone


# ── the fix ─────────────────────────────────────────────────────────────────


def test_a_locked_voice_is_kept_whoever_else_is_in_the_room():
    gen = _gen()
    gen.lock_voices({"Margit": "voice-from-episode-one"})
    gen.cast_characters(
        [_char(i, n) for i, n in enumerate(["Noor", "Elif", "Margit", "Sena"])]
    )

    assert gen.voice_id_for_character("Margit") == "voice-from-episode-one"


def test_a_locked_voice_is_not_handed_to_anyone_else():
    """The lock has to hold both ways: reserving Margit's voice is worthless if
    the character cast after her is given the same one."""
    gen = _gen()
    gen.lock_voices({"Margit": "voice-from-episode-one"})
    gen.cast_characters([_char(i, n) for i, n in enumerate(["Margit", "Noor"])])

    assert gen.voice_id_for_character("Noor") != "voice-from-episode-one"


def test_locking_is_case_and_whitespace_insensitive():
    """Library entries are typed by users; the cast comes from the model."""
    gen = _gen()
    gen.lock_voices({"  margit ": "voice-x"})
    gen.cast_characters([_char(0, "Margit")])

    assert gen.voice_id_for_character("Margit") == "voice-x"


def test_an_empty_or_missing_lock_changes_nothing():
    """Entries saved before the column existed must cast exactly as before."""
    before = _gen()
    before.cast_characters([_char(0, "Margit"), _char(1, "Noor")])

    after = _gen()
    after.lock_voices({"Margit": "", "Noor": None})
    after.cast_characters([_char(0, "Margit"), _char(1, "Noor")])

    assert after.voice_id_for_character("Margit") == before.voice_id_for_character(
        "Margit"
    )
    assert after.voice_id_for_character("Noor") == before.voice_id_for_character("Noor")


# ── the wiring ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_pipeline_locks_library_voices_before_casting(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from pipelines import idea2video as pipeline_mod

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")

    locked = {}

    class _Recorder:
        def lock_voices(self, voices):
            locked.update(voices)

        def cast_characters(self, characters):
            return {c.name.casefold(): locked.get(c.name, "cast-voice")
                    for c in characters}

        async def generate_scene_dialogue(self, lines, **kwargs):
            return []

    pipeline = pipeline_mod.Idea2VideoPipeline("test-key")
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline._lock_location_plate = AsyncMock(return_value=None)
    pipeline.script2video.run = AsyncMock(
        return_value={"path": "scene.mp4", "shots": []}
    )
    pipeline._assemble_final_drama = AsyncMock(return_value=str(tmp_path / "out.mp4"))
    monkeypatch.setattr(
        pipeline_mod, "_make_voice_generator", lambda *a, **kw: _Recorder()
    )

    result = await pipeline.continue_from_script(
        DramaScript(
            title="T",
            logline="L",
            scenes=[
                {
                    "action": "Margit closes the shop.",
                    "dialogue": [{"character": "Margit", "line": "Not tonight."}],
                }
            ],
            characters=[{"name": "Margit", "description": "woman in her seventies"}],
        ),
        working_dir=str(tmp_path / "job"),
        dialogue_enabled=True,
        library_characters=[
            {
                "name": "Margit",
                "static_features": "woman in her seventies",
                "portrait_url": "https://cdn/margit.png",
                "voice_id": "voice-from-episode-one",
            }
        ],
    )

    assert locked == {"Margit": "voice-from-episode-one"}
    # And the decision is handed back, so a character saved to the library
    # from THIS drama carries the voice it cast them with.
    assert result["character_voices"]["Margit"] == "voice-from-episode-one"


@pytest.mark.asyncio
async def test_a_drama_with_no_library_still_reports_what_it_cast(
    tmp_path, monkeypatch
):
    """Episode one is where the voice is decided; without this the decision is
    thrown away and episode two has nothing to lock onto."""
    from unittest.mock import AsyncMock

    from pipelines import idea2video as pipeline_mod

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")

    class _Caster:
        def cast_characters(self, characters):
            return {c.name.casefold(): f"voice-{c.name.lower()}" for c in characters}

        async def generate_scene_dialogue(self, lines, **kwargs):
            return []

    pipeline = pipeline_mod.Idea2VideoPipeline("test-key")
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline._lock_location_plate = AsyncMock(return_value=None)
    pipeline.script2video.run = AsyncMock(
        return_value={"path": "scene.mp4", "shots": []}
    )
    pipeline._assemble_final_drama = AsyncMock(return_value=str(tmp_path / "out.mp4"))
    monkeypatch.setattr(
        pipeline_mod, "_make_voice_generator", lambda *a, **kw: _Caster()
    )

    result = await pipeline.continue_from_script(
        DramaScript(
            title="T",
            logline="L",
            scenes=[
                {
                    "action": "Margit closes the shop.",
                    "dialogue": [{"character": "Margit", "line": "Not tonight."}],
                }
            ],
            characters=[{"name": "Margit", "description": "woman in her seventies"}],
        ),
        working_dir=str(tmp_path / "job"),
        dialogue_enabled=True,
    )

    assert result["character_voices"] == {"Margit": "voice-margit"}
