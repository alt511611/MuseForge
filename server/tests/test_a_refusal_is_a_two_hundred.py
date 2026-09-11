"""The model can decline, and declining is not an error.

A refusal comes back as HTTP 200 with `stop_reason: "refusal"` and a category
in `stop_details`. Nothing raises, nothing retries, and the response simply
has no answer in it.

Two of the three callers here had no idea. The storyboard artist read the
empty answer as "the model wrote something unparseable" and returned [] --
the template shot list, which is the silent fallback its own comments record
fighting twice already, arriving a third time from a cause nobody had looked
for. The frame QA was worse: it fails OPEN by design, so a declined check
returned `character_ok: True` and the frame went through marked verified.

The screenwriter did handle it, and that is the shape the other two now take:
say it was declined, say the category, and say that sending the same thing
again will be declined again.

The second half of this file is the other sorting that was missing. Both
agents caught `APIStatusError` and treated every status inside it the same,
so a busy minute and a key that cannot reach the model logged the same line.
`RateLimitError` and `NotFoundError` are both subclasses of it, which is why
the order of the isinstance chain is the whole behaviour.
"""

import json
import os
import sys

import anthropic
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.anthropic_request import (  # noqa: E402
    classify,
    log_usage,
    refusal_of,
)


class _Message:
    """Only the two attributes refusal_of is allowed to read."""

    def __init__(self, stop_reason, stop_details=None):
        self.stop_reason = stop_reason
        self.stop_details = stop_details


class _Details:
    def __init__(self, category):
        self.category = category


def test_a_finished_message_is_not_a_refusal():
    assert refusal_of(_Message("end_turn")) is None
    assert refusal_of(_Message("max_tokens")) is None
    assert refusal_of(_Message("tool_use")) is None


def test_the_category_survives_being_one_nobody_listed():
    """The set is open, so the category is reported, never matched."""
    assert refusal_of(_Message("refusal", _Details("cyber"))) == "cyber"
    assert refusal_of(_Message("refusal", _Details("a_category_from_2027"))) == (
        "a_category_from_2027"
    )


def test_a_refusal_without_details_still_reads_as_a_refusal():
    """`stop_details` is null for every stop reason but this one, and the
    guard has to survive it being null for this one too."""
    assert refusal_of(_Message("refusal")) == "unspecified"
    assert refusal_of(_Message("refusal", _Details(None))) == "unspecified"


def _status_error(cls, status):
    request = anthropic._base_client.httpx.Request("POST", "https://api.anthropic.com")
    response = anthropic._base_client.httpx.Response(status, request=request, json={})
    return cls("boom", response=response, body=None)


def test_a_rate_limit_is_worth_retrying_and_a_bad_key_is_not():
    rate_limited = classify(_status_error(anthropic.RateLimitError, 429))
    assert rate_limited.kind == "rate_limit"
    assert rate_limited.retryable is True

    for cls, status in ((anthropic.AuthenticationError, 401),
                        (anthropic.PermissionDeniedError, 403)):
        failure = classify(_status_error(cls, status))
        assert failure.kind == "auth"
        assert failure.retryable is False, (
            "telling an operator to retry into a rejected key is the line "
            "that sent them looking for an outage"
        )


def test_the_specific_errors_are_not_swallowed_by_their_parent():
    """Every one of these IS an APIStatusError; the order is the behaviour."""
    for cls, status, kind in (
        (anthropic.NotFoundError, 404, "not_found"),
        (anthropic.BadRequestError, 400, "request"),
        (anthropic.InternalServerError, 500, "server"),
    ):
        error = _status_error(cls, status)
        assert isinstance(error, anthropic.APIStatusError)
        assert classify(error).kind == kind, (
            f"{cls.__name__} was sorted as its parent"
        )


def test_a_server_error_retries_and_a_client_error_does_not():
    assert classify(_status_error(anthropic.InternalServerError, 503)).retryable
    assert not classify(_status_error(anthropic.BadRequestError, 422)).retryable


def test_never_reaching_the_api_is_its_own_kind():
    request = anthropic._base_client.httpx.Request("POST", "https://api.anthropic.com")
    failure = classify(anthropic.APITimeoutError(request=request))
    assert failure.kind == "network"
    assert failure.retryable is True, "a timeout is the definition of try again"


def test_an_unrecognised_exception_is_not_reported_as_retryable():
    """A bug in our own code must not be logged as a busy upstream."""
    failure = classify(KeyError("text"))
    assert failure.kind == "unknown"
    assert failure.retryable is False


class _Usage:
    input_tokens = 900
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0
    output_tokens = 120


def test_every_call_accounts_for_all_four_billed_quantities(caplog):
    """Regular input, cache writes, cache reads and output are four prices.
    A roll-up that is missing one of them cannot price a film."""
    with caplog.at_level("INFO"):
        log_usage("frame_qa", "claude-sonnet-5", _Usage())

    for field in ("call=frame_qa", "model=claude-sonnet-5", "input=900",
                  "cache_write=0", "cache_read=0", "output=120"):
        assert field in caplog.text, f"{field} missing from the accounting line"


def test_a_cache_that_neither_read_nor_wrote_says_so(caplog):
    """cache_control is a REQUEST to cache. A prefix under the model's
    minimum, or one that differs between calls, is accepted and silently
    does nothing -- and the only evidence is these counters."""
    with caplog.at_level("WARNING"):
        log_usage("storyboard", "claude-sonnet-5", _Usage(), cached=True)
    assert "neither wrote nor read" in caplog.text


def test_a_call_that_never_asked_to_cache_is_not_scolded_for_not_caching():
    """The screenwriter deliberately does not cache; a warning there would be
    noise on every job."""
    import logging

    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.getLogger("tools.anthropic_request")
    logger.addHandler(handler)
    try:
        log_usage("screenwriter", "claude-sonnet-5", _Usage())
    finally:
        logger.removeHandler(handler)
    assert not [r for r in records if r.levelno >= logging.WARNING]
