"""The screenwriter writes for a running time it was never told.

interfaces/second_budget fixes what a scene IS: about ten seconds of finished
film, six at the shortest and twelve at the longest, filmed as one continuous
shot from a single generated frame. The screenwriter was told how many scenes
to write and never how long one lasts -- so it wrote paragraphs. A delivered
script's second scene, approved by the user and rendered as a ten-second
single:

    Mara crosses the flooded aisle, boots splashing, and crouches at the
    container's manual release lever, rain streaming off her hood. The blue
    light pulses brighter with each breath she takes near it, throwing
    shifting light across her wet face. Her radio crackles.

Four beats. The storyboard picks ONE -- that is its whole job, "choose the
right moment" -- and the other three never reach the picture. The user reads
the script, approves it, and receives a film that shows a quarter of it.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.second_budget import (  # noqa: E402
    MAX_SCENE_SECONDS,
    MIN_SCENE_SECONDS,
    SECONDS_PER_CREDIT,
)


def _prompt(*args, **kwargs):
    return ScreenwriterAgent(demo=True)._system_prompt(*args, **kwargs)


def test_the_writer_is_told_what_a_scene_is_worth_in_seconds():
    prompt = _prompt()
    assert "WRITE TO THE RUNNING TIME" in prompt
    assert f"{SECONDS_PER_CREDIT:.0f} seconds" in prompt
    assert f"{MIN_SCENE_SECONDS:.0f} at the shortest" in prompt
    assert f"{MAX_SCENE_SECONDS:.0f} at the longest" in prompt


def test_the_numbers_come_from_the_budget_that_enforces_them():
    """Stated twice, they drift: the brief the writer is given and the budget
    the pipeline applies have to be the same fact."""
    import inspect

    source = inspect.getsource(ScreenwriterAgent._system_prompt)
    assert "SECONDS_PER_CREDIT" in source
    assert "MIN_SCENE_SECONDS" in source and "MAX_SCENE_SECONDS" in source


def test_it_asks_for_one_beat_rather_than_a_sequence():
    """The specific failure, named: a scene is not a paragraph of consecutive
    actions, because only the first of them gets filmed."""
    prompt = _prompt()
    assert "one beat" in prompt
    assert "four scenes' worth of film" in prompt
    assert "only the\nfirst of them will be shot" in prompt


def test_every_job_hears_it_whatever_else_it_asks_for():
    """A scene's length is a fact about the product, not something the caller
    chooses -- unlike the language and the scene count."""
    for kwargs in (
        {},
        {"num_scenes": 0},
        {"num_scenes": 3},
        {"language": "tr"},
        {"require_dialogue": True},
        {"narrative_mode": "micro_drama"},
    ):
        assert "WRITE TO THE RUNNING TIME" in _prompt(**kwargs), kwargs


def test_the_optional_clauses_are_still_optional():
    """The runtime clause must not have quietly turned the others on."""
    plain = _prompt("en")
    assert ScreenwriterAgent.SYSTEM_PROMPT in plain
    assert "SCENE COUNT IS FIXED" not in plain
    assert "Turkish" not in plain

    counted = _prompt("en", num_scenes=4)
    assert "SCENE COUNT IS FIXED" in counted


def test_the_runtime_is_stated_before_the_count():
    """How long a scene runs is what makes "compress it into three scenes"
    mean something; read the other way round it is an instruction to cram."""
    prompt = _prompt(num_scenes=3)
    assert prompt.index("WRITE TO THE RUNNING TIME") < prompt.index(
        "SCENE COUNT IS FIXED"
    )
