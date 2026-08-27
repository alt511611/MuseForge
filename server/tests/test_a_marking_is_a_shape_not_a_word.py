"""The render cannot spell, so nothing on the costume should ask it to.

Settling the garment (the previous commit) stopped the drift and introduced
this: told to name "any marking or lettering on it and where", the
screenwriter wrote lettering, and job 62df6dbb-d59 came back with

    HAROB     across the back of the jacket -- in a two-second push-in whose
              entire subject is that word
    FICST LOU on the name patch at her left breast, legible in every single
              shot of the drama

Writing is the one thing in a frame a viewer stops to read, so a misspelt
word costs more than the plain patch it replaced. A marking still has to be
named -- that is what stopped the drift -- but as a shape and a placement.

Two places, because they fail differently. The screenwriter is where new
scripts are written; the frame prompt is the backstop for a saved character
whose wardrobe already names lettering, and for a brief that asks for it
outright.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    IDENTITY_CLAUSE_OVERHEAD,
    build_character_identity_clause,
)


def _clause(wardrobe="a yellow hooded slicker, a patch on the left breast"):
    char = CharacterInScene(
        idx=0, name="Reyes", static_features="a woman in her fifties",
        wardrobe=wardrobe,
    )
    return build_character_identity_clause([char], matched_char=char)


# ── the frame, which is what cannot spell ───────────────────────────────────


def test_the_frame_is_told_a_marking_is_a_shape():
    assert "Markings are shapes, not words" in _clause()


def test_it_rides_the_sentence_that_already_names_a_badge():
    """Folded in rather than given a sentence of its own: same subject, and
    the reserve every frame holds back has no room for a fifth."""
    clause = _clause()
    listed = clause.index("badge")
    assert listed < clause.index("Markings are shapes")


def test_a_wardrobe_that_names_lettering_still_gets_the_rule():
    """The backstop's whole purpose: a character saved before this existed,
    or a brief that asked for the words outright."""
    clause = _clause("a yellow slicker with HARBOR OPS stencilled on the back")
    assert "HARBOR OPS" in clause, "the wardrobe is still restated verbatim"
    assert "Markings are shapes, not words" in clause


def test_it_did_not_cost_a_word_of_any_rule_already_there():
    """Every one of those names something a delivered drama actually did."""
    clause = _clause()
    for kept in (
        "IDENTICAL in every scene",     # face drift
        "hard hat",                     # a worker in a beanie, then a hard hat
        "backpack",                     # a pack in one shot of six
        # The costume lock is now stated positively -- these endpoints are
        # guidance-distilled and have no branch for a negation to act through
        # -- so the rule is checked by what it asserts, not by "never
        # restyled or swapped".
        "same garment, cut and colour",  # three outfits in a three-scene drama
    ):
        assert kept in clause, kept


def test_the_reserve_still_fits_with_room_after_it():
    """Sitting exactly on the cap would make the next legitimate word break
    an unrelated test."""
    assert IDENTITY_CLAUSE_OVERHEAD <= 790


# ── the writer, which is where new scripts are settled ──────────────────────


def test_the_writer_is_asked_for_a_shape_and_shown_the_pair():
    prompt = ScreenwriterAgent.SYSTEM_PROMPT
    assert "Describe a marking as a SHAPE, never as words to be read" in prompt
    assert "a blue reflective band across" in prompt
    assert "HARBOR OPS stencilled across" in prompt


def test_the_writer_is_told_why():
    """"The render cannot spell" is the reason, and it is the reason a model
    can act on -- unlike "avoid lettering", which reads as a style note."""
    assert "The render cannot spell" in ScreenwriterAgent.SYSTEM_PROMPT


@pytest.mark.parametrize("evidence", ["HAROB", "FICST LOU"])
def test_the_delivered_failure_is_named_not_paraphrased(evidence):
    assert evidence in ScreenwriterAgent.SYSTEM_PROMPT


def test_the_schema_asks_for_shapes_where_the_field_is_filled_in():
    assert "markings as SHAPES not words" in ScreenwriterAgent.SYSTEM_PROMPT


def test_the_garment_is_still_settled():
    """The rule this narrows must survive it -- naming the marking is what
    stopped the drift; naming what it SAYS is what broke."""
    prompt = ScreenwriterAgent.SYSTEM_PROMPT
    assert "badge or marking on it and where" in prompt
    assert "HEAD DOWN" in prompt
