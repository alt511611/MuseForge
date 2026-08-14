"""The rendered video must match the prompt the user actually wrote.

Regression cover for a real report: a detailed brief ("Marcus, late 30s-40s,
charcoal crew-neck sweater, seated at a walnut desk, bookshelves behind,
locked-off tripod, three hard cuts") came back as a young man in three
different outfits, standing in three empty rooms, in silence. Root cause was
the screenwriter falling back to the deterministic template -- which keeps
none of that -- and the pipeline rendering it anyway.

These tests pin the three guarantees that follow from it:
  1. a template script is never rendered outside demo mode;
  2. the user's verbatim brief reaches the shot-design step;
  3. an unstated wardrobe is pinned to the reference instead of being
     re-invented every scene.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    build_character_identity_clause,
)

BRIEF = (
    "Marcus: man, late 30s-mid 40s, short greying hair, plain charcoal "
    "crew-neck sweater, analog watch on left wrist. Seated at a dark walnut "
    "desk in a minimal home study, bookshelves behind him. All shots "
    "locked-off tripod, zero camera movement."
)


# --- 1. the brief reaches shot design ---------------------------------------


@pytest.mark.asyncio
async def test_user_brief_is_sent_to_the_storyboard_artist(monkeypatch):
    """The scene action line is the screenwriter's paraphrase; the concrete
    specifics (the desk, the sweater, the locked-off camera) only survive in
    the brief, so shot design has to see it."""
    import agents.storyboard_artist as sb_mod

    captured = {}

    async def fake_complete_via_muapi(system_prompt, user_prompt, **_kwargs):
        captured["prompt"] = user_prompt
        return (
            '[{"idx": 0, "visual_desc": "Marcus at his desk", '
            '"motion_desc": "still", "expression_desc": "measured", '
            '"audio_desc": "room tone", "shot_type": "medium", '
            '"camera_movement": "static locked-off tripod", '
            '"lens": "50mm", "duration_seconds": 5}]'
        )

    monkeypatch.setattr(sb_mod, "complete_via_muapi", fake_complete_via_muapi)
    monkeypatch.setenv("MUAPI_LLM_MODEL", "test-llm-slug")

    artist = StoryboardArtist()
    artist.muapi_key = "fake-muapi-key"
    await artist.design_storyboard(
        "Marcus speaks to camera.",
        [CharacterInScene(idx=0, name="Marcus", static_features="man, 40s")],
        user_brief=BRIEF,
    )

    prompt = captured["prompt"]
    assert "charcoal crew-neck sweater" in prompt
    assert "walnut desk" in prompt
    assert "locked-off tripod" in prompt


def test_brief_block_is_marked_binding_and_leads_the_prompt():
    block = StoryboardArtist._format_user_brief_block(BRIEF)
    assert "BINDING" in block
    # Ranked above the generic guidance that follows it, and placed first so
    # it is not the thing a truncating model drops.
    assert block.startswith("USER'S ORIGINAL BRIEF")


def test_brief_block_is_bounded():
    """A future cap increase on the idea field must not blow the shot-design
    token budget."""
    block = StoryboardArtist._format_user_brief_block("x" * 10_000)
    assert len(block) < StoryboardArtist.MAX_BRIEF_CHARS + 500
    assert block.rstrip().endswith("[…]")


def test_no_brief_emits_nothing():
    assert StoryboardArtist._format_user_brief_block("") == ""
    assert StoryboardArtist._format_user_brief_block("   ") == ""


@pytest.mark.asyncio
async def test_pipeline_forwards_the_brief_from_script_to_shot_design(monkeypatch, tmp_path):
    """idea2video -> script2video -> storyboard: the brief must survive the
    whole chain, not just exist on the script object."""
    import pipelines.idea2video as mod
    from interfaces.character import CharacterProfile, DramaScript, ScriptScene

    captured = {}

    async def fake_run(**kwargs):
        captured.update(kwargs)
        return {"path": None, "shots": []}

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=True)
    monkeypatch.setattr(pipeline, "_lock_character_portraits", _async_return({}))
    monkeypatch.setattr(pipeline.script2video, "run", fake_run)

    script = DramaScript(
        title="Money Scripts",
        logline="Marcus explains the shadow.",
        user_brief=BRIEF,
        characters=[CharacterProfile(name="Marcus", description="man, 40s")],
        scenes=[ScriptScene(action="Marcus speaks to camera.")],
    )
    await pipeline.continue_from_script(script, working_dir=str(tmp_path / "job"))

    assert captured["user_brief"] == BRIEF


# --- 2. wardrobe is pinned when the script does not state one ---------------


def test_missing_wardrobe_pins_the_costume_to_the_reference():
    """The reference image binds a face, not an outfit. With nothing said
    about clothing the image model dressed the character afresh each scene --
    observed as three different outfits in one three-scene drama."""
    clause = build_character_identity_clause(
        [CharacterInScene(idx=0, name="Marcus", static_features="man, 40s")]
    )
    assert "EXACT outfit from the reference image" in clause


def test_stated_wardrobe_is_named_and_needs_no_pin():
    clause = build_character_identity_clause(
        [
            CharacterInScene(
                idx=0,
                name="Marcus",
                static_features="man, 40s",
                wardrobe="plain charcoal crew-neck sweater",
            )
        ]
    )
    assert "plain charcoal crew-neck sweater" in clause
    assert "EXACT SAME" not in clause


# --- 3. a failed script refunds rather than renders -------------------------


def test_job_runner_refunds_on_script_generation_failure():
    import inspect

    import jobs

    source = inspect.getsource(jobs.run_generation_job)
    assert "except ScriptGenerationFailed" in source
    # Same treatment as a timeout: FAILED + refund, not a shipped video.
    failure_block = source.split("except ScriptGenerationFailed")[1].split(
        "except asyncio.TimeoutError"
    )[0]
    assert "_sb_refund_credits" in failure_block
    assert "JobStatus.FAILED" in failure_block


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner
