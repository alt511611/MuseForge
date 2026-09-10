"""A frame is drawn from every face in it, not just one.

`generate_image_with_reference` took a single URL, and that was not a
simplification -- it was the shape of a delivered defect. A two-hander gets one
anchor, so the OTHER person in the frame was drawn from the prompt's prose
description, and prose produces somebody who matches the description and is not
the same person twice.

Delivered job 4c7bbe85-e5c: two characters, six frames, twelve face
appearances, six locks. Its male lead is three different men -- a man in his
forties in one scene, a man in his twenties in the next, a man in his sixties
in the third, all of them matching "man in his forties, sharp jaw,
grey-streaked hair" as well as prose can.

So the frame is now offered an ORDERED set: the anchor, then the other faces
the shot shows, then the set plate. The backend takes what it can read.
"""

import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --------------------------------------------------------------------------
# The backend contract
# --------------------------------------------------------------------------

def test_a_single_reference_endpoint_takes_the_anchor_and_says_what_it_dropped(caplog):
    """PuLID reads one image. That is a property of the model, not a choice.

    The failure this guards is silence: three references arriving at a
    single-identity endpoint and two being ignored with no error looks exactly
    like a model that ignored them.
    """
    from tools.muapi_image_generator import reference_capacity

    assert reference_capacity("flux-pulid") == 1
    assert reference_capacity("flux-kontext-pro-i2i") > 1


@pytest.mark.asyncio
async def test_pulid_gets_the_anchor_from_a_set():
    from tools.muapi_image_generator import MuAPIImageGenerator

    generator = MuAPIImageGenerator(api_key="k", demo=False)
    generator.KONTEXT_ENDPOINT = "flux-pulid"
    generator.client.generate = AsyncMock(return_value="https://cdn/frame.png")

    await generator.generate_image_with_reference(
        prompt="the card table",
        references=[
            "https://cdn/vivian.png",
            "https://cdn/julian.png",
            "https://cdn/plate.png",
        ],
        aspect_ratio="9:16",
    )

    payload = generator.client.generate.await_args.args[1]
    assert payload["image_url"] == "https://cdn/vivian.png", (
        "The anchor leads the set and is the one a single-identity model gets."
    )
    assert "images_list" not in payload


@pytest.mark.asyncio
async def test_a_multi_reference_endpoint_receives_the_whole_set():
    from tools.muapi_image_generator import MuAPIImageGenerator

    generator = MuAPIImageGenerator(api_key="k", demo=False)
    generator.KONTEXT_ENDPOINT = "flux-kontext-pro-i2i"
    generator.client.generate = AsyncMock(return_value="https://cdn/frame.png")

    await generator.generate_image_with_reference(
        prompt="the card table",
        references=[
            "https://cdn/vivian.png",
            "https://cdn/julian.png",
            "https://cdn/plate.png",
        ],
        aspect_ratio="9:16",
    )

    payload = generator.client.generate.await_args.args[1]
    assert payload["images_list"] == [
        "https://cdn/vivian.png",
        "https://cdn/julian.png",
        "https://cdn/plate.png",
    ]


@pytest.mark.asyncio
async def test_capacity_is_overridable_without_a_deploy(monkeypatch):
    """The Kontext ceiling is a playground measurement, not a constant."""
    from tools.muapi_image_generator import MuAPIImageGenerator, reference_capacity

    monkeypatch.setenv("MUAPI_REFERENCE_CAPACITY_FLUX_KONTEXT_PRO_I2I", "2")
    assert reference_capacity("flux-kontext-pro-i2i") == 2

    generator = MuAPIImageGenerator(api_key="k", demo=False)
    generator.KONTEXT_ENDPOINT = "flux-kontext-pro-i2i"
    generator.client.generate = AsyncMock(return_value="https://cdn/frame.png")
    await generator.generate_image_with_reference(
        prompt="x", references=["a", "b", "c"], aspect_ratio="9:16"
    )
    assert generator.client.generate.await_args.args[1]["images_list"] == ["a", "b"]


@pytest.mark.asyncio
async def test_duplicate_references_do_not_spend_a_slot():
    """The anchor and the plate are the same URL on a characterless shot."""
    from tools.muapi_image_generator import MuAPIImageGenerator

    generator = MuAPIImageGenerator(api_key="k", demo=False)
    generator.KONTEXT_ENDPOINT = "flux-kontext-pro-i2i"
    generator.client.generate = AsyncMock(return_value="https://cdn/frame.png")

    await generator.generate_image_with_reference(
        prompt="empty room",
        references=["https://cdn/plate.png", "https://cdn/plate.png"],
        aspect_ratio="9:16",
    )
    assert generator.client.generate.await_args.args[1]["images_list"] == [
        "https://cdn/plate.png"
    ]


@pytest.mark.asyncio
async def test_an_empty_set_takes_the_unreferenced_path():
    """Better than sending `null` to a model that requires a reference."""
    from tools.muapi_image_generator import MuAPIImageGenerator

    generator = MuAPIImageGenerator(api_key="k", demo=False)
    generator.client.generate = AsyncMock(return_value="https://cdn/frame.png")

    await generator.generate_image_with_reference(
        prompt="a wide street", references=[], aspect_ratio="9:16"
    )
    payload = generator.client.generate.await_args.args[1]
    assert "image_url" not in payload and "images_list" not in payload


@pytest.mark.asyncio
async def test_a_bare_string_is_still_a_valid_reference():
    """Every caller that predates the set keeps working byte-for-byte."""
    from tools.muapi_image_generator import MuAPIImageGenerator

    generator = MuAPIImageGenerator(api_key="k", demo=False)
    generator.KONTEXT_ENDPOINT = "flux-pulid"
    generator.client.generate = AsyncMock(return_value="https://cdn/frame.png")

    await generator.generate_image_with_reference(
        prompt="x", references="https://cdn/only.png", aspect_ratio="9:16"
    )
    assert generator.client.generate.await_args.args[1]["image_url"] == (
        "https://cdn/only.png"
    )


# --------------------------------------------------------------------------
# Who ends up in the set
# --------------------------------------------------------------------------

def _shot(visual_desc, motion_desc=""):
    from interfaces.shot import StoryboardShot

    return StoryboardShot(idx=0, visual_desc=visual_desc, motion_desc=motion_desc)


def _cast():
    from interfaces.character import CharacterInScene

    vivian = CharacterInScene(
        idx=0, name="Vivian Marsh", static_features="woman, mid-thirties"
    )
    julian = CharacterInScene(
        idx=1, name="Julian Voss", static_features="man, forties"
    )
    return vivian, julian


def test_the_frame_prompt_and_the_reference_set_agree_on_who_is_present():
    """The one invariant this refactor exists to make unbreakable.

    A frame handed one person's portrait while being told about somebody
    else's face is the most expensive way to draw a stranger. Both answers now
    come from the same function.
    """
    from pipelines.script2video import characters_in_frame

    vivian, julian = _cast()
    shot = _shot("Vivian deals as Julian watches the chips")

    present = characters_in_frame(shot, [vivian, julian], matched_char=vivian)
    assert present[0] is vivian, "The anchor leads."
    assert julian in present, "The other face in the frame is in the list."


def test_a_shot_that_names_nobody_keeps_the_whole_cast():
    """Narrowing on no evidence is how a character comes back as a stranger."""
    from pipelines.script2video import characters_in_frame

    vivian, julian = _cast()
    shot = _shot("a hand slides a chip across the felt")

    present = characters_in_frame(shot, [vivian, julian], matched_char=None)
    assert [c.name for c in present] == ["Vivian Marsh", "Julian Voss"]


def test_an_invisible_character_is_never_in_the_frame():
    """A radio voice has no face to lock, and asking for one invents it."""
    from pipelines.script2video import characters_in_frame
    from interfaces.character import CharacterInScene

    vivian, _ = _cast()
    radio = CharacterInScene(
        idx=2, name="Control", static_features="a voice", is_visible=False
    )
    shot = _shot("Control's voice warns as Vivian lifts the card")

    present = characters_in_frame(shot, [vivian, radio], matched_char=vivian)
    assert radio not in present
    assert present == [vivian]


# --------------------------------------------------------------------------
# The character sheet
# --------------------------------------------------------------------------

def test_the_character_sheet_is_off_unless_the_backend_can_read_one(monkeypatch):
    """PuLID locks a FACE; a four-panel grid is not one.

    Pairing the sheet with a backend that combines multiple views is the
    operator's call, because nothing can ask a MuAPI slug what it does with a
    grid and guessing wrong degrades every face in the film.
    """
    from pipelines.idea2video import is_character_sheet_enabled

    monkeypatch.delenv("MUSEFORGE_CHARACTER_SHEET", raising=False)
    assert is_character_sheet_enabled() is False
    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    assert is_character_sheet_enabled() is True


@pytest.mark.asyncio
async def test_the_sheet_asks_for_four_views_of_one_person(monkeypatch):
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    vivian, _ = _cast()
    pipeline = Idea2VideoPipeline(api_key="k", demo=False)

    prompts = []

    async def fake_generate(prompt, aspect_ratio="1:1", is_cancelled=None):
        prompts.append(prompt)
        return "https://cdn/sheet.png"

    pipeline.image_gen.generate_image = fake_generate
    await pipeline._lock_character_portraits([vivian], style="Noir")

    assert len(prompts) == 1
    prompt = prompts[0]
    assert "reference sheet" in prompt
    assert "2x2 grid of the SAME person" in prompt
    assert "profile" in prompt
    assert "Front-facing, neutral expression" not in prompt, (
        "The sheet REPLACES the single-view framing; it does not extend it."
    )


@pytest.mark.asyncio
async def test_without_the_flag_the_portrait_is_unchanged(monkeypatch):
    """The shipped default must be byte-for-byte what it was."""
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.delenv("MUSEFORGE_CHARACTER_SHEET", raising=False)
    vivian, _ = _cast()
    pipeline = Idea2VideoPipeline(api_key="k", demo=False)

    prompts = []

    async def fake_generate(prompt, aspect_ratio="1:1", is_cancelled=None):
        prompts.append(prompt)
        return "https://cdn/portrait.png"

    pipeline.image_gen.generate_image = fake_generate
    await pipeline._lock_character_portraits([vivian], style="Noir")

    assert "Character portrait" in prompts[0]
    assert "Front-facing, neutral expression, studio lighting, high detail." in prompts[0]
    assert "grid" not in prompts[0]
