"""Job 21a87c5a: "extreme close-up on Mira's eyes and mouth" came back as a
full-body shot with her eyes on the lens.

The one-step reference-to-video call is given a portrait and the EMPTY wide
plate as references, and the plate's framing wins. Measured on fal: the same
shot started from a Nano Banana frame (portrait + plate, close-up asked of the
IMAGE model) and then animated kept the scar, the hut and an off-lens gaze.
So a close-up starts from a frame, even where every other shot is
reference-only.
"""
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")

from pipelines.script2video import wants_first_frame  # noqa: E402
from tools import falai_minimax_video_generator as mm  # noqa: E402

CAPABLE = SimpleNamespace(can_start_from_frame=True)
ONE_STEP_ONLY = SimpleNamespace()


def _shot(kind):
    return SimpleNamespace(shot_type=kind)


def test_a_close_up_starts_from_a_frame(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_CLOSEUP_FIRST_FRAME", raising=False)
    for kind in ("close-up", "Extreme close-up", "medium close-up", "close up"):
        assert wants_first_frame(_shot(kind), CAPABLE), kind


def test_a_wide_shot_stays_reference_only(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_CLOSEUP_FIRST_FRAME", raising=False)
    for kind in ("wide shot", "medium shot", "", "over-the-shoulder"):
        assert not wants_first_frame(_shot(kind), CAPABLE), kind


def test_a_backend_that_cannot_take_a_frame_is_left_alone(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_CLOSEUP_FIRST_FRAME", raising=False)
    assert not wants_first_frame(_shot("close-up"), ONE_STEP_ONLY)


def test_the_extra_frame_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_CLOSEUP_FIRST_FRAME", "0")
    assert not wants_first_frame(_shot("close-up"), CAPABLE)


def test_a_per_shot_frame_beats_a_reference_only_deployment(monkeypatch):
    monkeypatch.setenv("FALAI_MINIMAX_MODE", "reference")
    sent = {}

    async def fake_generate(client, endpoint, payload, is_cancelled=None):
        sent.update(payload)
        return {"video": {"url": "https://example.com/v.mp4"}}

    monkeypatch.setattr(mm, "fal_generate", fake_generate)
    gen = mm.FalAIMiniMaxVideoGenerator("k")
    assert gen.can_start_from_frame is True

    asyncio.run(
        gen.generate_video_from_image(
            "p", "https://example.com/frame.png", 4,
            reference_images=["https://example.com/portrait.png"],
            reference_labels=["Mira"],
            by_reference=False,
        )
    )
    assert sent["image_url"] == "https://example.com/frame.png"
    assert sent["reference_image_urls"] == ["https://example.com/portrait.png"]

    sent.clear()
    asyncio.run(gen.generate_video_from_image("p", "https://example.com/portrait.png", 4))
    assert "image_url" not in sent
    assert sent["reference_image_urls"] == ["https://example.com/portrait.png"]
