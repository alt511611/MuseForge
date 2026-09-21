"""Lip sync was charged on three scenes and delivered on none of them.

The sync provider is handed ONE combined audio file per scene and one face to
drive with it. It cannot know that a second visible character takes over
halfway through that file, so `idea2video._has_one_visible_speaker` refuses
such a scene before any provider is paid. That refusal is correct and is not
what this file is about.

What this file is about is that nothing ever told the SCREENWRITER. Delivered
job 532aa102-86f:

    Scene 0 has multiple visible speakers in one combined dialogue track;
    keeping it as voice-over instead of driving the wrong face.
    Scene 1 has multiple visible speakers ...
    Scene 2 has multiple visible speakers ...
    Lip sync was charged for 3 scene(s), delivered on 0; refunding 3
    undelivered scene surcharge(s).

The refund is right and the film still played — three scenes of closed mouths
over voice-over, on a job that had asked and paid for the opposite. Job
4631cc44-d30 synced all three of ITS scenes a few hours earlier with no code
difference between the two runs: its second voice happened to be a dispatcher
on a radio, which is off-screen, which the gate does not count. Whether the
feature the customer bought arrived at all was a property of the script's
shape, settled by a writer who had never been told the shape was load-bearing.

`grep -n "lip sync" agents/screenwriter.py` returned nothing at all.
"""

import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from pipelines.idea2video import (  # noqa: E402
    Idea2VideoPipeline,
    _has_one_visible_speaker,
)


def _agent():
    return ScreenwriterAgent(demo=True)


# ── the instruction exists, and only when it was bought ─────────────────────


def test_a_job_that_bought_sync_is_told_who_may_speak():
    """THE TEST THIS FILE EXISTS FOR."""
    prompt = _agent()._system_prompt(require_dialogue=True, lipsync_enabled=True)
    assert "LIP SYNC" in prompt
    # The rule itself, not merely the subject.
    assert "ONE character who is visible" in prompt


def test_the_rule_comes_with_the_way_out():
    """A hard "one speaker per scene" with no escape costs the drama every
    exchange it has. The escape is the one job 4631cc44-d30 took by accident
    and the one _heard_but_never_seen already reads for: a voice off-screen."""
    prompt = _agent()._system_prompt(require_dialogue=True, lipsync_enabled=True)
    rule = prompt.split("LIP SYNC")[1]
    for hatch in ("off-screen", "radio", "intercom", "(O.S.)"):
        assert hatch in rule, f"the clause does not offer {hatch!r} as a way out"
    # ...and the other way out: two people face to face get two scenes.
    assert "split" in rule


def test_a_job_that_did_not_buy_sync_keeps_its_two_handers():
    """The clause costs the drama its face-to-face scenes. That is not a price
    to charge a job which was never going to sync anyway."""
    prompt = _agent()._system_prompt(require_dialogue=True, lipsync_enabled=False)
    assert "LIP SYNC" not in prompt


def test_the_rule_reaches_both_provider_paths():
    """The MuAPI LLM route is tried FIRST, so a clause added only to the
    Anthropic fallback would do nothing on the primary path. Same shape as
    test_language's check, for the same reason."""
    source = inspect.getsource(ScreenwriterAgent.write_script)
    # Twice: once into the MuAPI path's own _system_prompt call, once into the
    # Anthropic delegation. Counted rather than matched against one exact
    # spelling, because a test that breaks on reformatting stops being read.
    assert source.count("lipsync_enabled=lipsync_enabled") >= 2, (
        "write_script does not pass the flag down both provider paths"
    )
    assert (
        "lipsync_enabled"
        in inspect.signature(ScreenwriterAgent._write_with_claude).parameters
    )
    claude = inspect.getsource(ScreenwriterAgent._write_with_claude)
    assert "lipsync_enabled=lipsync_enabled" in claude


# ── and the flag actually gets there from a job ─────────────────────────────


def test_the_flag_is_threaded_from_the_pipeline_to_the_writer():
    """A clause nothing can switch on is a clause that never runs. Every hop
    is asserted because each one is a separate place to drop it."""
    for fn in (Idea2VideoPipeline.write_script_only, Idea2VideoPipeline.run):
        assert "lipsync_enabled" in inspect.signature(fn).parameters, (
            f"{fn.__name__} cannot be told the sync was bought"
        )
    assert "lipsync_enabled=lipsync_enabled" in inspect.getsource(
        Idea2VideoPipeline.run
    ), "the full run does not pass it to the script phase"
    # The writer is only constrained when the lines will actually be voiced:
    # a silent script has no speakers to keep to one.
    assert "lipsync_enabled=lipsync_enabled and dialogue_enabled" in inspect.getsource(
        Idea2VideoPipeline.write_script_only
    )


def test_the_approve_script_path_is_told_too():
    """By the time continue_from_script sees the flag, the script has been
    written, approved and is about to be shot -- the same argument the
    dialogue_enabled comment beside it already makes."""
    import jobs

    source = inspect.getsource(jobs)
    # Bounded by the next argument of the enclosing wait_for rather than by the
    # first ")", which lands inside a comment in this block.
    call = source.split("pipeline.write_script_only(")[1].split("timeout=")[0]
    assert "lipsync_enabled=job.lipsync_enabled" in call


# ── the gate this is written against, unchanged ─────────────────────────────


@pytest.mark.parametrize(
    "lines, off_screen, expected, what",
    [
        ([{"character": "Reya", "line": "Here."}], set(), True, "a one-hander"),
        (
            [
                {"character": "Reya", "line": "Here."},
                {"character": "Tomas", "line": "Copy that."},
            ],
            set(),
            False,
            "the delivered job's shape: two visible speakers",
        ),
        (
            [
                {"character": "Reya", "line": "Here."},
                {"character": "Control", "line": "Copy that."},
            ],
            {"control"},
            True,
            "the same exchange with the second voice on a radio",
        ),
    ],
)
def test_the_clause_is_written_against_this_gate(lines, off_screen, expected, what):
    """The clause is only worth its cost if it is aimed at the real rule. This
    pins what the screenwriter is being asked to satisfy -- including that the
    off-screen hatch the clause offers is one the gate actually honours."""
    assert _has_one_visible_speaker(lines, off_screen) is expected, what
