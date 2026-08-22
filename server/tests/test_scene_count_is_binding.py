"""The number of scenes the user chose is the number of scenes they get.

The count used to reach the model as one line of the USER message
("Scenes: 3") while the system prompt separately told it to "Build 3-5
scenes" -- and nothing anywhere checked the answer. A delivered three-scene
drama came back with five scenes and rendered a 60-second film. Everything
downstream disagreed at once: /api/estimate had quoted and charged for three
scenes, the runtime budget is per scene, and the plan ceiling is per scene, so
the job spent two scenes' worth of generation the user never bought.

Two layers, because a prompt instruction is not a guarantee: the constraint is
STATED (SCENE_COUNT_CLAUSE) and then ENFORCED (_hold_to_scene_count).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.character import DramaScript, ScriptScene  # noqa: E402


def _scene(function, tension, action="something happens", world_change=""):
    return ScriptScene(
        action=action,
        dramatic_function=function,
        tension=tension,
        world_change=world_change,
    )


def _script(scenes, duration=40):
    return DramaScript(
        title="The Address",
        logline="A bookseller walks to an address one last time.",
        scenes=scenes,
        estimated_duration_seconds=duration,
    )


# ── layer 1: the constraint is stated ───────────────────────────────────────


def test_the_prompt_states_the_count_and_overrides_the_range():
    agent = ScreenwriterAgent(demo=True)
    prompt = agent._system_prompt("en", num_scenes=3)

    assert agent.SYSTEM_PROMPT in prompt, "the direction must survive intact"
    assert "EXACTLY 3 scenes" in prompt
    # The base prompt's own "Build 3-5 scenes" is the thing it has to beat, so
    # the clause has to be the LAST word on the subject rather than a second
    # opinion buried above it.
    assert prompt.index("SCENE COUNT IS FIXED") > prompt.index("STRUCTURE.")


def test_a_job_with_no_stated_count_is_left_exactly_as_it_was():
    """Callers that do not care must not be told a count -- the clause costs
    tokens on every single job.

    Asserted on the clause rather than on the whole prompt: a scene's LENGTH
    is a fixed fact about the product and is stated unconditionally (see
    RUNTIME_CLAUSE), so byte-equality with the base prompt stopped being the
    thing this is protecting."""
    agent = ScreenwriterAgent(demo=True)
    for prompt in (
        agent._system_prompt("en"),
        agent._system_prompt("en", num_scenes=0),
    ):
        assert agent.SYSTEM_PROMPT in prompt
        assert "SCENE COUNT IS FIXED" not in prompt


def test_the_count_reaches_both_provider_paths():
    """The MuAPI LLM route is tried FIRST, so a constraint added only to the
    Anthropic fallback would do nothing on the primary path."""
    import inspect
    import re

    source = inspect.getsource(ScreenwriterAgent.write_script)
    calls = re.findall(r"self\._system_prompt\(([^)]*)\)", source, re.DOTALL)
    assert calls, "the MuAPI path must build a system prompt"
    assert all("num_scenes" in args for args in calls)
    assert "num_scenes" in inspect.signature(
        ScreenwriterAgent._write_with_claude
    ).parameters


# ── layer 2: the constraint is enforced ─────────────────────────────────────


def test_an_over_long_script_is_cut_back_to_what_was_paid_for():
    script = _script([
        _scene("setup", 2),
        _scene("inciting_incident", 4),
        _scene("rising_action", 3),
        _scene("climax", 9),
        _scene("resolution", 6),
    ])

    ScreenwriterAgent._hold_to_scene_count(script, 3)

    assert len(script.scenes) == 3
    functions = [s.dramatic_function for s in script.scenes]
    # The two lowest-tension non-climax scenes go; the shape survives.
    assert functions == ["inciting_incident", "climax", "resolution"]


def test_the_climax_is_never_what_gets_cut():
    """Cutting the climax does not shorten the film, it removes the reason it
    exists -- and it is the lowest-hanging scene by no measure except order."""
    script = _script([
        _scene("setup", 8),
        _scene("rising_action", 7),
        _scene("climax", 1),  # mis-scored by the writer, still load-bearing
    ])

    ScreenwriterAgent._hold_to_scene_count(script, 2)

    assert [s.dramatic_function for s in script.scenes] == ["setup", "climax"]


def test_a_scene_that_changes_the_world_survives_the_cut():
    """world_change is the one sanctioned break in the drama's locked lighting.
    Cut the scene carrying it and the event the whole film is built on becomes
    literally invisible, however well the rest is written."""
    script = _script([
        _scene("setup", 9),
        _scene("rising_action", 1, world_change="every lamp in the alley goes out"),
        _scene("climax", 8),
    ])

    ScreenwriterAgent._hold_to_scene_count(script, 2)

    assert [s.world_change for s in script.scenes if s.world_change]


def test_the_count_wins_when_every_remaining_scene_is_load_bearing():
    """Protection yields to the promise: the user chose two scenes and was
    charged for two, so two is what renders."""
    script = _script([
        _scene("climax", 9),
        _scene("resolution", 5),
        _scene("resolution", 2),
    ])

    ScreenwriterAgent._hold_to_scene_count(script, 2)

    assert len(script.scenes) == 2
    assert [s.tension for s in script.scenes] == [9, 5]


def test_the_quoted_runtime_follows_the_scenes_that_are_left():
    """Left alone, estimated_duration_seconds keeps quoting the length of the
    script that was just cut. Scaled rather than recomputed from a per-scene
    constant, so the writer's own pacing survives."""
    script = _script(
        [_scene("setup", 2), _scene("rising_action", 3), _scene("climax", 9)],
        duration=45,
    )

    ScreenwriterAgent._hold_to_scene_count(script, 2)

    assert script.estimated_duration_seconds == 30


def test_a_script_that_came_back_short_is_never_padded():
    """Inventing a scene is the screenwriter's job, not a repair's. A short
    film is less than the user paid for; a fabricated beat is worse."""
    script = _script([_scene("setup", 3), _scene("climax", 9)], duration=20)

    ScreenwriterAgent._hold_to_scene_count(script, 5)

    assert len(script.scenes) == 2
    assert script.estimated_duration_seconds == 20


def test_a_script_that_already_matches_is_untouched():
    scenes = [_scene("setup", 3), _scene("climax", 9)]
    script = _script(scenes, duration=20)

    ScreenwriterAgent._hold_to_scene_count(script, 2)

    assert script.scenes == scenes
    assert script.estimated_duration_seconds == 20


def test_legacy_string_scenes_do_not_crash_the_trim():
    """DramaScript still accepts plain-string scenes for stored and demo
    scripts, and a repair that raised on one would fail the whole job."""
    script = _script(["a bookshop at closing", "an alley", "a door"], duration=30)

    ScreenwriterAgent._hold_to_scene_count(script, 2)

    assert len(script.scenes) == 2


def test_the_guarantee_runs_on_every_script_however_it_was_written():
    """Both provider paths come through _with_brief, and the trim has to
    happen BEFORE the brief's event is restored -- run the other way round, a
    script whose extra scenes are cut could lose the restored world_change
    with them."""
    script = _script([
        _scene("setup", 2, action="the shop closes"),
        _scene("rising_action", 3, action="she walks"),
        _scene("climax", 9, action="she knocks"),
    ])

    ScreenwriterAgent._with_brief(script, "the power dies as she knocks", 2)

    assert len(script.scenes) == 2
    assert script.user_brief == "the power dies as she knocks"
    # The event landed on a scene that is still in the film.
    carriers = [s for s in script.scenes if (s.world_change or "").strip()]
    assert len(carriers) == 1


# ── the two layers together, through write_script ───────────────────────────


@pytest.mark.asyncio
async def test_a_five_scene_answer_to_a_three_scene_job_comes_back_as_three(
    monkeypatch,
):
    """The end the user sees: they asked for three, the writer wrote five, and
    what leaves the agent is three. Stubbed at the provider so the whole path
    runs -- prompt built, JSON parsed, brief applied, count held."""
    import agents.screenwriter as sw

    seen = {}

    async def fake_complete(system, user, max_tokens=0):
        seen["system"] = system
        seen["user"] = user
        return json.dumps({
            "title": "The Address",
            "logline": "A bookseller walks to an address one last time.",
            "characters": [
                {
                    "name": "Margit",
                    "description": "woman in her seventies",
                    "role": "protagonist",
                }
            ],
            "scenes": [
                {"action": "the shop at closing", "dramatic_function": "setup",
                 "tension": 2},
                {"action": "the letter falls out",
                 "dramatic_function": "inciting_incident", "tension": 5},
                {"action": "she walks", "dramatic_function": "rising_action",
                 "tension": 3},
                {"action": "she knocks", "dramatic_function": "climax",
                 "tension": 9},
                {"action": "the door opens", "dramatic_function": "resolution",
                 "tension": 6},
            ],
        })

    monkeypatch.setattr(sw, "complete_via_muapi", fake_complete)
    monkeypatch.setattr(sw, "is_muapi_llm_enabled", lambda: True)

    agent = ScreenwriterAgent(api_key="", demo=False)
    agent.muapi_key = "test-key"
    script = await agent.write_script(
        "An old bookseller walks to the address on an envelope.", num_scenes=3
    )

    assert len(script.scenes) == 3
    # Stated as well as enforced. The trim is the net, not the plan: a job that
    # leans on the net alone still pays for the scenes it then throws away.
    assert "EXACTLY 3 scenes" in seen["system"]
    assert "Scenes: 3" in seen["user"]
    # And the shape survived the cut.
    assert "climax" in [s.dramatic_function for s in script.scenes]
