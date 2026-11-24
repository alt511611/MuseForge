"""Job 93aa0ac7: fal answered 403 "User is locked. Reason: Exhausted balance."
on the very first call, and the customer read that the script service "is not
configured correctly -- please contact support". Nothing was misconfigured; our
supplier account was empty, which is a top-up for us and a retry for them.
A genuinely rejected key must still read as a configuration problem.
"""

import os
import sys

import anthropic
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.screenwriter import ScreenwriterAgent  # noqa: E402


def _status_error(status, text):
    request = httpx.Request("POST", "https://fal.run/x")
    response = httpx.Response(status, request=request, text=text)
    return anthropic.AsyncAnthropic(api_key="x")._make_status_error_from_response(response)


def test_an_empty_supplier_balance_is_not_called_a_misconfiguration():
    exc = _status_error(403, "User is locked. Reason: Exhausted balance.")
    message = ScreenwriterAgent._failure_message(exc)
    assert "not configured" not in message and "contact support" not in message
    assert "try again" in message


def test_a_rejected_key_is_still_a_configuration_problem():
    exc = _status_error(401, "Invalid API key")
    assert "not configured correctly" in ScreenwriterAgent._failure_message(exc)
