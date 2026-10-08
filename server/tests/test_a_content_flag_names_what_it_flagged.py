"""A content flag that survives its retry has to say what it flagged.

fal echoes the flagged prompt and reference URLs inside its own error, and that
echo was the only place they were ever written down. Translating the error into
a friendly sentence, as fal_generate now does, discarded it: the person is told
to change "the prompt wording" and neither they nor the log can say which words
-- or which stage, since every fal caller shares this one helper.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fal_client

from tools import falai_common

FLAG = (
    "[{'loc': ['body', 'prompt'], 'msg': 'The content could not be processed "
    "because it contained material flagged by a content checker.', "
    "'type': 'content_policy_violation'}]"
)


class _Handle:
    request_id = "req-1"


class _Client:
    """flags the first `flags` results, then succeeds."""

    def __init__(self, flags, error=FLAG):
        self.flags = flags
        self.error = error
        self.submits = 0

    async def submit(self, endpoint, arguments):
        self.submits += 1
        return _Handle()

    async def status(self, endpoint, request_id, with_logs=False):
        return fal_client.Completed(logs=None, metrics={})

    async def result(self, endpoint, request_id):
        if self.submits <= self.flags:
            raise RuntimeError(self.error)
        return {"images": [{"url": "https://fal/ok.png"}]}


ARGS = {
    "prompt": "Dahlia leans over the pot, fingers brushing her earring",
    "image_urls": ["https://fal/dahlia.jpg", "https://fal/set.png"],
}


@pytest.mark.asyncio
async def test_a_flag_that_clears_on_the_retry_is_never_seen(caplog):
    client = _Client(flags=1)
    with caplog.at_level(logging.WARNING):
        result = await falai_common.fal_generate(
            client, "fal-ai/flux-2-pro/edit", ARGS, poll_interval=0
        )
    assert result["images"][0]["url"] == "https://fal/ok.png"
    assert client.submits == 2


@pytest.mark.asyncio
async def test_a_flag_that_survives_the_retry_names_the_stage(caplog):
    client = _Client(flags=99)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError) as err:
            await falai_common.fal_generate(
                client, "fal-ai/flux-2-pro/edit", ARGS, poll_interval=0
            )
    assert client.submits == 2, "one retry, not a loop"
    assert "fal-ai/flux-2-pro/edit" in str(err.value)
    assert "content_policy_violation" not in str(err.value)


@pytest.mark.asyncio
async def test_the_flagged_prompt_and_references_reach_the_log(caplog):
    client = _Client(flags=99)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError):
            await falai_common.fal_generate(
                client, "fal-ai/flux-2-pro/edit", ARGS, poll_interval=0
            )
    text = caplog.text
    assert "Dahlia leans over the pot" in text
    assert "https://fal/dahlia.jpg" in text and "https://fal/set.png" in text


@pytest.mark.asyncio
async def test_a_single_reference_field_is_logged_too(caplog):
    client = _Client(flags=99)
    args = {"prompt": "p", "image_url": "https://fal/one.png"}
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError):
            await falai_common.fal_generate(client, "fal-ai/x", args, poll_interval=0)
    assert "https://fal/one.png" in caplog.text


@pytest.mark.asyncio
async def test_an_unrelated_failure_passes_through_untouched():
    client = _Client(flags=99, error="HTTP 500: upstream exploded")
    with pytest.raises(RuntimeError, match="upstream exploded"):
        await falai_common.fal_generate(client, "fal-ai/x", ARGS, poll_interval=0)
    assert client.submits == 1, "only a content flag is retried"
