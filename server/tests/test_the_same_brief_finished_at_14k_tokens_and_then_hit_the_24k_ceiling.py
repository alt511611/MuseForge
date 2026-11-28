"""Job 8e1a8dc7 was thrown away after 296 s at the 24000-token ceiling.

Job 82c56e88, an hour earlier, was the same four-scene brief with the same
7203 input tokens and finished at 14365 output tokens. Thinking and JSON share
the ceiling and thinking is adaptive, so the ceiling has to clear the bad draw.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.screenwriter import ScreenwriterAgent

TOKENS_PER_SECOND = 24000 / 296  # measured on the failed job


def test_the_ceiling_clears_the_draw_that_was_thrown_away():
    assert ScreenwriterAgent.MAX_SCRIPT_TOKENS >= 24000 * 1.3


def test_the_deadline_still_fits_the_whole_new_budget_with_margin():
    needed = ScreenwriterAgent.MAX_SCRIPT_TOKENS / TOKENS_PER_SECOND
    assert ScreenwriterAgent.SCRIPT_STREAM_TIMEOUT_SECONDS >= needed * 1.4
