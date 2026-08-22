"""A line of dialogue is a subtitle too, and it is the same string.

The word captions are built from the written line
(elevenlabs_voice_generator._word_timings walks `spoken_text` and emits the
characters the line itself contains), so whatever spelling reaches the voice
provider also reaches the picture. A delivered drama's opening caption:

    container four-teen-oh-two

which is a pronunciation respelling -- helpful to a text-to-speech engine,
and a typo to everybody watching. Nothing in the pipeline put those hyphens
there; the screenwriter wrote them, because nothing had told it the line
would be read as well as heard.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402


def test_the_screenwriter_is_told_the_line_is_also_a_subtitle():
    clause = ScreenwriterAgent.DIALOGUE_CLAUSE
    assert "burned into the picture as a" in clause
    assert "subtitle, from the same string" in clause


def test_the_rule_names_the_spelling_that_shipped():
    """Stated as the pair it got wrong, not as an abstract prohibition -- a
    model follows "write X, never Y" far better than "avoid respellings"."""
    clause = ScreenwriterAgent.DIALOGUE_CLAUSE
    assert '"fourteen-oh-two"' in clause
    assert '"four-teen-oh-two"' in clause


def test_the_rule_reaches_the_prompt_a_voiced_script_is_written_from():
    agent = ScreenwriterAgent(api_key="test-key-not-real")
    voiced = agent._system_prompt(require_dialogue=True)
    assert "No pronunciation respellings" in voiced


def test_a_silent_script_is_not_lectured_about_subtitles():
    """The whole clause is conditional on the script being voiced; a silent
    one has no lines to spell and no captions to spell them into."""
    agent = ScreenwriterAgent(api_key="test-key-not-real")
    silent = agent._system_prompt(require_dialogue=False)
    assert "No pronunciation respellings" not in silent
