"""The identity lock and the costume lock are the same picture, and only one
of them was being photographed.

Every frame of a drama is drawn from one locked portrait per character, and
that portrait is generated "Wearing {wardrobe}" -- so the intent was always
that it carry the outfit too. Its framing direction said otherwise:
"Front-facing, neutral expression, studio lighting, high detail" is a
head-and-shoulders portrait, and a head-and-shoulders portrait holds a collar.

Job 8b8fce47-445 is what a collar is worth. One face, consistent across all
six shots -- the reference doing exactly its job -- wearing a slicker that

    buttoned, then zipped, then hung open
    went matte, then glossy PVC
    grew flap pockets, then patch pockets, then none
    put the band on her chest, then her sleeves, then nowhere

Every one of those lives below the collar. The frame prompt restates the
wardrobe verbatim on every frame, so text had already said what it could say;
what was missing was a picture of the thing.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from interfaces.character import CharacterInScene  # noqa: E402
from pipelines.idea2video import (  # noqa: E402
    COSTUME_IS_IN_THE_PORTRAIT,
    Idea2VideoPipeline,
)

SLICKER = (
    "hood up, matte yellow PVC slicker zipped to the throat, two hip flap "
    "pockets, one reflective blue band across the chest only, nothing on her "
    "back"
)


def _dressed():
    return CharacterInScene(
        idx=0,
        name="Yara",
        static_features="a woman in her early thirties, oval face",
        dynamic_features="watchful",
        wardrobe=SLICKER,
    )


def _undressed():
    return CharacterInScene(
        idx=0,
        name="Yara",
        static_features="a woman in her early thirties, oval face",
        dynamic_features="watchful",
    )


async def _portrait_prompt(character, monkeypatch=None):
    pipeline = Idea2VideoPipeline(api_key="k", demo=False)
    prompts = []

    async def fake_generate(prompt, aspect_ratio="1:1", is_cancelled=None):
        prompts.append(prompt)
        return "https://cdn/portrait.png"

    pipeline.image_gen.generate_image = fake_generate
    await pipeline._lock_character_portraits([character], style="Noir")
    return prompts[0]


@pytest.mark.asyncio
async def test_a_dressed_character_is_photographed_in_the_clothes(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_CHARACTER_SHEET", raising=False)
    prompt = await _portrait_prompt(_dressed())

    assert f"Wearing {SLICKER}" in prompt, "the outfit still has to be asked for"
    assert "Framed from the hips up" in prompt
    assert "fastening, its pockets, its markings" in prompt
    assert "costume reference as well as the face reference" in prompt


@pytest.mark.asyncio
async def test_the_face_is_still_the_thing_the_reference_binds(monkeypatch):
    """flux-pulid reads a face out of this picture. Widening the frame is a
    bounded trade, not a handover: the portrait is still front-facing, still
    evenly lit, and says so about the face outright."""
    monkeypatch.delenv("MUSEFORGE_CHARACTER_SHEET", raising=False)
    prompt = await _portrait_prompt(_dressed())

    assert "Front-facing, neutral expression, studio lighting, high detail." in prompt
    assert "face stays sharp and clearly readable" in prompt


@pytest.mark.asyncio
async def test_an_undressed_character_gets_the_portrait_it_always_got(monkeypatch):
    """Nothing to widen the frame for, and no change to the shipped prompt."""
    monkeypatch.delenv("MUSEFORGE_CHARACTER_SHEET", raising=False)
    prompt = await _portrait_prompt(_undressed())

    assert "Wearing" not in prompt
    assert COSTUME_IS_IN_THE_PORTRAIT.strip() not in prompt
    assert prompt.rstrip().endswith(
        "Front-facing, neutral expression, studio lighting, high detail."
    )


@pytest.mark.asyncio
async def test_the_reference_sheet_is_left_alone(monkeypatch):
    """Four panels of a hips-up figure is four small faces, and the sheet is
    a flag-gated path whose whole value is the angles. Its own direction
    already asks for identical clothing in all four panels; making it carry
    the garment as well is a separate change."""
    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    prompt = await _portrait_prompt(_dressed())

    assert "2x2 grid of the SAME person" in prompt
    assert f"Wearing {SLICKER}" in prompt
    assert "Framed from the hips up" not in prompt


# The continuity-edit path -- "put her in a red coat" -- regenerates the locked
# portrait from itself, and is framed the same way for the same reason. Asserted
# where that path is already exercised end to end:
# test_global_and_timeline_edits.test_global_edit_moves_the_lock_then_re_renders_every_affected_scene
