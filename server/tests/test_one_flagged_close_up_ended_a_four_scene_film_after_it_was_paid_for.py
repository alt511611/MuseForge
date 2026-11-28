"""Job 5fa6f615: the image checker flagged a close-up of a sixteen-year-old
twice, and that one shot ended the film.

The flag is respected -- the prompt is never reworded to get past it -- but it
is answered at that shot: the shot starts from its locked reference.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipelines.script2video import frame_surviving_a_flag  # noqa: E402
from tools.falai_common import ContentFlagged  # noqa: E402


async def test_a_frame_the_checker_accepts_is_the_frame_drawn():
    async def draw(text):
        return "https://fal/frame.png"

    url, flagged = await frame_surviving_a_flag(draw, "p", fallback_url="https://fal/portrait.jpg")
    assert (url, flagged) == ("https://fal/frame.png", False)


async def test_a_flagged_shot_starts_from_its_locked_reference_and_nothing_is_reworded():
    prompts = []

    async def draw(text):
        prompts.append(text)
        raise ContentFlagged("flagged")

    url, flagged = await frame_surviving_a_flag(
        draw, "extreme close-up of a teenage boy", fallback_url="https://fal/portrait.jpg"
    )
    assert (url, flagged) == ("https://fal/portrait.jpg", True)
    assert prompts == ["extreme close-up of a teenage boy"], "one attempt, the prompt untouched"


async def test_with_nothing_honest_to_start_from_the_flag_is_still_raised():
    async def draw(text):
        raise ContentFlagged("flagged")

    with pytest.raises(ContentFlagged):
        await frame_surviving_a_flag(draw, "p", fallback_url="")


async def test_a_failure_that_is_not_a_flag_is_not_swallowed():
    async def draw(text):
        raise RuntimeError("fal is down")

    with pytest.raises(RuntimeError):
        await frame_surviving_a_flag(draw, "p", fallback_url="https://fal/portrait.jpg")


def test_the_cache_warning_is_silent_where_the_provider_reports_no_cache(monkeypatch, caplog):
    import logging
    from types import SimpleNamespace

    from tools.anthropic_request import log_usage

    usage = SimpleNamespace(input_tokens=5, output_tokens=5)
    monkeypatch.setenv("MUSEFORGE_LLM_PROVIDER", "falai")
    with caplog.at_level(logging.WARNING):
        log_usage("storyboard", "m", usage, cached=True)
    assert "asked to cache" not in caplog.text
    monkeypatch.setenv("MUSEFORGE_LLM_PROVIDER", "anthropic")
    with caplog.at_level(logging.WARNING):
        log_usage("storyboard", "m", usage, cached=True)
    assert "asked to cache" in caplog.text
