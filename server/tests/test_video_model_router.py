"""Shot classification and the per-shot MuAPI model chain.

The chain is the resilience story: a shot whose endpoint is rejected used to
fail the scene, and every shot went to the same model regardless of whether it
was a talking close-up or a chase.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from tools.muapi_client import MuAPIError  # noqa: E402
from tools.video_model_router import (  # noqa: E402
    ACTION,
    DIALOGUE,
    ESTABLISHING,
    STANDARD,
    classify_shot,
    model_chain,
)


def test_dialogue_wins_over_camera_dynamics():
    # A handheld two-shot of people talking is still a dialogue shot: the
    # audience watches the faces, and a lip-sync pass has to work on them.
    assert (
        classify_shot(
            motion_desc="handheld drift", camera_movement="handheld",
            has_dialogue=True, has_character=True,
        )
        == DIALOGUE
    )


def test_action_detected_from_motion_words_and_from_tension():
    assert classify_shot(motion_desc="she runs down the alley") == ACTION
    # High tension reads as action even when the wording is calm, because the
    # storyboard agent writes restrained prose for the tensest beats.
    assert classify_shot(motion_desc="she waits", scene_tension=9) == ACTION


def test_characterless_shot_is_an_establishing_shot():
    assert classify_shot(motion_desc="slow push-in", has_character=False) == ESTABLISHING


def test_ordinary_shot_stays_standard():
    assert classify_shot(motion_desc="slow push-in", visual_desc="he lifts the cup") == STANDARD


def test_chain_is_unchanged_when_nothing_is_configured(monkeypatch):
    for env in ("MUAPI_VIDEO_MODEL_ACTION", "MUAPI_VIDEO_MODEL_DIALOGUE", "MUAPI_VIDEO_MODEL_ESTABLISHING"):
        monkeypatch.delenv(env, raising=False)
    from tools.muapi_video_generator import PRO_ENDPOINT, STANDARD_ENDPOINT

    assert model_chain(ACTION, plan="pro") == [PRO_ENDPOINT, STANDARD_ENDPOINT]
    # Free plan's endpoint IS Standard, so the chain collapses to one link
    # rather than listing the same endpoint twice.
    assert model_chain(ACTION, plan="free") == [STANDARD_ENDPOINT]


def test_configured_specialist_leads_but_never_replaces_the_paid_endpoint(monkeypatch):
    monkeypatch.setenv("MUAPI_VIDEO_MODEL_ACTION", "some-action-model")
    from tools.muapi_video_generator import PRO_ENDPOINT, STANDARD_ENDPOINT

    assert model_chain(ACTION, plan="pro") == [
        "some-action-model",
        PRO_ENDPOINT,
        STANDARD_ENDPOINT,
    ]
    # A profile with no specialist configured is untouched by another's.
    assert model_chain(DIALOGUE, plan="pro") == [PRO_ENDPOINT, STANDARD_ENDPOINT]


@pytest.mark.asyncio
async def test_rejected_endpoint_falls_through_to_the_next_link(monkeypatch):
    monkeypatch.setenv("MUAPI_VIDEO_MODEL_ACTION", "missing-model")
    from tools.muapi_video_generator import MuAPIVideoGenerator, STANDARD_ENDPOINT

    tried = []

    async def fake_generate(self, endpoint, payload, **kwargs):
        tried.append(endpoint)
        if endpoint != STANDARD_ENDPOINT:
            raise MuAPIError("MuAPI request failed: status_code=404 not found")
        return "https://fake.cdn/clip.mp4"

    monkeypatch.setattr("tools.muapi_client.MuAPIClient.generate", fake_generate)

    gen = MuAPIVideoGenerator("test-key-not-real")
    url = await gen.generate_video_from_image(
        prompt="p", image_url="https://fake.cdn/f.png", plan="pro", shot_profile=ACTION
    )
    assert url == "https://fake.cdn/clip.mp4"
    assert tried[0] == "missing-model"
    assert tried[-1] == STANDARD_ENDPOINT


@pytest.mark.asyncio
async def test_a_real_generation_failure_is_not_retried_on_every_model(monkeypatch):
    """A prompt MuAPI refuses fails identically everywhere.

    Walking the chain for it would spend the customer's time three times over
    and still fail, so only endpoint-level rejections may fall through.
    """
    monkeypatch.setenv("MUAPI_VIDEO_MODEL_ACTION", "some-action-model")
    from tools.muapi_video_generator import MuAPIVideoGenerator

    tried = []

    async def fake_generate(self, endpoint, payload, **kwargs):
        tried.append(endpoint)
        raise MuAPIError("MuAPI job failed: content policy")

    monkeypatch.setattr("tools.muapi_client.MuAPIClient.generate", fake_generate)

    gen = MuAPIVideoGenerator("test-key-not-real")
    with pytest.raises(MuAPIError):
        await gen.generate_video_from_image(
            prompt="p", image_url="https://fake.cdn/f.png", plan="pro", shot_profile=ACTION
        )
    assert len(tried) == 1
