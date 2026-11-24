"""Job 782c689e: the script was written ($0.13), the first portrait drew
`downstream_service_unavailable` on result fetch, and the job crashed.

Nothing in `fal_generate` retried anything but a content flag, so a blink in
one model host ended the whole job. A failed fal job is not billed; a resubmit
costs the wait.
"""
import os
import sys

import fal_client
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import falai_common  # noqa: E402

DOWN = (
    "[{'loc': ['body'], 'msg': 'Downstream service unavailable', "
    "'type': 'downstream_service_unavailable'}]"
)


class _Handle:
    request_id = "r"


class _Client:
    def __init__(self, fails, error=DOWN):
        self.fails, self.error, self.submits = fails, error, 0

    async def submit(self, endpoint, arguments):
        self.submits += 1
        return _Handle()

    async def status(self, endpoint, request_id, with_logs=False):
        return fal_client.Completed(logs=None, metrics={})

    async def result(self, endpoint, request_id):
        if self.submits <= self.fails:
            raise RuntimeError(self.error)
        return {"images": [{"url": "https://fal/ok.png"}]}


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr(falai_common, "TRANSIENT_BACKOFF_SECONDS", 0.0)


async def test_a_host_that_blinks_once_is_asked_again():
    client = _Client(fails=1)
    result = await falai_common.fal_generate(client, "fal-ai/x", {}, poll_interval=0)
    assert result["images"][0]["url"] == "https://fal/ok.png"
    assert client.submits == 2


async def test_a_host_that_stays_down_is_given_up_on_after_two_more_tries():
    client = _Client(fails=99)
    with pytest.raises(RuntimeError):
        await falai_common.fal_generate(client, "fal-ai/x", {}, poll_interval=0)
    assert client.submits == 3


async def test_a_request_fal_rejected_is_not_sent_again():
    client = _Client(fails=99, error="[{'msg': 'image_url is required', 'type': 'missing'}]")
    with pytest.raises(RuntimeError):
        await falai_common.fal_generate(client, "fal-ai/x", {}, poll_interval=0)
    assert client.submits == 1
