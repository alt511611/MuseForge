"""The storyboard writes for a reader it was never told about.

Its "visual_desc" is not read by a person. It is pasted into a prompt for a
diffusion model, and its "motion_desc" into a prompt for a video model, and
the brief tells it how LONG to write without ever saying who reads it.

Two measured consequences of that gap.

A frame prompt taken off a delivered job carried, in the shot's own sentence,
the phrase "no markings" beside an outfit that names a satchel while the
costume lock forbids a bag. An image model has no NOT: every noun in the
prompt is a noun that was asked for. The budget rules in this brief are
about length; nothing in it was about the grammar the reader actually parses.

And job 49512158 -- "a dock worker finds a shipping container that hums with
light, and the city's power dies the moment she opens it" -- opened on a lit
skyline, established it, and then spent its last three seconds on a lamp
dimming beside one face. The city never went dark on camera. The brief was
honoured noun by noun and its promise had no shot, because the storyboard was
told to honour what the brief LISTS and never told to find what it PROMISES.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import (  # noqa: E402
    StoryboardArtist,
    system_prompt_for,
)

PROMPT = StoryboardArtist.SYSTEM_PROMPT


def test_the_brief_is_read_for_its_promise_and_not_only_its_nouns():
    assert "HONOUR WHAT IT PROMISED" in PROMPT
    assert "49512158" not in PROMPT, (
        "a job id is evidence for the reader of this repo, not instruction "
        "for the model -- the brief pays for every character it carries"
    )
    assert "pays it off" in PROMPT


def test_the_brief_names_who_actually_reads_the_shot():
    assert "WRITE FOR THE MODELS THAT READ THIS" in PROMPT
    assert "image model" in PROMPT and "video model" in PROMPT


def test_the_negation_rule_is_stated_as_a_rule_about_the_reader():
    """"Do not write no" is a style note. "The reader has no NOT" is a
    reason, and a reason survives a case the rule did not enumerate."""
    assert "NEVER WRITE A NEGATION" in PROMPT
    assert "has no NOT" in PROMPT
    assert "Say what IS" in PROMPT


def test_the_shot_is_told_to_lead_with_its_subject():
    """The render step places this sentence at the top of the frame prompt
    precisely because an image model weights the opening hardest."""
    assert "SUBJECT and the ACTION first" in PROMPT
    assert "weights the opening" in PROMPT


def test_the_locked_clauses_are_not_paid_for_twice():
    """The setting and the lighting plan are appended to every frame prompt
    word for word; a second copy comes out of the budget that the eyeline and
    closed-cast rules are already the first to lose."""
    assert "Do not restate the setting" in PROMPT


def test_the_motion_field_is_told_that_its_overrun_fails_the_scene():
    """Unlike every other budget in this brief, this one is not a degraded
    picture: the take is one generation with a hard per-beat budget, and a
    beat over it is a 422 and no scene at all."""
    assert 'ONE CONTINUOUS ACTION IN "motion_desc"' in PROMPT
    assert "fails the whole" in PROMPT


def test_none_of_it_is_lost_when_the_scene_takes_more_than_one_shot():
    """system_prompt_for rewrites sentences INSIDE the brief, so a section
    added after it was written is exactly the kind of thing that gets
    silently dropped on a multi-shot deployment."""
    multi = system_prompt_for(PROMPT, 4)

    assert "Design exactly 4 shots" in multi, "the rewrite still applies"
    for heading in (
        "HONOUR WHAT IT PROMISED",
        "WRITE FOR THE MODELS THAT READ THIS",
        "NEVER WRITE A NEGATION",
        'ONE CONTINUOUS ACTION IN "motion_desc"',
    ):
        assert heading in multi, f"{heading} did not survive the rewrite"
