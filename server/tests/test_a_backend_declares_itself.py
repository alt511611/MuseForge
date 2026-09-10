"""One declaration per endpoint, instead of five maps that had to agree.

This knowledge used to live in five parallel dictionaries -- accepted fields,
whether there is a duration field, whether it is an enum, which aspect ratios
it admits, and what it costs -- all keyed by the same slug and all maintained
by hand. They were five answers to one question, and forgetting one of them is
not an error anybody sees: an undeclared field is a 422, the fallback chain
reads 422 as "this model does not exist here", and the shot demotes to
Standard in silence. A routed model would have been configured, expected,
planned for and billed for in advance, and never once actually run.

These tests pin the contract, not the refactor: what a caller may ask a
backend, and what the router must do when a declaration turns out to be wrong.
"""

import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interfaces.video_backend import (
    BACKENDS,
    FLAT,
    PER_SECOND,
    Duration,
    backend_for,
    is_declared,
)


# --------------------------------------------------------------------------
# Duration: the three shapes an endpoint can have
# --------------------------------------------------------------------------

def test_a_range_clamps_and_an_enum_snaps():
    """Kling takes any integer 3..15; MuAPI's veo3.1 takes 8 and nothing else.

    Sending a Kling-shaped 6 or 10 to Veo is the 422 that used to read as a
    missing endpoint. A caller asks for the seconds it budgeted and the
    declaration turns that into something the endpoint accepts.
    """
    kling = Duration(minimum=3, maximum=15)
    assert kling.send(6) == 6
    assert kling.send(30) == 15
    assert kling.send(1) == 3

    veo = Duration(allowed=(8,))
    assert veo.send(6) == 8
    assert veo.send(12) == 8


def test_an_absent_duration_field_is_omitted_not_guessed():
    """The hailuo endpoints have no duration field; sending one is a 422."""
    absent = Duration(absent=True)
    assert absent.send(6) is None
    assert absent.delivers(6) == 0.0, "0.0 means unknown, not zero-length."
    assert absent.honours(6) is False


def test_the_caller_is_told_when_it_will_get_more_than_it_asked_for():
    """A 6-second scene on an 8-second enum comes back long and must be cut.

    This is the question the old maps could not answer at all -- they could
    correct the payload after the fact, but nothing could ask, before
    planning, whether a budget was deliverable here.
    """
    veo = Duration(allowed=(8,))
    assert veo.delivers(6) == 8.0
    assert veo.honours(6) is False

    kling = Duration(minimum=3, maximum=15)
    assert kling.delivers(6) == 6.0
    assert kling.honours(6) is True


def test_a_nonsense_duration_never_raises():
    """A caller may ask for six seconds without knowing what six means here."""
    assert Duration().send(None) == 3
    assert Duration().send("nonsense") == 3
    assert Duration(allowed=(8,)).send(None) == 8


# --------------------------------------------------------------------------
# The router reads the declaration, and nothing else
# --------------------------------------------------------------------------

def test_the_router_functions_are_readers_over_the_registry():
    from tools import video_model_router as router

    assert router.optional_fields("veo3.1-lite-image-to-video") == (
        backend_for("veo3.1-lite-image-to-video").fields
    )
    assert router.fixed_duration("veo3.1-lite-image-to-video") == 8
    assert router.fixed_duration("kling-v3.0-standard-image-to-video") is None
    assert router.accepts_aspect_ratio("veo3.1-lite-image-to-video", "9:16")
    assert not router.accepts_aspect_ratio("veo3.1-lite-image-to-video", "1:1")
    assert router.send_duration("veo3.1-lite-image-to-video", 6) == 8
    assert router.delivered_seconds("veo3.1-lite-image-to-video", 6) == 8.0


def test_an_undeclared_endpoint_keeps_the_conservative_default():
    """Assumed to take a prompt, an image and a duration. Nothing else.

    The permissive direction is the dangerous one: declaring a field an
    endpoint rejects costs a silent demotion, which is what the registry
    exists to stop.
    """
    unknown = backend_for("some-model-nobody-declared")
    assert unknown.fields == frozenset({"duration"})
    assert unknown.accepts_aspect_ratio("1:1") is True
    assert unknown.max_elements == 0
    assert unknown.multishot is False
    assert not is_declared("some-model-nobody-declared")
    assert is_declared("kling-v3.0-standard-image-to-video")


# --------------------------------------------------------------------------
# Capabilities the planner needs and had nowhere to read
# --------------------------------------------------------------------------

def test_native_audio_is_declared_per_language_not_as_a_boolean():
    """"Has native audio" is not a property an endpoint has; a LANGUAGE is.

    A pipeline that lays its own dialogue over the picture has to know the
    difference, and the difference is per language: an endpoint that speaks
    English and not Turkish is not "an endpoint with native audio".
    """
    kling = backend_for("kling-v3.0-standard-image-to-video")
    assert kling.speaks("en")
    assert not kling.speaks("tr")

    turbo = backend_for("kling-v3-turbo-standard-image-to-video")
    assert not turbo.speaks("en"), "Turbo has no audio flag at all."


def test_the_billing_shape_is_declared_because_it_inverts_the_ranking():
    """A short clip does not get a discount from a per-second rate.

    Pinned so nobody 'optimises' a three-second reaction shot onto turbo.
    """
    turbo = backend_for("kling-v3-turbo-standard-image-to-video")
    veo = backend_for("veo3.1-lite-image-to-video")

    assert turbo.billing == PER_SECOND
    assert veo.billing == FLAT
    assert turbo.cost(3) > veo.cost(3), (
        "The cheap-sounding endpoint is the expensive one for a short shot."
    )
    assert veo.cost(3) == veo.cost(8), "Flat is flat."


def test_every_declared_backend_is_self_consistent():
    """A declaration that contradicts itself is worse than no declaration."""
    for slug, declared in BACKENDS.items():
        assert declared.slug == slug, f"{slug} declares a different slug"
        if declared.duration.absent:
            assert "duration" not in declared.fields, (
                f"{slug} has no duration field but declares one"
            )
        else:
            assert "duration" in declared.fields, (
                f"{slug} quantises duration but does not declare the field"
            )
        if declared.aspect_ratios:
            assert "aspect_ratio" in declared.fields, (
                f"{slug} restricts aspect ratios but takes no such field"
            )
        assert declared.billing in (FLAT, PER_SECOND)
        assert declared.rate >= 0


# --------------------------------------------------------------------------
# The failure this whole registry exists to make visible
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_declared_endpoint_that_refuses_our_payload_is_an_error_not_noise(caplog):
    """422 from an endpoint we DESCRIBED means our description is wrong.

    404 and 422 both demote, and they mean opposite things: 404 is a slug this
    vendor does not have, 422 is a payload we built from our own declaration
    and it was refused. Only the second is a bug in
    interfaces/video_backend.BACKENDS, and it must not read like routine
    fallback noise -- it is the exact failure the registry exists to prevent.
    """
    from tools.muapi_client import MuAPIError
    from tools.muapi_video_generator import MuAPIVideoGenerator

    generator = MuAPIVideoGenerator(api_key="k", demo=False)
    calls = []

    async def fake_generate(endpoint, payload, **kwargs):
        calls.append(endpoint)
        if len(calls) == 1:
            raise MuAPIError("HTTP 422: Unprocessable Entity")
        return "https://cdn/clip.mp4"

    generator.client.generate = fake_generate

    with caplog.at_level(logging.ERROR):
        result = await generator.generate_video_from_image(
            prompt="x", image_url="https://cdn/frame.png", duration=6, plan="pro"
        )

    assert result == "https://cdn/clip.mp4", "Still fail-open: the shot survives."
    assert len(calls) == 2, "It still demoted to the next link in the chain."
    errors = " ".join(r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)
    assert "video_backend" in errors, (
        "The log has to name the file that is wrong, not just report a fallback."
    )
    assert calls[0] in errors


@pytest.mark.asyncio
async def test_an_undeclared_endpoint_refusing_us_is_ordinary_fallback(caplog):
    """Nothing claimed to know this endpoint's schema, so 422 blames nobody."""
    from tools.muapi_client import MuAPIError
    from tools.muapi_video_generator import MuAPIVideoGenerator

    generator = MuAPIVideoGenerator(api_key="k", demo=False)
    calls = []

    async def fake_generate(endpoint, payload, **kwargs):
        calls.append(endpoint)
        if len(calls) == 1:
            raise MuAPIError("HTTP 404: Not Found")
        return "https://cdn/clip.mp4"

    generator.client.generate = fake_generate

    with caplog.at_level(logging.DEBUG):
        await generator.generate_video_from_image(
            prompt="x", image_url="https://cdn/frame.png", duration=6, plan="pro"
        )

    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], (
        "A 404 is a configuration question, not a bug in the registry."
    )


# --------------------------------------------------------------------------
# The payload is built from the declaration
# --------------------------------------------------------------------------

def test_the_payload_carries_only_declared_fields():
    from tools.muapi_video_generator import MuAPIVideoGenerator

    generator = MuAPIVideoGenerator(api_key="k", demo=False)

    veo = generator._payload(
        "prompt",
        "https://cdn/frame.png",
        duration=6,
        generate_audio=True,
        last_image="https://cdn/end.png",
        endpoint="veo3.1-lite-image-to-video",
        aspect_ratio="9:16",
    )
    assert veo["duration"] == 8, "Snapped to the endpoint's enum."
    assert "generate_audio" not in veo, "Veo's audio is always on; no flag."
    assert veo["last_image"] == "https://cdn/end.png"
    assert veo["aspect_ratio"] == "9:16"

    turbo = generator._payload(
        "prompt",
        "https://cdn/frame.png",
        duration=6,
        generate_audio=True,
        last_image="https://cdn/end.png",
        endpoint="kling-v3-turbo-standard-image-to-video",
        aspect_ratio="9:16",
    )
    assert turbo["duration"] == 6
    assert "last_image" not in turbo, "Turbo takes no end frame."
    assert "generate_audio" not in turbo
    assert "aspect_ratio" not in turbo


def test_an_endpoint_with_no_duration_field_gets_no_duration():
    from tools.muapi_video_generator import MuAPIVideoGenerator

    generator = MuAPIVideoGenerator(api_key="k", demo=False)
    payload = generator._payload(
        "prompt",
        "https://cdn/frame.png",
        duration=6,
        endpoint="minimax-hailuo-2.3-pro-i2v",
        aspect_ratio="9:16",
    )
    assert payload == {"prompt": "prompt", "image_url": "https://cdn/frame.png"}


def test_an_unsupported_aspect_ratio_is_dropped_not_sent():
    """Omitting it lets the model use its default rather than rejecting us."""
    from tools.muapi_video_generator import MuAPIVideoGenerator

    generator = MuAPIVideoGenerator(api_key="k", demo=False)
    payload = generator._payload(
        "prompt",
        "https://cdn/frame.png",
        duration=8,
        endpoint="veo3.1-lite-image-to-video",
        aspect_ratio="1:1",
    )
    assert "aspect_ratio" not in payload


# --------------------------------------------------------------------------
# One source of truth for what a render costs
# --------------------------------------------------------------------------

def test_the_pricing_test_reads_the_registry_rather_than_a_second_copy():
    """A second copy is how a margin gets computed from a rate we do not pay."""
    from tests.test_pricing_coherence import KLING_PER_GENERATION, MUAPI_RATES

    assert KLING_PER_GENERATION == backend_for(
        "kling-v3.0-standard-image-to-video"
    ).rate
    for slug, declared in BACKENDS.items():
        assert MUAPI_RATES[slug] == declared.rate
