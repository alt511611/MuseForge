"""Verify cancellation actually interrupts an in-flight MuAPI poll loop
quickly, instead of letting it run to completion regardless of the
cancel signal -- found via a free (no-cost) audit of the cancellation
path using mocked MuAPI calls.
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


@pytest.mark.asyncio
async def test_poll_result_stops_quickly_when_cancelled():
    from tools.muapi_client import MuAPIClient, MuAPICancelled

    poll_count = {"n": 0}

    class FakeResponse:
        status_code = 200

        def json(self):
            poll_count["n"] += 1
            return {"status": "processing"}  # never completes on its own

        def raise_for_status(self):
            pass

    async def fake_request(self, method, url, headers=None, **kwargs):
        return FakeResponse()

    client = MuAPIClient(api_key="test-key")
    cancelled = {"value": False}

    async def flip_cancel_soon():
        await asyncio.sleep(0.05)
        cancelled["value"] = True

    import httpx

    orig_request = httpx.AsyncClient.request
    httpx.AsyncClient.request = fake_request
    try:
        asyncio.create_task(flip_cancel_soon())
        with pytest.raises(MuAPICancelled):
            await client.poll_result(
                "fake-id",
                poll_interval=0.02,
                max_polls=1000,  # would take 20s+ without cancellation working
                is_cancelled=lambda: cancelled["value"],
            )
    finally:
        httpx.AsyncClient.request = orig_request

    # Should have stopped within a small handful of polls after the flag
    # flipped, not run anywhere near max_polls.
    assert poll_count["n"] < 20, f"Polling didn't stop promptly on cancel (polled {poll_count['n']} times)"


@pytest.mark.asyncio
async def test_script2video_translates_muapi_cancelled_to_pipeline_cancelled(monkeypatch):
    """A MuAPICancelled raised deep inside a MuAPI call must surface as
    PipelineCancelled at the script2video level, since that's the
    exception jobs.py already knows how to handle as a clean cancellation
    rather than a generic error."""
    from pipelines.script2video import Script2VideoPipeline, PipelineCancelled
    from tools.muapi_client import MuAPICancelled
    from interfaces.character import CharacterInScene
    from interfaces.shot import StoryboardShot

    async def fake_design_storyboard(self, script, characters, user_requirement, director_style, **_kwargs):
        return [StoryboardShot(idx=0, visual_desc="x", motion_desc="y")]

    async def fake_generate_image(self, prompt, aspect_ratio, is_cancelled=None):
        raise MuAPICancelled("simulated cancel mid-poll")

    monkeypatch.setattr(
        "agents.storyboard_artist.StoryboardArtist.design_storyboard", fake_design_storyboard
    )
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image", fake_generate_image
    )

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [CharacterInScene(idx=0, name="Alex", static_features="x", is_visible=True)]

    with pytest.raises(PipelineCancelled):
        await pipeline.run(script="test", characters=characters, working_dir="/tmp/museforge_cancel_test")
