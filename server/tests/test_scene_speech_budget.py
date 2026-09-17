"""A scene's line length is briefed from the same constants as its runtime."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_spoken_words_scales_with_the_scene():
    from interfaces.second_budget import (
        MAX_SCENE_SECONDS,
        MIN_SCENE_SECONDS,
        SECONDS_PER_CREDIT,
        spoken_words_for,
    )

    short = spoken_words_for(MIN_SCENE_SECONDS)
    nominal = spoken_words_for(SECONDS_PER_CREDIT)
    long = spoken_words_for(MAX_SCENE_SECONDS)

    assert short < nominal < long
    assert short >= 1


def test_the_brief_asks_for_more_than_job_a8d0766b_delivered():
    """The measured failure, turned into a threshold.

    Job a8d0766b-421 put 2.64s, 2.16s and 3.6s of speech into scenes of 9, 9
    and 12 seconds. Whatever the constants are tuned to, the brief has to ask
    for more speech than that, or it is not asking for anything.
    """
    from interfaces.second_budget import (
        SPEAKING_WORDS_PER_SECOND,
        SECONDS_PER_CREDIT,
        spoken_words_for,
    )

    delivered_speech_seconds = 3.6  # the most talkative of the three scenes
    briefed_seconds = spoken_words_for(SECONDS_PER_CREDIT) / SPEAKING_WORDS_PER_SECOND
    assert briefed_seconds > delivered_speech_seconds


def test_a_scene_is_never_briefed_to_talk_through_its_whole_take():
    """Speech has to leave room for the beats the budget already reserves."""
    from interfaces.second_budget import (
        SPEAKING_WORDS_PER_SECOND,
        SPEECH_BEAT_SECONDS,
        MAX_SCENE_SECONDS,
        spoken_words_for,
    )

    for seconds in (6.0, 10.0, MAX_SCENE_SECONDS):
        briefed = spoken_words_for(seconds) / SPEAKING_WORDS_PER_SECOND
        assert briefed + SPEECH_BEAT_SECONDS <= seconds, (
            f"{seconds}s scene briefed for {briefed:.1f}s of speech"
        )


def test_the_runtime_clause_states_a_word_count():
    """The two facts travel together or the writer reconciles them itself."""
    from agents.screenwriter import ScreenwriterAgent
    from interfaces.second_budget import SECONDS_PER_CREDIT, spoken_words_for

    agent = ScreenwriterAgent.__new__(ScreenwriterAgent)
    prompt = ScreenwriterAgent._system_prompt(agent, require_dialogue=True)

    assert str(spoken_words_for(SECONDS_PER_CREDIT)) in prompt
    assert "FILL THE RUNNING TIME" in prompt
