"""Half a cast's identity anchor came back as artwork.

Job a66acd59 was ordered photoreal noir. Its two character sheets arrived in
different media from the same brief: the woman photographic, the man a
cel-shaded 3D render in a fedora with a cigarette. Every frame that man
appears in was then drawn from a drawing, inside a photographic film.

The cause is in the words. "Character reference sheet" is a term of art in
ILLUSTRATION -- concept art, model sheets, turnarounds -- and a model reading
it renders the conventions that come with it. The style clause says "Film Noir
style", which does nothing to contradict a drawing, and the render note that
would (`look.render_note`) is deliberately withheld on photoreal looks because
a photoreal style is supposed to need no help.

It needs help here, because the prompt itself is pulling the other way.
"""

import pytest

from pipelines.idea2video import SHEET_IS_PHOTOGRAPHED


@pytest.mark.asyncio
async def test_a_photoreal_sheet_says_it_is_a_photograph(monkeypatch):
    from interfaces.character import CharacterInScene
    from pipelines import idea2video as idea_mod

    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    prompts = []

    async def capture(prompt, aspect_ratio="1:1", is_cancelled=None):
        prompts.append(prompt)
        return "https://cdn/sheet.png"

    pipeline = idea_mod.Idea2VideoPipeline("test-key", demo=False)
    pipeline.image_gen.generate_image = capture

    await pipeline._lock_character_portraits(
        [
            CharacterInScene(
                idx=0,
                name="Julian Voss",
                static_features="man, fifties, lined face",
                dynamic_features="watchful",
                wardrobe="grey overcoat and a fedora",
            )
        ],
        style="Film Noir",
    )

    assert prompts, "the sheet has to be generated to be tested"
    assert SHEET_IS_PHOTOGRAPHED in prompts[0]
    assert "reference sheet" in prompts[0], (
        "the grid is still what is being asked for; only the medium is pinned"
    )


@pytest.mark.asyncio
async def test_a_stylised_sheet_is_not_told_to_be_a_photograph(monkeypatch):
    """On a drawn film the render note already points the other way."""
    from interfaces.character import CharacterInScene
    from pipelines import idea2video as idea_mod

    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    prompts = []

    async def capture(prompt, aspect_ratio="1:1", is_cancelled=None):
        prompts.append(prompt)
        return "https://cdn/sheet.png"

    pipeline = idea_mod.Idea2VideoPipeline("test-key", demo=False)
    pipeline.image_gen.generate_image = capture

    await pipeline._lock_character_portraits(
        [
            CharacterInScene(
                idx=0,
                name="Julian Voss",
                static_features="man, fifties",
                dynamic_features="watchful",
                wardrobe="grey overcoat",
            )
        ],
        style="anime",
    )

    assert prompts
    assert SHEET_IS_PHOTOGRAPHED not in prompts[0]
