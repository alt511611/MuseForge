"""A delivered master has to BE a resolution, not merely have one.

The audited master measured 1276x718: the old rule fitted the largest 16:9
rectangle inside what the provider really rendered and capped it at 1080p,
which is honest about not upscaling and says nothing at all about landing on a
size an editor, a platform or a spec sheet recognises. Fourteen pixels of
width were saved and the file stopped being a 720p file.

The other half is the tier: no video model here renders 4K, so a 4K delivery
is an upscale -- one that is declared, recorded, and only ever performed when
a customer orders it.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --- the ladder ----------------------------------------------------------


def test_the_audited_master_lands_on_720p():
    """1276x718, delivered. The fit is within 0.3% of a real resolution."""
    from interfaces.delivery import plan_delivery

    delivery = plan_delivery(1276, 718, "16:9")

    assert delivery.size == (1280, 720)
    # And it is not an upscale in any sense a viewer would recognise.
    assert delivery.upscaled is False


def test_a_provider_house_size_still_lands_on_1080p():
    """1904x1072 (multiples of 16) used to ship as 1904x1070."""
    from interfaces.delivery import plan_delivery

    assert plan_delivery(1904, 1072, "16:9").size == (1920, 1080)


def test_the_snap_never_goes_down_a_rung():
    """A 1920x1080 master ordered vertical fits 608x1080. 480x854 is a rung it
    could 'reach', and snapping there would throw away a fifth of the picture
    that was actually generated."""
    from interfaces.delivery import plan_delivery

    assert plan_delivery(1920, 1080, "9:16").size == (608, 1080)


def test_a_genuinely_smaller_render_is_never_inflated():
    """The no-upscaling rule is the point; the ladder is its last 5%."""
    from interfaces.delivery import plan_delivery

    # 40% short of 720p vertical -- nowhere near a rung.
    assert plan_delivery(768, 1344, "9:16").size == (756, 1344)
    assert plan_delivery(1280, 720, "16:9").size == (1280, 720)


@pytest.mark.parametrize("ratio", ["16:9", "9:16", "1:1"])
def test_every_rung_is_even_and_on_ratio(ratio):
    from interfaces.delivery import DELIVERY_LADDER

    wanted = {"16:9": 16 / 9, "9:16": 9 / 16, "1:1": 1.0}[ratio]
    for width, height in DELIVERY_LADDER[ratio]:
        assert width % 2 == 0 and height % 2 == 0, "yuv420p refuses odd sides"
        assert abs(width / height - wanted) / wanted < 0.001


def test_ratios_we_do_not_deliver_are_left_alone():
    from interfaces.delivery import plan_delivery

    assert plan_delivery(1920, 1080, "4:3") is None
    assert plan_delivery(1920, 1080, "") is None


# --- tiers ---------------------------------------------------------------


def test_the_default_tier_never_upscales(monkeypatch):
    """Every job that ever ran took this path, and it does not change."""
    from interfaces.delivery import DEFAULT_TIER, plan_delivery

    monkeypatch.delenv("MUSEFORGE_DELIVERY_TIER", raising=False)
    delivery = plan_delivery(1280, 720, "16:9", tier=DEFAULT_TIER)

    assert delivery.size == (1280, 720)
    assert delivery.upscaled is False


def test_four_k_is_delivered_and_declared():
    """A 4K order gets a real 3840x2160 file AND says where the pixels came
    from. The market sells upscaled 4K; the record may not pretend the render
    was 4K."""
    from interfaces.delivery import plan_delivery

    delivery = plan_delivery(1920, 1080, "16:9", tier="4k")

    assert delivery.size == (3840, 2160)
    assert delivery.upscaled is True
    assert delivery.as_dict()["rendered_width"] == 1920
    assert delivery.as_dict()["rendered_height"] == 1080


def test_four_k_out_of_a_four_k_render_is_not_called_an_upscale():
    from interfaces.delivery import plan_delivery

    assert plan_delivery(3840, 2160, "16:9", tier="4k").upscaled is False


def test_a_ladder_snap_is_not_reported_as_an_upscale():
    """1276 -> 1280 adds 0.3% of width. Calling that 'upscaled' would make the
    flag useless for the case it exists for."""
    from interfaces.delivery import plan_delivery

    assert plan_delivery(1276, 718, "16:9").upscaled is False


def test_a_lower_tier_is_a_real_downscale():
    from interfaces.delivery import plan_delivery

    delivery = plan_delivery(1920, 1080, "16:9", tier="720p")

    assert delivery.size == (1280, 720)
    assert delivery.upscaled is False


def test_vertical_four_k_is_vertical():
    from interfaces.delivery import plan_delivery

    assert plan_delivery(1080, 1920, "9:16", tier="4k").size == (2160, 3840)


def test_a_paid_tier_asked_for_by_a_plan_that_lacks_it_degrades(monkeypatch):
    """Same shape as music and dialogue: the drama still ships, at the size
    the plan bought, instead of erroring."""
    from interfaces.delivery import DEFAULT_TIER, resolve_tier

    monkeypatch.delenv("MUSEFORGE_DELIVERY_TIER", raising=False)
    assert resolve_tier("4k", "free") == DEFAULT_TIER
    assert resolve_tier("4k", "creator") == DEFAULT_TIER
    assert resolve_tier("4k", "pro") == "4k"
    # A free tier is free for everyone.
    assert resolve_tier("720p", "free") == "720p"


def test_the_deployment_default_is_read_from_the_environment(monkeypatch):
    from interfaces.delivery import resolve_tier

    monkeypatch.setenv("MUSEFORGE_DELIVERY_TIER", "720p")
    assert resolve_tier("", "free") == "720p"
    # An explicit request still wins over it.
    assert resolve_tier("1080p", "free") == "1080p"


def test_an_unknown_tier_is_not_silently_honoured(monkeypatch):
    from interfaces.delivery import DEFAULT_TIER, normalize_tier, resolve_tier

    monkeypatch.delenv("MUSEFORGE_DELIVERY_TIER", raising=False)
    assert normalize_tier("cinema") == ""
    assert resolve_tier("cinema", "pro") == DEFAULT_TIER
    # ...but the spellings people really type are understood.
    assert normalize_tier("2160p") == "4k"
    assert normalize_tier("UHD") == "4k"


def test_exact_resolution_still_forces_the_canonical_size(monkeypatch):
    from interfaces.delivery import plan_delivery

    assert plan_delivery(768, 1344, "9:16", force=True).size == (1080, 1920)


# --- what the encode is told ---------------------------------------------


def test_an_upscale_asks_for_lanczos_and_a_downscale_is_left_alone():
    """ffmpeg's default softens an upscale exactly where an upscale has the
    least detail to spare. A downscale keeps the filter string every existing
    delivery already used."""
    from pipelines.script2video import build_geometry_filters

    up = build_geometry_filters(1920, 1080, "16:9", tier="4k")
    assert "scale=3840:2160" in up[0]
    assert "flags=lanczos" in up[0]

    down = build_geometry_filters(1920, 1080, "16:9", tier="720p")
    assert down[0] == "scale=1280:720:force_original_aspect_ratio=increase"


def test_a_master_already_at_its_tier_is_not_re_encoded_for_geometry():
    from pipelines.script2video import build_geometry_filters

    assert build_geometry_filters(1080, 1920, "9:16") == []


def test_the_delivery_filters_report_the_size_that_will_ship():
    from pipelines.script2video import build_delivery_filters

    _filters, size = build_delivery_filters(
        1920, 1080, director_style="cinematic_balanced", aspect_ratio="16:9", tier="4k"
    )

    assert size == (3840, 2160)


# --- the job's own record -------------------------------------------------


def test_the_request_rejects_a_tier_we_do_not_deliver():
    import pydantic

    from api import GenerateRequest

    assert GenerateRequest(idea="a brand film").delivery_tier == ""
    assert GenerateRequest(idea="idea", delivery_tier="4k").delivery_tier == "4k"
    with pytest.raises(pydantic.ValidationError):
        GenerateRequest(idea="idea", delivery_tier="8k")


def test_the_job_carries_the_tier_it_was_sold():
    from jobs import Job

    job = Job(id="j1", delivery_tier="4k")

    assert job.to_dict(include_events=False)["delivery_tier"] == "4k"
