"""The Visual Style control had to actually change the picture.

It was two words glued to the front of an image prompt: shot DESIGN never
saw it, so a noir and a romance were the same frames with a different word
in front of them, and every style — Anime included — carried the same
photoreal suffix asking for film grain and visible skin pores.
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

#: The list the client actually offers (client/components/IdeaForm.js).
CLIENT_STYLES = [
    "Cinematic", "Noir", "Sci-Fi", "Fantasy",
    "Horror", "Romance", "Documentary", "Anime",
]


def _shot():
    return SimpleNamespace(
        visual_desc="Mara hauls the door open",
        shot_type="medium shot",
        lens="50mm",
        expression_desc="jaw set",
    )


# --- the look ------------------------------------------------------------


def test_every_style_the_client_offers_is_known_to_the_server():
    """A style in the dropdown with no entry here renders as Cinematic —
    silently, which is exactly how this control became decorative."""
    from interfaces.visual_style import STYLES

    for name in CLIENT_STYLES:
        assert name.casefold() in STYLES, name


def test_anime_is_not_asked_for_film_grain_and_skin_pores():
    """The contradiction that made the style unwinnable: 'Anime style' and
    'realistic skin texture with visible pores' in one prompt."""
    from pipelines.script2video import build_frame_prompt

    prompt = build_frame_prompt("Anime", _shot())

    assert "Anime style." in prompt
    assert "visible pores" not in prompt
    assert "35mm film" not in prompt
    assert "cel shading" in prompt


def test_photoreal_styles_render_exactly_as_they_always_have():
    """Live-action styles must not move a byte: this is what every delivered
    drama has looked like."""
    from interfaces.visual_style import PHOTOREAL_RENDER
    from pipelines.script2video import IMAGE_QUALITY_SUFFIX, build_frame_prompt

    assert IMAGE_QUALITY_SUFFIX == PHOTOREAL_RENDER
    for name in ("Cinematic", "Noir", "Horror", "Documentary"):
        assert PHOTOREAL_RENDER in build_frame_prompt(name, _shot()), name


def test_an_unknown_style_still_renders():
    """A legacy job or a style added to the client first must not error."""
    from interfaces.visual_style import PHOTOREAL_RENDER
    from pipelines.script2video import build_frame_prompt

    assert PHOTOREAL_RENDER in build_frame_prompt("Steampunk", _shot())
    assert PHOTOREAL_RENDER in build_frame_prompt("", _shot())


def test_every_style_forbids_captions_and_watermarks():
    """The one instruction no look may lose."""
    from interfaces.visual_style import STYLES

    for name, look in STYLES.items():
        assert "No text, captions" in look.render_note, name


# --- the shot ------------------------------------------------------------


def test_the_storyboard_is_told_how_to_compose_for_the_style():
    from agents.storyboard_artist import StoryboardArtist

    noir = StoryboardArtist._format_visual_style("Noir")
    romance = StoryboardArtist._format_visual_style("Romance")

    assert "Noir" in noir and "hard-edged shadow" in noir
    assert "Romance" in romance and "shallow focus" in romance
    assert noir != romance


def test_cinematic_adds_nothing_to_the_shot_brief():
    """It is the neutral house style the prompt already describes; a note
    would restate the default and spend tokens doing it."""
    from agents.storyboard_artist import StoryboardArtist

    assert StoryboardArtist._format_visual_style("Cinematic") == ""
    assert StoryboardArtist._format_visual_style("") == ""


def test_the_style_note_stays_in_its_lane():
    """Framing and light are its business; the locked place and cast are not."""
    from agents.storyboard_artist import StoryboardArtist

    note = StoryboardArtist._format_visual_style("Horror")

    assert "never the place or who is in it" in note


@pytest.mark.asyncio
async def test_the_identity_anchor_is_made_in_the_dramas_own_look():
    """Every frame is matched against the locked portrait, so a photographic
    face bound into cel-shaded scenes fights the style in every shot."""
    from unittest.mock import AsyncMock

    from interfaces.character import CharacterInScene
    from pipelines import idea2video as pipeline_mod

    prompts = []

    async def capture(prompt, aspect_ratio="1:1"):
        prompts.append(prompt)
        return "https://cdn/portrait.png"

    pipeline = pipeline_mod.Idea2VideoPipeline("test-key")
    pipeline.image_gen.generate_image = AsyncMock(side_effect=capture)
    cast = [CharacterInScene(idx=0, name="Mara", static_features="thirties")]

    await pipeline._lock_character_portraits(cast, style="Anime")
    assert "cel shading" in prompts[0]

    prompts.clear()
    await pipeline._lock_character_portraits(
        [CharacterInScene(idx=0, name="Otto", static_features="sixties")],
        style="Cinematic",
    )
    # A photoreal style keeps the portrait prompt it has always had.
    assert "35mm film" not in prompts[0]


@pytest.mark.asyncio
async def test_the_style_reaches_the_shot_designer(tmp_path):
    """End to end: the string the frame prompt renders with is the string the
    shot was designed for."""
    from unittest.mock import AsyncMock

    from pipelines.script2video import Script2VideoPipeline

    pipeline = Script2VideoPipeline("test-key", demo=True)
    pipeline.storyboard_artist.design_storyboard = AsyncMock(return_value=[])

    await pipeline.run(
        script="She opens the container.",
        characters=[],
        style="Noir",
        working_dir=str(tmp_path / "scene"),
    )

    assert pipeline.storyboard_artist.design_storyboard.await_args.kwargs["style"] == "Noir"
