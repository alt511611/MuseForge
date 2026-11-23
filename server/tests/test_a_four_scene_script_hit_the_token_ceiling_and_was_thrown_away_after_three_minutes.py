"""The script budget has to fit a four-scene drama, and its deadline the budget.

Two production jobs on 2026-11-22 (451971f2 at 188 s, the one before at 204 s)
wrote four scenes with five described characters and were cut off at
MAX_SCRIPT_TOKENS=16000 -- mid-JSON, nothing salvageable, nothing shown. The
jobs that did fit ended at 14045 and 15165 tokens, so the ceiling sat inside the
size of an ordinary request.

Raising the ceiling alone moves the failure: the stream is drained under a
deadline, and at the ~85 tokens a second those jobs measured the whole budget
has to FIT inside it, or a long script dies as an "outage" at the deadline
instead of finishing.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.screenwriter import ScreenwriterAgent

#: Measured on job 451971f2: 16000 tokens in 188 s.
MEASURED_TOKENS_PER_SECOND = 16000 / 188


def test_the_budget_clears_the_biggest_script_that_did_fit_with_room_to_spare():
    biggest_that_fit = 15165
    assert ScreenwriterAgent.MAX_SCRIPT_TOKENS >= biggest_that_fit * 1.4


def test_the_whole_budget_streams_inside_the_deadline_with_margin():
    seconds_for_the_whole_budget = ScreenwriterAgent.MAX_SCRIPT_TOKENS / MEASURED_TOKENS_PER_SECOND
    assert ScreenwriterAgent.SCRIPT_STREAM_TIMEOUT_SECONDS >= seconds_for_the_whole_budget * 1.5


def test_the_job_deadline_is_nowhere_near_the_script_deadline():
    # The pipeline's own cap is two hours; this guards against the script
    # deadline ever being raised past it by mistake.
    import jobs

    assert ScreenwriterAgent.SCRIPT_STREAM_TIMEOUT_SECONDS < jobs.PIPELINE_HARD_TIMEOUT_SECONDS / 10
