"""MUSEFORGE_IMAGE_PROVIDER=falai_nanobanana.

Two failures this answers, both measured on 2026-11-22:

* The multi-reference frame step (flux-2-pro/edit) drew two men from three
  portraits and a set in one run of two, and lost the one character's headband
  in the other. In a blind test of 18 frames on three hard shots Nano Banana 2.1
  scored 4.6 against Kling O1 Image's 2.5, and every one of its frames beat every
  one of Kling's.
* flux-pro/v1.1 draws a portrait sheet as an illustration however firmly the
  prompt says PHOTOGRAPH; FLUX.3 draws photographs.

Nano Banana addresses its references by position in the PROMPT, so the pipeline
now says who each picture is -- but only to a backend that declares it reads the
labels; every other provider is called exactly as it was.
"""
import logging
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tools.falai_image_generator as mod
from tools import t5_budget
from tools.falai_image_generator import FalAIImageGenerator

REFS = ["https://x/yusuf.jpg", "https://x/deniz.jpg", "https://x/set.png"]
LABELS = ["Yusuf", "Deniz", "the empty set"]


@pytest.fixture
def calls(monkeypatch):
    seen = []

    async def fake(client, endpoint, arguments, **kwargs):
        seen.append((endpoint, arguments))
        return {"images": [{"url": "https://fal/out.jpg"}]}

    monkeypatch.setattr(mod, "fal_generate", fake)
    return seen


def _gen(**kw):
    return FalAIImageGenerator("key", **kw)


# ── selection ────────────────────────────────────────────────────────────────


def test_the_provider_is_selectable_and_reads_the_whole_set(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_nanobanana")
    monkeypatch.setenv("FAL_KEY", "k")
    from pipelines.script2video import _make_image_generator

    generator = _make_image_generator("k", demo=False)
    assert isinstance(generator, FalAIImageGenerator)
    assert generator.nanobanana is True
    assert generator.multiref is True  # nothing is ever held back to one picture


def test_the_older_providers_are_unchanged(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "k")
    assert _gen().nanobanana is False
    assert _gen(multiref=True).nanobanana is False
    assert _gen().accepts_reference_labels is False
    assert _gen(multiref=True).accepts_reference_labels is False
    assert _gen(nanobanana=True).accepts_reference_labels is True


# ── the frame ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_frame_sends_every_reference_to_nano_banana(calls):
    url = await _gen(nanobanana=True).generate_image_with_reference(
        "three men on a boat", REFS, "16:9", reference_labels=LABELS
    )
    endpoint, args = calls[0]
    assert url == "https://fal/out.jpg"
    assert endpoint == "google/nano-banana-2.1/edit"
    assert args["image_urls"] == REFS
    assert args["aspect_ratio"] == "16:9"
    assert args["resolution"] == "1K"
    assert args["thinking_level"] == "medium"  # high scored the same, slower
    assert "image_size" not in args and "image_url" not in args


@pytest.mark.asyncio
async def test_each_picture_is_named_by_its_position(calls):
    await _gen(nanobanana=True).generate_image_with_reference(
        "three men on a boat", REFS, "16:9", reference_labels=LABELS
    )
    prompt = calls[0][1]["prompt"]
    assert prompt.startswith("Image 1 is Yusuf. Image 2 is Deniz. Image 3 is the empty set.")
    assert prompt.endswith("three men on a boat")


@pytest.mark.asyncio
async def test_a_picture_nothing_names_is_left_out_of_the_legend(calls):
    await _gen(nanobanana=True).generate_image_with_reference(
        "x", REFS, "16:9", reference_labels=["Yusuf", "", "the empty set"]
    )
    assert calls[0][1]["prompt"].startswith("Image 1 is Yusuf. Image 3 is the empty set.")


@pytest.mark.asyncio
async def test_no_labels_means_the_prompt_goes_out_as_it_was(calls):
    await _gen(nanobanana=True).generate_image_with_reference("just words", REFS, "16:9")
    assert calls[0][1]["prompt"] == "just words"


@pytest.mark.asyncio
async def test_more_than_fourteen_references_are_capped_and_said_so(calls, caplog):
    many = [f"https://x/{i}.jpg" for i in range(17)]
    with caplog.at_level(logging.WARNING):
        await _gen(nanobanana=True).generate_image_with_reference("x", many, "16:9")
    assert calls[0][1]["image_urls"] == many[:14]
    assert "holding back the last 3 of 17" in caplog.text


@pytest.mark.asyncio
async def test_an_aspect_ratio_it_does_not_know_falls_back_instead_of_422ing(calls):
    await _gen(nanobanana=True).generate_image_with_reference("x", REFS, "7:3")
    assert calls[0][1]["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_the_environment_can_raise_thinking_and_resolution(calls, monkeypatch):
    monkeypatch.setenv("FALAI_NANOBANANA_THINKING", "HIGH")
    monkeypatch.setenv("FALAI_NANOBANANA_RESOLUTION", "2k")
    await _gen(nanobanana=True).generate_image_with_reference("x", REFS, "16:9")
    assert calls[0][1]["thinking_level"] == "high"
    assert calls[0][1]["resolution"] == "2K"


@pytest.mark.asyncio
async def test_an_unknown_setting_falls_back_to_the_default(calls, monkeypatch):
    monkeypatch.setenv("FALAI_NANOBANANA_THINKING", "ludicrous")
    monkeypatch.setenv("FALAI_NANOBANANA_RESOLUTION", "8K")
    await _gen(nanobanana=True).generate_image_with_reference("x", REFS, "16:9")
    assert calls[0][1]["thinking_level"] == "medium"
    assert calls[0][1]["resolution"] == "1K"


@pytest.mark.asyncio
async def test_without_references_it_is_a_text_to_image_call(calls):
    await _gen(nanobanana=True).generate_image_with_reference("an empty shore", [], "16:9")
    assert calls[0][0] == "blackforestlabs/flux-3/text-to-image"


# ── the sheet ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_portrait_sheet_is_drawn_by_flux_3_in_its_own_schema(calls):
    await _gen(nanobanana=True).generate_image("a 2x2 character sheet", "1:1")
    endpoint, args = calls[0]
    assert endpoint == "blackforestlabs/flux-3/text-to-image"
    assert args == {
        "prompt": "a 2x2 character sheet",
        "aspect_ratio": "1:1",
        "resolution": "1k",
        "output_format": "jpeg",
    }


@pytest.mark.asyncio
async def test_an_operator_named_model_still_wins_for_text_to_image(calls, monkeypatch):
    monkeypatch.setenv("FALAI_IMAGE_MODEL", "fal-ai/flux-pro/v1.1")
    monkeypatch.setattr(FalAIImageGenerator, "TEXT_ENDPOINT", "fal-ai/flux-pro/v1.1")
    await _gen(nanobanana=True).generate_image("x", "1:1")
    endpoint, args = calls[0]
    assert endpoint == "fal-ai/flux-pro/v1.1"
    assert args["image_size"] == "square_hd" and "resolution" not in args


@pytest.mark.asyncio
async def test_the_other_providers_still_draw_with_flux_pro(calls):
    await _gen().generate_image("x", "1:1")
    assert calls[0][0] == "fal-ai/flux-pro/v1.1"
    assert calls[0][1]["image_size"] == "square_hd"


@pytest.mark.asyncio
async def test_demo_mode_never_touches_the_network():
    gen = FalAIImageGenerator("", demo=True, nanobanana=True)
    assert (await gen.generate_image("x", "1:1")).startswith("https://picsum.photos/")
    assert (await gen.generate_image_with_reference("x", REFS, "16:9", reference_labels=LABELS)).startswith(
        "https://picsum.photos/"
    )


# ── what the pipeline hands over ─────────────────────────────────────────────


def test_the_pipeline_sends_labels_only_to_a_backend_that_declares_it():
    from pipelines.script2video import _frame_label_kwargs

    anchor = SimpleNamespace(name="Mara")
    args = dict(
        frame_references=["https://x/mara_latest.jpg", "https://x/set.png"],
        shot=SimpleNamespace(visual_desc="Mara looks at the shore", motion_desc=""),
        characters=[anchor],
        portraits={},
        matched_char=anchor,
        location_plate_url="https://x/set.png",
    )
    declares = SimpleNamespace(accepts_reference_labels=True)
    assert _frame_label_kwargs(declares, **args) == {"reference_labels": ["Mara", "the empty set"]}
    assert _frame_label_kwargs(SimpleNamespace(), **args) == {}
    assert _frame_label_kwargs(SimpleNamespace(accepts_reference_labels=False), **args) == {}
    assert _frame_label_kwargs(declares, **{**args, "frame_references": []}) == {}


# ── the prompt budget ────────────────────────────────────────────────────────


def test_the_budget_knows_this_is_a_gemini_model_not_t5(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_nanobanana")
    assert t5_budget.encoder_family() == "gemini"
    assert t5_budget.window_label() == "Gemini"
    assert t5_budget.tokenizer_is_real() is False
    assert t5_budget.count_tokens("x" * 350) == int(350 / t5_budget.GEMINI_FALLBACK_CHARS_PER_TOKEN) + 1


def test_a_custom_nano_banana_model_is_still_recognised(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_nanobanana")
    monkeypatch.setenv("FALAI_NANOBANANA_EDIT_MODEL", "google/nano-banana-3/edit")
    assert t5_budget.encoder_family() == "gemini"


def test_the_other_families_are_not_disturbed(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_multiref")
    assert t5_budget.encoder_family() == "mistral"
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai")
    assert t5_budget.encoder_family() == "t5"
