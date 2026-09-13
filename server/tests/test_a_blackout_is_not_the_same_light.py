"""Naming a lamp in order to KILL it is not naming it in order to shoot by it.

The setting line is the screenwriter's, and a screenwriter describing a place
at night describes how it is lit. The delivered locked setting reads
"rain-soaked cargo harbour, stacked shipping containers under sodium
floodlights", so on the one scene allowed to break that lock the frame prompt
adds a veto: "Any light named in that setting line describes this place BEFORE
the change; do not light the frame with it."

That veto stands down when the change is ABOUT the named light -- the basement
whose event is a hanging bulb swinging wildly cannot also be told to ignore
the bulb. The test for "about the named light" was a shared word, and a
blackout written the way the screenwriter prompt asks for it ("every light in
the city and on the docks goes out") shares that word too. So the veto stood
down for the one event that needs it most, the prompt asked for the
floodlights and for their failure in the same breath, and the delivered film
of the brief "...and the city's power dies the moment she opens it" burns
every lamp in the yard through the blackout and the shots after it.

The two cases are opposite: one wants the fixture to light the frame, the
other wants it gone.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.lighting import extinguishes_light  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    build_frame_prompt,
    names_the_same_light,
)

HARBOUR = (
    "rain-soaked cargo harbour, stacked shipping containers under sodium "
    "floodlights"
)
BASEMENT = "windowless basement card room, felt table under a bare hanging bulb"

#: The phrasing the screenwriter prompt asks for, word for word.
BLACKOUT = (
    "every light in the city and on the docks goes out, leaving only the "
    "container's glow"
)
#: The same event in the setting's own noun -- the shared word that used to
#: silence the veto.
FLOODLIGHTS_OUT = "every floodlight on the quay dies, leaving only one blue glow"
#: A change that makes the named fixture the light of the shot.
SWINGING_BULB = (
    "the basement door bursts open and the single hanging bulb swings wildly, "
    "throwing sweeping shadows"
)


def _prompt(setting, change):
    shot = StoryboardShot(
        idx=0,
        visual_desc="Mara staggers back from the open container door",
        motion_desc="handheld push in",
        shot_type="wide shot",
        lens="35mm",
        expression_desc="eyes wide, breath caught",
    )
    character = CharacterInScene(
        idx=0,
        name="Mara Voss",
        static_features="a woman in her late thirties, dark hair pulled back",
        wardrobe="a yellow hooded rain slicker",
    )
    return build_frame_prompt(
        "Sci-Fi",
        shot,
        setting_location=setting,
        setting_time_of_day="night",
        setting_era="near future",
        characters=[character],
        matched_char=character,
        world_change=change,
    )


# ── the word list ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        BLACKOUT,
        FLOODLIGHTS_OUT,
        "the city's power dies the moment she opens it",
        "every sodium lamp on the harbour snaps to black",
        "the quay blacks out",
        "limandaki ışıklar söner",
        "şehrin elektriği kesilir",
    ],
)
def test_a_light_going_out_is_recognised(text):
    assert extinguishes_light(text)


@pytest.mark.parametrize(
    "text",
    [
        SWINGING_BULB,
        "the container's blue glow floods the lane",
        "the water floods over the pier edge",
        "the felt table is overturned and the chips scatter",
        "",
    ],
)
def test_a_light_that_stays_on_is_not(text):
    assert not extinguishes_light(text)


# ── the veto ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("change", [BLACKOUT, FLOODLIGHTS_OUT])
def test_a_blackout_never_counts_as_the_setting_s_own_light(change):
    """Both halves name a floodlight; only one of them wants it lit."""
    assert not names_the_same_light(HARBOUR, change)


def test_the_light_the_event_is_about_is_still_exempt():
    """The case the exemption was written for has to keep working."""
    assert names_the_same_light(BASEMENT, SWINGING_BULB)


@pytest.mark.parametrize("change", [BLACKOUT, FLOODLIGHTS_OUT])
def test_the_yard_lamps_are_vetoed_for_the_blackout(change):
    prompt = _prompt(HARBOUR, change)

    assert HARBOUR in prompt, "the location lock still has to name the place"
    assert change in prompt
    assert "describes this place BEFORE the change" in prompt
    assert "do not light the frame with it" in prompt, (
        "this sentence is the only thing standing between the setting line's "
        "sodium floodlights and a lit harbour"
    )


def test_the_swinging_bulb_is_still_allowed_to_light_its_own_frame():
    prompt = _prompt(BASEMENT, SWINGING_BULB)

    assert "do not light the frame with it" not in prompt


# ── end to end, on the brief this was delivered against ─────────────────────


BRIEF = (
    "A dock worker on a rain-soaked cargo harbour finds a shipping container "
    "that hums with light, and the city's power dies the moment she opens it."
)


def test_the_brief_s_blackout_survives_from_idea_to_frame_prompt():
    """The screenwriter restores it, and the frame prompt renders it dark.

    Both halves have failed separately on this brief: once the writer declared
    the container's own glow as the world_change and the restorer stood down,
    and once the restorer worked and the veto did not.
    """
    from interfaces.character import CharacterProfile, DramaScript, ScriptScene

    script = DramaScript(
        title="Cargo 7",
        logline="A dock worker opens the wrong container.",
        mood="tense",
        estimated_duration_seconds=30,
        setting_location=HARBOUR,
        setting_time_of_day="night",
        setting_era="present day",
        characters=[
            CharacterProfile(
                name="Mara Voss",
                description="woman in her fifties, weathered face",
                wardrobe="hood up, matte yellow hooded rain slicker",
                role="protagonist",
            )
        ],
        scenes=[
            ScriptScene(
                action="Mara walks the container lane.",
                dramatic_function="setup",
                tension=3,
            ),
            ScriptScene(
                action="She finds the humming container.",
                dramatic_function="inciting_incident",
                tension=6,
            ),
            ScriptScene(
                action="The door swings open and light pours out.",
                dramatic_function="climax",
                tension=10,
                # What the writer actually declared on the delivered job: a
                # real change, and not the one the brief was commissioned for.
                world_change="the container's blue glow floods the lane",
            ),
        ],
    )
    ScreenwriterAgent._with_brief(script, BRIEF, num_scenes=3)

    climax = script.scenes[-1]
    assert "power dies" in climax.world_change, (
        "the brief's own event has to be restored onto the climax"
    )
    assert "blue glow" in climax.world_change, (
        "and added to the writer's change, never over it"
    )

    prompt = _prompt(HARBOUR, climax.world_change)
    assert "do not light the frame with it" in prompt
