"""Two dramas with nothing in common came back cut in the same places.

Job 49512158 is a rain-soaked cargo harbour. Job 9da99938 is a basement card
game. Different stories, different casts, different aspect ratios, one of them
in colour and one in black and white. Read off the delivered files, their cut
points:

    49512158   1.96  5.42  8.04  11.67  15.00  18.08  27.13
    9da99938   1.96  4.88  8.04  11.67  15.00  18.04  26.58

Six of seven within half a second of each other, and both films then hold one
static shot for eight or nine seconds from 18s -- which is where the payoff
of both briefs was supposed to be.

That is not two films that happen to be paced alike. Neither film was asked
for a rhythm at all. DEFAULT_SHOTS_PER_SCENE is one, so the storyboard designs
one shot per scene, so plan_scene_take builds one beat, so generate_scene_take
takes its single-`prompt` branch -- and `shot_type: "customize"`, the field
that makes a shot list BINDING rather than a suggestion, is never sent. The
model cut both films where it liked, and it likes the same places.

The constant was right when it was written: a second angle was a second frame
generation and a second image-to-video call. It is wrong for a multishot
endpoint billed per second, where the scene is one request from one frame and
the bill is the seconds either way. So the count stops being a constant and
becomes a question about the endpoint.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import agents.storyboard_artist as storyboard  # noqa: E402
from agents.storyboard_artist import shots_per_scene  # noqa: E402
from interfaces.scene_take import Element, plan_scene_take  # noqa: E402
from interfaces.shot_plan import (  # noqa: E402
    MAX_COVERAGE,
    coverage_a_take_affords,
)
from interfaces.video_backend import BACKENDS, PER_SECOND, backend_for  # noqa: E402

MULTISHOT = "fal-ai/kling-video/v3/standard/image-to-video"


class _Shot:
    def __init__(self, seconds=4, framing="wide"):
        self.visual_desc = "Vivian Marsh slides the chip stack forward"
        self.motion_desc = ""
        self.shot_type = framing
        self.deliver_seconds = seconds
        self.duration_seconds = seconds


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_SHOTS_PER_SCENE", raising=False)
    monkeypatch.delenv("MUSEFORGE_VIDEO_PROVIDER", raising=False)
    storyboard._COVERAGE_MEMO.clear()
    yield
    storyboard._COVERAGE_MEMO.clear()


def test_an_endpoint_that_cannot_cut_is_still_answered_one():
    """Every endpoint this pipeline had before scene_take, unchanged. The
    cost argument that set the constant is still true of all of them."""
    for slug, backend in BACKENDS.items():
        if backend.multishot:
            continue
        assert coverage_a_take_affords(backend) == 1, slug
    assert coverage_a_take_affords(None) == 1, "an unknown endpoint is not a free one"


def test_a_flat_billed_multishot_endpoint_is_not_free_either():
    """The beat is free because the SECONDS are what is metered. Priced per
    generation, a second angle is a second price, and this does not guess."""
    per_second = backend_for(MULTISHOT)
    assert per_second.billing == PER_SECOND
    assert coverage_a_take_affords(per_second) == MAX_COVERAGE

    flat = per_second.__class__(**{**per_second.__dict__, "billing": "flat"})
    assert coverage_a_take_affords(flat) == 1


def test_the_operator_still_outranks_the_endpoint(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_multishot")
    storyboard._COVERAGE_MEMO.clear()
    assert shots_per_scene() == MAX_COVERAGE, "the endpoint's answer"

    monkeypatch.setenv("MUSEFORGE_SHOTS_PER_SCENE", "2")
    assert shots_per_scene() == 2, "and the operator's answer wins over it"


def test_a_deployment_that_cannot_cut_renders_exactly_as_it_did():
    """The whole change has to be invisible to every existing deployment:
    the default provider is muapi, whose endpoints are all single-shot."""
    assert shots_per_scene() == 1


@pytest.mark.asyncio
async def test_the_shot_list_is_only_binding_when_there_is_one():
    """The consequence the delivered films are made of.

    One shot is not a shot list. The payload loses `multi_prompt` AND
    `shot_type: "customize"` with it, and the model is left to cut the scene
    however it cuts scenes -- which is the same way twice.
    """
    from tools.falai_video_generator import FalAIVideoGenerator

    async def _payload_for(shot_count):
        generator = FalAIVideoGenerator(api_key="test-key", demo=False)
        sent = {}

        async def fake_run(payload, endpoint, is_cancelled=None):
            sent.update(payload)
            return "https://cdn/scene.mp4"

        generator._run = fake_run
        take = plan_scene_take(
            12,
            [_Shot() for _ in range(shot_count)],
            backend_for(MULTISHOT),
            elements=[Element(name="Vivian Marsh", images=("v1.png",))],
            start_image="https://cdn/frame.png",
        )
        await generator.generate_scene_take(take)
        return sent

    alone = await _payload_for(1)
    assert "multi_prompt" not in alone
    assert "shot_type" not in alone, (
        "with one beat the cuts are the model's to choose, and it chose the "
        "same seven for two unrelated films"
    )

    covered = await _payload_for(MAX_COVERAGE)
    assert len(covered["multi_prompt"]) > 1
    assert covered["shot_type"] == "customize", (
        "customize is what makes the storyboard binding rather than a hint"
    )


def test_coverage_costs_the_scene_nothing_it_was_not_already_paying():
    """One frame, one call, the same seconds -- which is the entire reason
    the old cost cap does not apply to this endpoint."""
    backend = backend_for(MULTISHOT)
    one = plan_scene_take(12, [_Shot()], backend, start_image="f.png")
    many = plan_scene_take(
        12, [_Shot() for _ in range(MAX_COVERAGE)], backend, start_image="f.png"
    )

    assert one.seconds == many.seconds, "the bill is the seconds"
    assert one.start_image == many.start_image == "f.png", "and one frame"
    assert len(many.beats) > len(one.beats), "for more cuts"
