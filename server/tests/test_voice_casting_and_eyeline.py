"""Gender-matched voice casting + 180°-rule screen direction.

Two amateurism risks in a two-hander:
- the per-line hash could voice a mother with "George - Warm";
- independently generated scenes could flip which side of frame each
  character occupies, so cuts read as two people facing away from each other.
"""

import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    build_frame_prompt,
    build_motion_prompt,
    build_screen_direction_clause,
)
from tools.muapi_voice_generator import MuAPIVoiceGenerator  # noqa: E402


def _chars(*pairs):
    return [
        CharacterInScene(idx=i, name=name, static_features=desc)
        for i, (name, desc) in enumerate(pairs)
    ]


# --- voice casting ------------------------------------------------------


def test_female_description_gets_a_female_voice():
    gen = MuAPIVoiceGenerator(api_key="k", demo=True)
    gen.cast_characters(_chars(("Ayse", "52-year-old woman, grey bun")))
    assert gen.voice_id_for_character("Ayse") in gen.FEMALE_VOICE_IDS


def test_turkish_descriptions_are_understood():
    gen = MuAPIVoiceGenerator(api_key="k", demo=True)
    gen.cast_characters(
        _chars(("Ayse", "52 yaşında kadın, gri topuz"), ("Kemal", "60 yaşında adam"))
    )
    assert gen.voice_id_for_character("Ayse") in gen.FEMALE_VOICE_IDS
    assert gen.voice_id_for_character("Kemal") in gen.MALE_VOICE_IDS


def test_mother_and_daughter_get_distinct_female_voices():
    """The reported scenario: both female, and they must not share a voice."""
    gen = MuAPIVoiceGenerator(api_key="k", demo=True)
    gen.cast_characters(
        _chars(
            ("Ayse", "the mother, 52-year-old woman"),
            ("Elif", "her daughter, 24-year-old woman"),
        )
    )
    ayse = gen.voice_id_for_character("Ayse")
    elif_ = gen.voice_id_for_character("Elif")
    assert ayse in gen.FEMALE_VOICE_IDS
    assert elif_ in gen.FEMALE_VOICE_IDS
    assert ayse != elif_


def test_casting_is_stable_across_scenes():
    """Same character, same voice on every later lookup -- the whole point."""
    gen = MuAPIVoiceGenerator(api_key="k", demo=True)
    gen.cast_characters(_chars(("Ayse", "a woman")))
    first = gen.voice_id_for_character("Ayse")
    for _ in range(5):
        assert gen.voice_id_for_character("ayse") == first  # case-insensitive


def test_unknown_gender_keeps_hash_fallback():
    gen = MuAPIVoiceGenerator(api_key="k", demo=True)
    gen.cast_characters(_chars(("Robot-7", "a chrome service automaton")))
    # Not force-assigned at cast time; first line assigns from the full enum.
    voice = gen.voice_id_for_character("Robot-7")
    assert voice in gen.SYSTEM_VOICE_IDS


def test_cast_characters_respects_existing_assignments():
    gen = MuAPIVoiceGenerator(api_key="k", demo=True)
    pre = gen.voice_id_for_character("Ayse")  # hash-assigned before casting
    gen.cast_characters(_chars(("Ayse", "a woman")))
    assert gen.voice_id_for_character("Ayse") == pre


def test_gender_pools_partition_the_enum():
    gen = MuAPIVoiceGenerator
    assert set(gen.FEMALE_VOICE_IDS) | set(gen.MALE_VOICE_IDS) == set(gen.SYSTEM_VOICE_IDS)
    assert not set(gen.FEMALE_VOICE_IDS) & set(gen.MALE_VOICE_IDS)


def test_pipeline_casts_before_generating(monkeypatch):
    """The call site guard: idea2video must cast the ensemble up front."""
    import inspect

    import pipelines.idea2video as mod

    source = inspect.getsource(mod.Idea2VideoPipeline.continue_from_script)
    assert "cast_characters(characters)" in source


# --- 180° rule ----------------------------------------------------------


def test_axis_clause_for_a_two_hander():
    clause = build_screen_direction_clause(
        _chars(("Ayse", "52"), ("Elif", "24"))
    )
    assert "Ayse is on frame-left facing screen-right" in clause
    assert "Elif is on frame-right facing screen-left" in clause
    assert "180-degree rule" in clause
    assert "Never mirror" in clause


def test_axis_clause_only_for_exactly_two_visible():
    assert build_screen_direction_clause(_chars(("Ayse", "52"))) == ""
    assert build_screen_direction_clause(
        _chars(("A", "1"), ("B", "2"), ("C", "3"))
    ) == ""
    two_plus_hidden = _chars(("Ayse", "52"), ("Elif", "24"), ("Ghost", "x"))
    two_plus_hidden[2].is_visible = False
    assert "Ayse is on frame-left" in build_screen_direction_clause(two_plus_hidden)
    assert build_screen_direction_clause(None) == ""


def test_axis_is_order_deterministic():
    """Scene renders are parallel and independent; the axis must come from
    character order alone so every scene derives the identical line."""
    a = build_screen_direction_clause(_chars(("Ayse", "52"), ("Elif", "24")))
    b = build_screen_direction_clause(_chars(("Ayse", "anything"), ("Elif", "else")))
    assert a == b


def test_frame_prompt_carries_the_axis():
    from types import SimpleNamespace

    shot = SimpleNamespace(
        visual_desc="they face each other", shot_type="medium", lens="50mm"
    )
    prompt = build_frame_prompt(
        "Cinematic", shot, characters=_chars(("Ayse", "52"), ("Elif", "24"))
    )
    assert "Ayse is on frame-left facing screen-right" in prompt


def test_storyboard_prompt_teaches_the_rule():
    from agents.storyboard_artist import StoryboardArtist

    prompt = StoryboardArtist.SYSTEM_PROMPT
    assert "RESPECT THE 180° LINE" in prompt
    assert "frame-left" in prompt and "screen-RIGHT" in prompt


def test_motion_prompt_forbids_mirroring():
    from interfaces.shot import StoryboardShot

    shot = StoryboardShot(idx=0, visual_desc="x", motion_desc="hands meet")
    prompt = build_motion_prompt(shot, None)
    assert "never mirror the composition" in prompt
    assert "screen direction" in prompt.lower()
