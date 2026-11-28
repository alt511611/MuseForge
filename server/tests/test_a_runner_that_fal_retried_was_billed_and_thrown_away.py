"""A runner fal retried on its own was billed, and we showed a failure.

Vidu Q4 job 01a2035e-666a-7551-a20f-44e759462b1e reported COMPLETED with
``error="Runner connection lost"``; fal re-queued it, it finished, and $0.126
was charged for a video fal_generate had already given up on. A failed status
is now watched for a grace window before it is believed.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fal_client

from tools import falai_common

LOST = "Runner connection lost"


class _Handle:
    request_id = "req-1"


class _Client:
    """status() replays `script`, then repeats its last entry."""

    def __init__(self, script):
        self.script = list(script)
        self.polls = 0
        self.submits = 0

    async def submit(self, endpoint, arguments):
        self.submits += 1
        return _Handle()

    async def status(self, endpoint, request_id, with_logs=False):
        item = self.script[min(self.polls, len(self.script) - 1)]
        self.polls += 1
        return item

    async def result(self, endpoint, request_id):
        return {"video": {"url": "https://fal/ok.mp4"}}


def _failed(error=LOST):
    return fal_client.Completed(logs=None, metrics={}, error=error)


def _done():
    return fal_client.Completed(logs=None, metrics={})


async def _run(client, **kw):
    return await falai_common.fal_generate(client, "ep", {"prompt": "x"}, poll_interval=0.01, **kw)


@pytest.mark.asyncio
async def test_a_runner_fal_requeues_and_finishes_is_not_a_failure(monkeypatch):
    monkeypatch.setattr(falai_common, "FAILED_STATUS_GRACE_SECONDS", 1.0)
    client = _Client([_failed(), fal_client.Queued(position=0), fal_client.InProgress(logs=[]), _done()])
    assert (await _run(client))["video"]["url"] == "https://fal/ok.mp4"
    assert client.submits == 1  # watched, not resubmitted: a resubmit would bill twice


@pytest.mark.asyncio
async def test_a_failure_that_stays_a_failure_still_raises(monkeypatch):
    monkeypatch.setattr(falai_common, "FAILED_STATUS_GRACE_SECONDS", 0.05)
    with pytest.raises(RuntimeError, match=LOST):
        await _run(_Client([_failed()]))


@pytest.mark.asyncio
async def test_the_grace_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(falai_common, "FAILED_STATUS_GRACE_SECONDS", 0)
    client = _Client([_failed()])
    with pytest.raises(RuntimeError, match=LOST):
        await _run(client)
    assert client.polls == 1


@pytest.mark.asyncio
async def test_a_content_flag_is_not_waited_on(monkeypatch):
    monkeypatch.setattr(falai_common, "FAILED_STATUS_GRACE_SECONDS", 5.0)
    client = _Client([_failed("[{'type': 'content_policy_violation'}]")])
    with pytest.raises(falai_common.ContentFlagged):
        await _run(client)
    assert client.polls == 2  # one per attempt of the existing flag retry
