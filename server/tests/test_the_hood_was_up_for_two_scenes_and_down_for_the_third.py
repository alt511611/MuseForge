"""Job 93be3d88: the hood was up for two scenes and down for the third.

"yellow hooded rain slicker" names a garment with a hood, not a hood worn. The
storyboard drew rain dripping off it (up); the character sheet drew it down;
the climax followed the sheet. The lead took her hood off on the cut into the
film's most important shot.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.character import CharacterProfile, DramaScript  # noqa: E402


def _settled(wardrobe):
    script = DramaScript(
        title="t", logline="l",
        characters=[CharacterProfile(name="Nadia", description="woman", wardrobe=wardrobe)],
    )
    ScreenwriterAgent._settle_the_hood(script)
    return script.characters[0].wardrobe


def test_a_hooded_garment_with_no_state_is_settled_up():
    assert _settled("yellow hooded rain slicker, zip-fastened").startswith("hood up, ")


@pytest.mark.parametrize(
    "wardrobe",
    [
        "hood up on a yellow rain slicker",
        "yellow slicker, hood down",
        "navy parka with the hood pushed back",
        "bare-headed, wool coat",
        "grey wool coat",
    ],
)
def test_a_wardrobe_that_already_says_is_left_alone(wardrobe):
    assert _settled(wardrobe) == wardrobe


def test_the_writer_is_told_a_garment_with_a_hood_is_not_a_hood_worn():
    assert '"hood up" or "hood down"' in ScreenwriterAgent.SYSTEM_PROMPT


def test_every_script_is_settled_on_its_way_out():
    script = DramaScript(
        title="t", logline="l",
        characters=[CharacterProfile(name="Nadia", description="woman", wardrobe="hooded slicker")],
        scenes=["She opens it."],
    )
    ScreenwriterAgent._with_brief(script, "A dock worker opens a container.", 1)
    assert "hood up" in script.characters[0].wardrobe
