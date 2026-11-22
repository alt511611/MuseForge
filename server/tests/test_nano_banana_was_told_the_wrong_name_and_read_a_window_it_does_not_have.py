"""Four things the adversarial review of PR #160 (falai_nanobanana) proved.

1. The legend named the wrong person. ``label_frame_references`` gave slot 0
   the anchor's name unconditionally, so when the anchor had no portrait the set
   opened with somebody else's face (or the empty plate) and the model was told
   "Image 1 is <the anchor>". A blank or repeated URL did the same to every
   label after it, because labels were indexed against the raw list while the
   backend sends the normalised one. A wrong name is worse than none.
2. The prompt was cut to a 512-token window Nano Banana does not have (fal's
   schema: ``prompt`` maxLength 50,000), dropping wardrobes, the lighting lock
   and the face/cast guardrails on a six-character scene.
3. A text-only answer (Gemini's refusal) was a plain RuntimeError, so the one
   resubmit that exists for content flags never ran.
4. The Gemini family logged "the T5 tokenizer did not load" on every frame.
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

import tools.falai_image_generator as g  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    build_frame_prompt,
    label_frame_references,
    resolve_frame_references,
)
from tools.falai_common import ContentFlagged  # noqa: E402

PLATE = "http://x/plate.jpg"


def _char(i, name):
    return CharacterInScene(
        idx=i, name=name, static_features="a man", is_visible=True, wardrobe="coat"
    )


def _shot(text="Yusuf looks at Mara across the quay"):
    return StoryboardShot(
        idx=0, visual_desc=text, motion_desc="push in", expression_desc="calm",
        shot_type="medium", lens="35mm",
    )


def _labels(portraits, plate=PLATE):
    chars = [_char(0, "Yusuf"), _char(1, "Mara")]
    shot = _shot()
    matched, _anchor, refs = resolve_frame_references(
        shot, chars, portraits, location_plate_url=plate
    )
    return refs, label_frame_references(
        refs, shot, chars, portraits, matched_char=matched, location_plate_url=plate
    )


def test_the_ordinary_set_is_labelled_in_order():
    refs, labels = _labels({"Yusuf": "http://x/y.jpg", "Mara": "http://x/m.jpg"})
    assert labels == ["Yusuf", "Mara", "the empty set"]


def test_another_characters_face_in_slot_zero_is_not_named_for_the_anchor():
    refs, labels = _labels({"Mara": "http://x/m.jpg"})
    assert refs[0] == "http://x/m.jpg"
    assert labels == ["Mara", "the empty set"]


def test_a_plate_alone_is_not_named_for_a_person():
    refs, labels = _labels({})
    assert refs == [PLATE]
    assert labels == ["the empty set"]


def test_a_blank_portrait_url_does_not_shift_the_labels():
    refs, labels = _labels({"Yusuf": "http://x/y.jpg", "Mara": "  "})
    # what a backend sends: the blank entry is gone
    assert labels == ["Yusuf", "the empty set"]


def _run(coro):
    return asyncio.run(coro)


def _generator(monkeypatch, results):
    calls = []

    async def fake(client, endpoint, payload, **kw):
        calls.append(payload)
        return results.pop(0) if len(results) > 1 else results[0]

    monkeypatch.setattr(g, "fal_generate", fake)
    return g.FalAIImageGenerator("k", nanobanana=True), calls


def test_the_generator_pairs_labels_with_urls_before_it_drops_any(monkeypatch):
    gen, calls = _generator(monkeypatch, [{"images": [{"url": "u"}]}])
    _run(gen.generate_image_with_reference(
        "p", ["http://a/1", "  ", "http://a/2"], "9:16",
        reference_labels=["A", "ghost", "B"],
    ))
    assert calls[0]["image_urls"] == ["http://a/1", "http://a/2"]
    assert calls[0]["prompt"].startswith("Image 1 is A. Image 2 is B.")


def test_labels_that_cannot_be_paired_send_no_legend(monkeypatch):
    gen, calls = _generator(monkeypatch, [{"images": [{"url": "u"}]}])
    _run(gen.generate_image_with_reference(
        "p", ["http://a/1", "http://a/2"], "16:9", reference_labels=["only one"],
    ))
    assert calls[0]["prompt"] == "p"


def test_a_text_only_answer_is_resubmitted_once(monkeypatch):
    gen, calls = _generator(
        monkeypatch,
        [{"images": [], "description": "I can't do that."}, {"images": [{"url": "ok"}]}],
    )
    assert _run(gen.generate_image_with_reference("p", ["http://a/1"])) == "ok"
    assert len(calls) == 2


def test_a_second_refusal_is_a_content_flag_with_the_reason(monkeypatch):
    gen, calls = _generator(
        monkeypatch, [{"images": [], "description": "Blocked by safety."}]
    )
    with pytest.raises(ContentFlagged, match="Blocked by safety"):
        _run(gen.generate_image_with_reference("p", ["http://a/1"]))
    assert len(calls) == 2


def _heavy_prompt():
    chars = [
        CharacterInScene(
            idx=i, name=f"Character{i}", is_visible=True,
            static_features=(
                "a woman in her early thirties, sharp cheekbones, dark hair pulled "
                "back in a wet knot, tired grey eyes, lean build, a faded scar"
            ),
            wardrobe="a soaked navy dock parka over a charcoal sweater, steel-toed boots",
        )
        for i in range(6)
    ]
    shot = StoryboardShot(
        idx=0, visual_desc="She cuts the seal " + "under the sodium lamp " * 60,
        motion_desc="slow push in", expression_desc="jaw set, eyes narrowed",
        shot_type="medium", lens="35mm",
    )
    return build_frame_prompt(
        style="Sci-Fi", shot=shot,
        setting_location="a rain-soaked cargo harbour, container stacks under gantry cranes, "
        "wet asphalt, sodium floodlights, a customs shed with lit windows, mooring bollards",
        setting_time_of_day="night", setting_era="present day", has_dialogue=True,
        lipsync_enabled=True, characters=chars, matched_char=chars[0], has_reference=True,
    )


def test_nano_banana_keeps_the_guardrails_a_512_window_would_have_cut(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_nanobanana")
    prompt = _heavy_prompt()
    assert "Cast is closed" in prompt
    assert "lit and readable, not a silhouette" in prompt
    assert "Lighting continuity" in prompt


def test_flux_2_is_still_held_to_its_real_window(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_multiref")
    prompt = _heavy_prompt()
    assert "Lighting continuity" not in prompt


def test_gemini_does_not_log_that_the_t5_tokenizer_failed(monkeypatch, caplog):
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_nanobanana")
    with caplog.at_level(logging.WARNING):
        _heavy_prompt()
    assert "T5 tokenizer did not load" not in caplog.text
