"""fal.ai Vidu Q4 reference-to-video provider.

Present so Vidu can be measured against Kling on the same shot, not because it
has been shown better. What is pinned here is the wire shape (confirmed against
fal's OpenAPI) and the ways a deployment could select it wrongly.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


def test_factory_returns_the_vidu_generator(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_vidu")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import _make_video_generator
    from tools.falai_vidu_video_generator import FalAIViduVideoGenerator

    gen = _make_video_generator("test-key", demo=False)
    assert isinstance(gen, FalAIViduVideoGenerator)
    assert gen.uses_character_reference_to_video is True


def test_the_selector_is_normalised_like_every_other_value(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", " Falai_Vidu\n")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import _make_video_generator
    from tools.falai_vidu_video_generator import FalAIViduVideoGenerator

    assert isinstance(_make_video_generator("k", demo=False), FalAIViduVideoGenerator)


def test_vidu_is_not_a_one_take_backend(monkeypatch):
    """No cut control in its schema, so the estimate must not price a take the
    render will not make."""
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_vidu")
    from pipelines.script2video import configured_scene_take_backend

    assert configured_scene_take_backend() is None


def test_existing_selectors_are_untouched(monkeypatch):
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import VIDEO_PROVIDERS, _make_video_generator
    from tools.falai_reference_video_generator import FalAIReferenceVideoGenerator

    assert VIDEO_PROVIDERS[:4] == ("muapi", "falai", "falai_reference", "falai_multishot")
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_reference")
    assert isinstance(_make_video_generator("k", demo=False), FalAIReferenceVideoGenerator)


async def _call(monkeypatch, **kwargs):
    import tools.falai_vidu_video_generator as mod

    captured = {}

    async def fake_fal_generate(client, endpoint, arguments, **_kwargs):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {"video": {"url": "https://fal.media/vidu.mp4"}}

    monkeypatch.setattr(mod, "fal_generate", fake_fal_generate)
    gen = mod.FalAIViduVideoGenerator(api_key="k", demo=False)
    image_url = kwargs.pop("image_url", "https://example.com/portrait.png")
    url = await gen.generate_video_from_image(image_url=image_url, **kwargs)
    return url, captured


@pytest.mark.asyncio
async def test_payload_matches_the_confirmed_schema(monkeypatch):
    monkeypatch.delenv("FALAI_VIDU_RESOLUTION", raising=False)
    monkeypatch.delenv("FALAI_VIDU_VIDEO_MODEL", raising=False)
    url, captured = await _call(
        monkeypatch, prompt="walks toward the camera", duration=8, aspect_ratio="9:16"
    )
    assert url == "https://fal.media/vidu.mp4"
    assert captured["endpoint"] == "fal-ai/vidu/q4/reference-to-video"
    args = captured["arguments"]
    assert args["prompt"] == "[@reference_image_1] walks toward the camera"
    assert args["reference_image_urls"] == ["https://example.com/portrait.png"]
    # An INTEGER, unlike Kling's string enum -- sending "8" is a 422.
    assert args["duration"] == 8 and isinstance(args["duration"], int)
    assert args["aspect_ratio"] == "9:16"
    assert args["resolution"] == "720p"
    # The dialogue is voiced and mixed afterwards; a model track would double it.
    assert "audio" not in args
    # The fields of the OTHER providers' schemas must not leak in.
    assert "elements" not in args and "image_url" not in args


@pytest.mark.asyncio
async def test_duration_is_clamped_to_what_the_endpoint_takes(monkeypatch):
    _, low = await _call(monkeypatch, prompt="p", duration=1)
    _, high = await _call(monkeypatch, prompt="p", duration=40)
    assert low["arguments"]["duration"] == 3
    assert high["arguments"]["duration"] == 16


@pytest.mark.asyncio
async def test_square_is_a_ratio_this_endpoint_accepts_and_an_odd_one_is_not_sent(monkeypatch):
    _, square = await _call(monkeypatch, prompt="p", aspect_ratio="1:1")
    _, odd = await _call(monkeypatch, prompt="p", aspect_ratio="21:9")
    assert square["arguments"]["aspect_ratio"] == "1:1"
    assert odd["arguments"]["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_resolution_is_configurable_and_a_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("FALAI_VIDU_RESOLUTION", "1080P")
    _, ok = await _call(monkeypatch, prompt="p")
    monkeypatch.setenv("FALAI_VIDU_RESOLUTION", "8k")
    _, bad = await _call(monkeypatch, prompt="p")
    assert ok["arguments"]["resolution"] == "1080p"
    # An unknown value would be a 422 on every shot of every job.
    assert bad["arguments"]["resolution"] == "720p"


@pytest.mark.asyncio
async def test_a_long_prompt_is_cut_to_the_schema_limit(monkeypatch):
    _, captured = await _call(monkeypatch, prompt="x" * 9000)
    assert len(captured["arguments"]["prompt"]) == 5000


@pytest.mark.asyncio
async def test_the_acted_peak_is_accepted_and_ignored(monkeypatch):
    """The schema has no end frame; the pipeline may still pass one."""
    _, captured = await _call(monkeypatch, prompt="p", last_image="https://x/peak.png")
    assert "end_image_url" not in captured["arguments"]
    assert "https://x/peak.png" not in str(captured["arguments"])


@pytest.mark.asyncio
async def test_the_endpoint_can_be_overridden(monkeypatch):
    monkeypatch.setenv("FALAI_VIDU_VIDEO_MODEL", "fal-ai/vidu/q5/reference-to-video")
    _, captured = await _call(monkeypatch, prompt="p")
    assert captured["endpoint"] == "fal-ai/vidu/q5/reference-to-video"


@pytest.mark.asyncio
async def test_a_result_without_a_video_raises(monkeypatch):
    import tools.falai_vidu_video_generator as mod

    async def empty(*a, **k):
        return {"cover_image": {"url": "https://x/c.jpg"}}

    monkeypatch.setattr(mod, "fal_generate", empty)
    gen = mod.FalAIViduVideoGenerator(api_key="k", demo=False)
    with pytest.raises(RuntimeError, match="no video URL"):
        await gen.generate_video_from_image("p", "https://x/portrait.png")


@pytest.mark.asyncio
async def test_demo_mode_skips_the_network():
    from tools.falai_reference_video_generator import DEMO_VIDEO_URL
    from tools.falai_vidu_video_generator import FalAIViduVideoGenerator

    gen = FalAIViduVideoGenerator(api_key="", demo=True)
    assert await gen.generate_video_from_image("p", "https://x") == DEMO_VIDEO_URL


# ── the whole cast, not just the anchor ──────────────────────────────────────
# Job 79a25db0 sent Vidu one portrait for a two-hander: the woman was topknotted
# in one scene and shaven in the next, the man silver-haired and then bald.


@pytest.mark.asyncio
async def test_the_whole_set_is_bound_and_each_picture_is_named(monkeypatch):
    _, captured = await _call(
        monkeypatch,
        prompt="she studies his hand",
        image_url="https://x/mara.png",
        reference_images=["https://x/mara.png", "https://x/victor.png", "https://x/set.png"],
        reference_labels=["Mara", "Victor", "the empty set"],
    )
    args = captured["arguments"]
    assert args["reference_image_urls"] == [
        "https://x/mara.png",
        "https://x/victor.png",
        "https://x/set.png",
    ]
    assert args["prompt"] == (
        "[@reference_image_1] is Mara. [@reference_image_2] is Victor. "
        "[@reference_image_3] is the empty set. she studies his hand"
    )


@pytest.mark.asyncio
async def test_without_a_set_the_call_is_the_single_portrait_it_was(monkeypatch):
    _, captured = await _call(monkeypatch, prompt="p")
    assert captured["arguments"]["reference_image_urls"] == ["https://example.com/portrait.png"]
    assert captured["arguments"]["prompt"] == "[@reference_image_1] p"


@pytest.mark.asyncio
async def test_a_duplicate_picture_does_not_hand_one_face_anothers_name(monkeypatch):
    _, captured = await _call(
        monkeypatch,
        prompt="p",
        image_url="https://x/a.png",
        reference_images=["https://x/a.png", "https://x/a.png", "https://x/b.png"],
        reference_labels=["Ana", "Ana", "Ben"],
    )
    args = captured["arguments"]
    assert args["reference_image_urls"] == ["https://x/a.png", "https://x/b.png"]
    assert args["prompt"].startswith("[@reference_image_1] is Ana. [@reference_image_2] is Ben.")


@pytest.mark.asyncio
async def test_the_shots_own_reference_leads_even_when_the_set_omits_it(monkeypatch):
    _, captured = await _call(
        monkeypatch,
        prompt="p",
        reference_images=["https://x/other.png"],
        reference_labels=["Other"],
    )
    assert captured["arguments"]["reference_image_urls"][0] == "https://example.com/portrait.png"
    assert "[@reference_image_2] is Other." in captured["arguments"]["prompt"]


@pytest.mark.asyncio
async def test_the_set_is_capped_at_what_the_endpoint_reads(monkeypatch):
    many = [f"https://x/{i}.png" for i in range(20)]
    _, captured = await _call(monkeypatch, prompt="p", reference_images=many)
    assert len(captured["arguments"]["reference_image_urls"]) == 12


def test_the_generator_declares_that_it_takes_a_set():
    from tools.falai_vidu_video_generator import FalAIViduVideoGenerator
    from tools.falai_reference_video_generator import FalAIReferenceVideoGenerator

    assert FalAIViduVideoGenerator.accepts_reference_set is True
    # The Kling reference provider takes one image; it must not be handed more.
    assert not getattr(FalAIReferenceVideoGenerator, "accepts_reference_set", False)


# ── labelling the set ────────────────────────────────────────────────────────


def _cast():
    from interfaces.character import CharacterInScene

    return [
        CharacterInScene(idx=0, name="Mara", static_features="woman, thirties"),
        CharacterInScene(idx=1, name="Victor", static_features="man, sixties"),
    ]


def _shot(text):
    from interfaces.shot import StoryboardShot

    return StoryboardShot(idx=0, visual_desc=text, motion_desc="hold", shot_type="medium")


PORTRAITS = {"Mara": "https://x/mara.png", "Victor": "https://x/victor.png"}


def test_labels_follow_the_set_in_order():
    from pipelines.script2video import label_frame_references

    cast = _cast()
    labels = label_frame_references(
        ["https://x/mara.png", "https://x/victor.png", "https://x/set.png"],
        _shot("Mara studies Victor across the table"),
        cast,
        PORTRAITS,
        matched_char=cast[0],
        location_plate_url="https://x/set.png",
    )
    assert labels == ["Mara", "Victor", "the empty set"]


def test_a_dynamic_anchor_is_still_named_after_its_character():
    """With dynamic references on, the anchor is the latest frame -- nobody's
    portrait -- and must not come out unlabelled."""
    from pipelines.script2video import label_frame_references

    cast = _cast()
    labels = label_frame_references(
        ["https://x/last-frame.png", "https://x/victor.png"],
        _shot("Mara studies Victor"),
        cast,
        PORTRAITS,
        matched_char=cast[0],
    )
    assert labels == ["Mara", "Victor"]


def test_an_establishing_shot_labels_only_the_set():
    from pipelines.script2video import label_frame_references

    labels = label_frame_references(
        ["https://x/set.png"],
        _shot("the basement, empty"),
        _cast(),
        PORTRAITS,
        matched_char=None,
        location_plate_url="https://x/set.png",
    )
    assert labels == ["the empty set"]


# ── through the pipeline ─────────────────────────────────────────────────────


class _OneStepGenerator:
    uses_character_reference_to_video = True

    def __init__(self, accepts):
        self.calls = []
        if accepts:
            self.accepts_reference_set = True

    async def generate_video_from_image(self, prompt, image_url, duration=5, aspect_ratio="16:9",
                                        plan="free", is_cancelled=None, shot_profile=None, **kwargs):
        self.calls.append({"image_url": image_url, "kwargs": kwargs})
        return "https://fake.cdn/shot.mp4"


async def _run_two_hander(monkeypatch, tmp_path, generator):
    import agents.storyboard_artist as sb_mod
    import pipelines.script2video as s2v_mod
    from pipelines.script2video import Script2VideoPipeline

    async def fake_design(self, *a, **k):
        return [_shot("Mara studies Victor across the table")]

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(path, "wb").write(b"fake")
        return path

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)
    pipeline = Script2VideoPipeline(api_key="k", demo=False)
    pipeline.video_gen = generator
    await pipeline.run(
        script="Mara studies Victor.",
        characters=_cast(),
        working_dir=str(tmp_path),
        character_portraits=PORTRAITS,
        location_plate_url="https://x/set.png",
        scene_duration=6,
    )


@pytest.mark.asyncio
async def test_a_two_hander_hands_the_backend_both_faces_and_the_set(monkeypatch, tmp_path):
    generator = _OneStepGenerator(accepts=True)
    await _run_two_hander(monkeypatch, tmp_path, generator)
    kwargs = generator.calls[0]["kwargs"]
    assert kwargs["reference_images"] == [
        "https://x/mara.png",
        "https://x/victor.png",
        "https://x/set.png",
    ]
    assert kwargs["reference_labels"] == ["Mara", "Victor", "the empty set"]
    assert generator.calls[0]["image_url"] == "https://x/mara.png"


@pytest.mark.asyncio
async def test_a_backend_that_takes_one_reference_is_not_handed_more(monkeypatch, tmp_path):
    """The call site is duck-typed: an undeclared backend must see exactly the
    keywords it saw before, or it TypeErrors on every shot."""
    generator = _OneStepGenerator(accepts=False)
    await _run_two_hander(monkeypatch, tmp_path, generator)
    assert "reference_images" not in generator.calls[0]["kwargs"]
    assert "reference_labels" not in generator.calls[0]["kwargs"]
