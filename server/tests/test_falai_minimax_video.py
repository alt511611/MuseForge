"""fal.ai MiniMax H3 Max reference-to-video provider.

Present so H3 Max can be measured against Kling and Vidu on the same two-hander,
not because it has been shown better. It is the one schema that takes a first
frame, a last frame and a reference set in one call. What is pinned here is the
wire shape (confirmed against fal's OpenAPI) and the ways a deployment could
select or call it wrongly.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")

PORTRAIT = "https://example.com/portrait.png"
FRAME = "https://example.com/frame.png"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in (
        "FALAI_MINIMAX_MODE",
        "FALAI_MINIMAX_RESOLUTION",
        "FALAI_MINIMAX_PROMPT_EXPANSION",
        "FALAI_MINIMAX_VIDEO_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


# ── selection ────────────────────────────────────────────────────────────────


def test_factory_returns_the_minimax_generator(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_minimax")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import _make_video_generator
    from tools.falai_minimax_video_generator import FalAIMiniMaxVideoGenerator

    assert isinstance(_make_video_generator("k", demo=False), FalAIMiniMaxVideoGenerator)


def test_the_selector_is_normalised_like_every_other_value(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", " Falai_MiniMax\n")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    from pipelines.script2video import _make_video_generator
    from tools.falai_minimax_video_generator import FalAIMiniMaxVideoGenerator

    assert isinstance(_make_video_generator("k", demo=False), FalAIMiniMaxVideoGenerator)


def test_it_is_not_a_one_take_backend(monkeypatch):
    """No cut control in its schema, so the estimate must not price a take the
    render will not make."""
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_minimax")
    from pipelines.script2video import configured_scene_take_backend

    assert configured_scene_take_backend() is None


def test_existing_selectors_are_untouched():
    from pipelines.script2video import VIDEO_PROVIDERS

    assert VIDEO_PROVIDERS[:5] == (
        "muapi",
        "falai",
        "falai_reference",
        "falai_multishot",
        "falai_vidu",
    )
    assert VIDEO_PROVIDERS[-1] == "falai_minimax"


def test_the_default_mode_renders_the_opening_frame_first(monkeypatch):
    from tools.falai_minimax_video_generator import FalAIMiniMaxVideoGenerator

    gen = FalAIMiniMaxVideoGenerator(api_key="k", demo=True)
    assert gen.uses_character_reference_to_video is False
    monkeypatch.setenv("FALAI_MINIMAX_MODE", "reference")
    assert gen.uses_character_reference_to_video is True
    monkeypatch.setenv("FALAI_MINIMAX_MODE", "nonsense")
    assert gen.uses_character_reference_to_video is False


# ── the wire ─────────────────────────────────────────────────────────────────


async def _call(monkeypatch, **kwargs):
    import tools.falai_minimax_video_generator as mod

    captured = {}

    async def fake_fal_generate(client, endpoint, arguments, **_kwargs):
        captured["endpoint"] = endpoint
        captured["arguments"] = arguments
        return {"video": {"url": "https://fal.media/h3.mp4"}}

    monkeypatch.setattr(mod, "fal_generate", fake_fal_generate)
    gen = mod.FalAIMiniMaxVideoGenerator(api_key="k", demo=False)
    image_url = kwargs.pop("image_url", FRAME)
    url = await gen.generate_video_from_image(image_url=image_url, **kwargs)
    return url, captured


@pytest.mark.asyncio
async def test_frame_mode_sends_the_frame_as_the_first_frame_and_the_set_as_references(monkeypatch):
    url, captured = await _call(
        monkeypatch,
        prompt="walks toward the camera",
        duration=8,
        aspect_ratio="9:16",
        last_image="https://example.com/peak.png",
        reference_images=["https://x/mara.png", "https://x/victor.png", "https://x/set.png"],
        reference_labels=["Mara", "Victor", "the empty set"],
    )
    assert url == "https://fal.media/h3.mp4"
    assert captured["endpoint"] == "minimax/h3-max/reference-to-video"
    args = captured["arguments"]
    assert args["image_url"] == FRAME
    assert args["end_image_url"] == "https://example.com/peak.png"
    # The frame is NOT also a reference: it already opens the video.
    assert args["reference_image_urls"] == [
        "https://x/mara.png",
        "https://x/victor.png",
        "https://x/set.png",
    ]
    assert args["prompt"].startswith(
        "Image 1 is Mara. Image 2 is Victor. Image 3 is the empty set. walks"
    )
    assert args["aspect_ratio"] == "9:16"
    assert args["resolution"] == "768P"
    # A float, as the schema types it.
    assert args["duration"] == 8.0 and isinstance(args["duration"], float)


@pytest.mark.asyncio
async def test_prompt_expansion_is_always_sent_and_off_by_default(monkeypatch):
    """The field is REQUIRED by the schema, and a model free to rewrite the
    prompt is free to drop the clause that was holding a face."""
    _, captured = await _call(monkeypatch, prompt="p")
    assert captured["arguments"]["prompt_expansion_mode"] == "disabled"


@pytest.mark.asyncio
async def test_no_end_frame_is_sent_when_none_was_rendered(monkeypatch):
    _, captured = await _call(monkeypatch, prompt="p")
    assert "end_image_url" not in captured["arguments"]


@pytest.mark.asyncio
async def test_a_frame_with_no_reference_set_is_sent_on_its_own(monkeypatch):
    _, captured = await _call(monkeypatch, prompt="p")
    args = captured["arguments"]
    assert args["image_url"] == FRAME
    assert "reference_image_urls" not in args
    assert args["prompt"] == "p"


@pytest.mark.asyncio
async def test_reference_mode_has_no_first_frame_and_the_anchor_leads(monkeypatch):
    monkeypatch.setenv("FALAI_MINIMAX_MODE", "reference")
    _, captured = await _call(
        monkeypatch,
        prompt="p",
        image_url=PORTRAIT,
        reference_images=["https://x/victor.png", PORTRAIT],
        reference_labels=["Victor", "Mara"],
    )
    args = captured["arguments"]
    assert "image_url" not in args
    assert args["reference_image_urls"] == [PORTRAIT, "https://x/victor.png"]
    # Labels follow their pictures through the re-ordering and de-duplication.
    assert args["prompt"].startswith("Image 1 is Mara. Image 2 is Victor. p")


@pytest.mark.asyncio
async def test_reference_mode_with_no_labels_still_says_what_the_picture_is(monkeypatch):
    monkeypatch.setenv("FALAI_MINIMAX_MODE", "reference")
    _, captured = await _call(monkeypatch, prompt="walks", image_url=PORTRAIT)
    assert captured["arguments"]["prompt"] == "Image 1 is the character. walks"
    assert captured["arguments"]["reference_image_urls"] == [PORTRAIT]


@pytest.mark.asyncio
async def test_the_reference_list_stops_at_nine(monkeypatch):
    """fal's prose says 12, but that is the total across every kind of file;
    the image list alone stops at 9 and a tenth is a 422."""
    many = [f"https://x/{i}.png" for i in range(15)]
    _, captured = await _call(monkeypatch, prompt="p", reference_images=many)
    assert len(captured["arguments"]["reference_image_urls"]) == 9


@pytest.mark.asyncio
async def test_duration_is_clamped_to_what_the_endpoint_takes(monkeypatch):
    _, low = await _call(monkeypatch, prompt="p", duration=0)
    _, high = await _call(monkeypatch, prompt="p", duration=40)
    assert low["arguments"]["duration"] == pytest.approx(0.92)
    assert high["arguments"]["duration"] == 15.0


@pytest.mark.asyncio
async def test_an_odd_ratio_is_not_sent_and_adaptive_is_never_chosen(monkeypatch):
    _, ultra = await _call(monkeypatch, prompt="p", aspect_ratio="21:9")
    _, odd = await _call(monkeypatch, prompt="p", aspect_ratio="5:4")
    assert ultra["arguments"]["aspect_ratio"] == "21:9"
    assert odd["arguments"]["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_resolution_and_expansion_come_from_the_environment_or_fall_back(monkeypatch):
    monkeypatch.setenv("FALAI_MINIMAX_RESOLUTION", " 1080p ")
    monkeypatch.setenv("FALAI_MINIMAX_PROMPT_EXPANSION", "Quality")
    _, ok = await _call(monkeypatch, prompt="p")
    assert ok["arguments"]["resolution"] == "1080P"
    assert ok["arguments"]["prompt_expansion_mode"] == "quality"

    monkeypatch.setenv("FALAI_MINIMAX_RESOLUTION", "4k")
    monkeypatch.setenv("FALAI_MINIMAX_PROMPT_EXPANSION", "turbo")
    _, bad = await _call(monkeypatch, prompt="p")
    # An unknown value is a 422 on every shot of every job, so it is not sent.
    assert bad["arguments"]["resolution"] == "768P"
    assert bad["arguments"]["prompt_expansion_mode"] == "disabled"


@pytest.mark.asyncio
async def test_the_endpoint_can_be_overridden(monkeypatch):
    monkeypatch.setenv("FALAI_MINIMAX_VIDEO_MODEL", "minimax/h3/reference-to-video")
    _, captured = await _call(monkeypatch, prompt="p")
    assert captured["endpoint"] == "minimax/h3/reference-to-video"


@pytest.mark.asyncio
async def test_a_completion_with_no_video_is_an_error(monkeypatch):
    import tools.falai_minimax_video_generator as mod

    async def empty(*a, **k):
        return {"seed": 1}

    monkeypatch.setattr(mod, "fal_generate", empty)
    gen = mod.FalAIMiniMaxVideoGenerator(api_key="k", demo=False)
    with pytest.raises(RuntimeError, match="no video URL"):
        await gen.generate_video_from_image(prompt="p", image_url=FRAME)


@pytest.mark.asyncio
async def test_demo_mode_makes_no_call(monkeypatch):
    import tools.falai_minimax_video_generator as mod

    async def boom(*a, **k):
        raise AssertionError("demo must not reach fal")

    monkeypatch.setattr(mod, "fal_generate", boom)
    gen = mod.FalAIMiniMaxVideoGenerator(api_key="", demo=True)
    assert await gen.generate_video_from_image(prompt="p", image_url=FRAME) == mod.DEMO_VIDEO_URL


# ── through the pipeline ─────────────────────────────────────────────────────


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


class _Backend:
    def __init__(self, one_step, accepts):
        self.uses_character_reference_to_video = one_step
        self.calls = []
        if accepts:
            self.accepts_reference_set = True

    async def generate_video_from_image(self, prompt, image_url, duration=5, aspect_ratio="16:9",
                                        plan="free", is_cancelled=None, shot_profile=None, **kwargs):
        self.calls.append({"image_url": image_url, "kwargs": kwargs})
        return "https://fake.cdn/shot.mp4"


class _Images:
    def __init__(self):
        self.references = []

    async def generate_image(self, prompt, aspect_ratio="16:9", **_):
        return "https://x/frame.png"

    async def generate_image_with_reference(self, prompt, references, aspect_ratio="16:9", **_):
        self.references.append(list(references))
        return "https://x/frame.png"


async def _run(monkeypatch, tmp_path, backend):
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
    pipeline.video_gen = backend
    pipeline.image_gen = _Images()
    await pipeline.run(
        script="Mara studies Victor.",
        characters=_cast(),
        working_dir=str(tmp_path),
        character_portraits=PORTRAITS,
        location_plate_url="https://x/set.png",
        scene_duration=6,
    )
    return pipeline


@pytest.mark.asyncio
async def test_frame_mode_animates_the_rendered_frame_and_still_hands_over_the_set(monkeypatch, tmp_path):
    """A backend that takes a first frame AND references is owed the set: the
    frame is one picture of one moment, not the people."""
    backend = _Backend(one_step=False, accepts=True)
    await _run(monkeypatch, tmp_path, backend)
    call = backend.calls[0]
    assert call["image_url"] == "https://x/frame.png"
    assert call["kwargs"]["reference_images"] == [
        "https://x/mara.png",
        "https://x/victor.png",
        "https://x/set.png",
    ]
    assert call["kwargs"]["reference_labels"] == ["Mara", "Victor", "the empty set"]


@pytest.mark.asyncio
async def test_a_frame_backend_that_declares_nothing_sees_what_it_always_saw(monkeypatch, tmp_path):
    backend = _Backend(one_step=False, accepts=False)
    await _run(monkeypatch, tmp_path, backend)
    assert "reference_images" not in backend.calls[0]["kwargs"]
    assert "reference_labels" not in backend.calls[0]["kwargs"]
