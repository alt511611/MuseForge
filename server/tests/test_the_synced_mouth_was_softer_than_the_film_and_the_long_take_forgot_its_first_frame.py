"""Job 6efbb788, the three things its first fix left open.

1. The two lip-synced scenes were the only soft ones in a 1080p film: H3 drew
   them at a flat 768P (1344x768) and they were scaled up 1.41x to rejoin it.
2. A take is anchored at frame 0 and nowhere else. The 11-second blackout held
   its face and its darkness for about six seconds, then lit every floodlight
   and became a younger woman.
3. The multi-shot take -- the path that renders a whole scene in one request --
   had both problems and two of its own: its prompt never said the world had
   changed, and its element was handed the whole 2x2 character sheet as "the
   frontal view" and no angles, the shape its own docstring says the sheet
   produces and it was never given.
"""

import asyncio
import io
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import fal_client  # noqa: E402

import tools.falai_h3_lipsync as h3  # noqa: E402
from interfaces import long_take  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.scene_take import Beat, Element, SceneTake, MAX_STATE_CHARS  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from tools import sheet_views  # noqa: E402

BLACKOUT = (
    "every floodlight pole along the harbour goes dark, leaving the open "
    "container's glow as the only light on the dock"
)


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# --- 1. the synced mouth ------------------------------------------------------


def test_the_tier_is_the_scene_s_own(monkeypatch):
    monkeypatch.delenv("FALAI_H3_LIPSYNC_RESOLUTION", raising=False)
    assert h3._resolution(1080) == "1080P", "a 1080p film is synced at 1080P"
    assert h3._resolution(720) == "768P"
    assert h3._resolution(480) == "480P"
    assert h3._resolution(2160) == "1080P", "2K is never chosen by size"
    assert h3._resolution() == "768P", "an unmeasurable scene keeps the old default"


def test_an_operator_who_pins_a_tier_keeps_it(monkeypatch):
    monkeypatch.setenv("FALAI_H3_LIPSYNC_RESOLUTION", "768p")
    assert h3._resolution(1080) == "768P"


class _Handle:
    request_id = "req"


class _Client:
    def __init__(self):
        self.submitted = []

    async def upload_file(self, path):
        return f"https://fal/{os.path.basename(path)}"

    async def submit(self, endpoint, arguments):
        self.submitted.append(arguments)
        return _Handle()

    async def status(self, endpoint, request_id, with_logs=False):
        return fal_client.Completed(logs=None, metrics={})

    async def result(self, endpoint, request_id):
        return {"video": {"url": "https://fal/h3.mp4"}}


def test_a_1080p_scene_is_redrawn_at_1080p(monkeypatch):
    monkeypatch.delenv("FALAI_H3_LIPSYNC_RESOLUTION", raising=False)
    provider = h3.FalAIH3Lipsync("key")
    provider.client = _Client()

    async def first_frame(video, out):
        open(out, "wb").write(b"png")
        return True

    async def seconds(path):
        return 6.0

    async def size(path):
        return (1920, 1080)

    monkeypatch.setattr(h3, "_first_frame", first_frame)
    monkeypatch.setattr(h3, "_probe_seconds", seconds)
    monkeypatch.setattr(h3, "_probe_size", size)
    monkeypatch.setattr(os.path, "isfile", lambda p: True if p == "/scene.mp4" else os.path.exists(p))

    _run(provider.sync("/scene.mp4", "https://fal/line.mp3"))
    assert provider.client.submitted[0]["resolution"] == "1080P"


def test_a_vertical_film_is_measured_by_its_short_side(monkeypatch):
    """1080x1920 is a 1080p film, not a 1920p one."""
    monkeypatch.delenv("FALAI_H3_LIPSYNC_RESOLUTION", raising=False)
    assert h3._resolution(min(1080, 1920)) == "1080P"


# --- 2. the long take ---------------------------------------------------------


def test_a_take_long_enough_to_drift_is_long():
    assert long_take.is_long(11.0)
    assert long_take.is_long(7.0)
    assert not long_take.is_long(4.0), "the 3-4 s shots never drifted"


def test_it_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_LONG_TAKE_END_FRAME", "0")
    assert not long_take.is_long(11.0)


def test_the_end_frame_moves_on_and_keeps_everything_a_viewer_recognises():
    prompt = long_take.end_frame_prompt(
        action="Mira wrenches the lever and hauls the doors open",
        name="Mira",
        peak="eyes snapping wide",
        world_state=BLACKOUT,
    )
    assert "hauls the doors open" in prompt, "the take must still perform its action"
    assert "identical face, hair, age and clothing" in prompt
    assert "same camera position" in prompt
    assert "stays changed" in prompt and "floodlight" in prompt
    assert "eyes snapping wide" in prompt


class _RefImageGen:
    accepts_reference_labels = True

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    async def generate_image_with_reference(self, prompt, references, aspect_ratio="16:9",
                                            is_cancelled=None, reference_labels=None):
        self.calls.append({"prompt": prompt, "references": list(references),
                           "labels": list(reference_labels or [])})
        if self.fail:
            raise RuntimeError("refused")
        return "https://cdn/end.jpg"


def _pipeline(image_gen):
    from pipelines.script2video import Script2VideoPipeline

    pipeline = Script2VideoPipeline(api_key="test", demo=True)
    pipeline.image_gen = image_gen
    return pipeline


MIRA = CharacterInScene(idx=0, name="Mira", static_features="woman, late thirties")


def _shot(seconds):
    return StoryboardShot(
        idx=0, visual_desc="Mira at the lever", motion_desc="Mira hauls the doors open",
        shot_type="close-up", lens="50mm", duration_seconds=seconds,
        expression_peak_desc="eyes snapping wide",
    )


def test_an_eleven_second_take_is_given_a_drawn_last_frame(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_ACTING_END_FRAME", raising=False)
    image_gen = _RefImageGen()
    url = _run(_pipeline(image_gen)._render_end_frame(
        frame_url="https://cdn/open.jpg", shot=_shot(11.0), matched_char=MIRA,
        portrait="https://cdn/mira_sheet.jpg", world_state=BLACKOUT,
    ))
    assert url == "https://cdn/end.jpg"
    call = image_gen.calls[0]
    assert call["references"] == ["https://cdn/open.jpg", "https://cdn/mira_sheet.jpg"]
    assert call["labels"] == ["the opening frame of this shot", "Mira"]
    assert "stays changed" in call["prompt"]


def test_a_short_take_is_left_alone(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_ACTING_END_FRAME", raising=False)
    image_gen = _RefImageGen()
    assert _run(_pipeline(image_gen)._render_end_frame(
        frame_url="https://cdn/open.jpg", shot=_shot(4.0), matched_char=MIRA,
    )) is None
    assert image_gen.calls == []


def test_an_empty_take_has_no_face_to_anchor():
    image_gen = _RefImageGen()
    assert _run(_pipeline(image_gen)._render_end_frame(
        frame_url="https://cdn/plate.jpg", shot=_shot(11.0), matched_char=None,
    )) is None


def test_a_refused_end_frame_leaves_the_take_as_it_was():
    assert _run(_pipeline(_RefImageGen(fail=True))._render_end_frame(
        frame_url="https://cdn/open.jpg", shot=_shot(11.0), matched_char=MIRA,
    )) is None


def test_the_fal_image_provider_can_now_edit(monkeypatch):
    """Without edit_image the acting end frame silently never ran on fal."""
    from tools.falai_image_generator import FalAIImageGenerator

    generator = FalAIImageGenerator("key", nanobanana=True)
    seen = {}

    async def fake(prompt, references, aspect_ratio="16:9", is_cancelled=None, **kw):
        seen["references"] = references
        return "https://cdn/edited.jpg"

    monkeypatch.setattr(generator, "generate_image_with_reference", fake)
    assert _run(generator.edit_image("make her smile", "https://cdn/open.jpg")) == "https://cdn/edited.jpg"
    assert seen["references"] == ["https://cdn/open.jpg"]


# --- 3. the one-take path -----------------------------------------------------


def _take(world_state="", limit=512):
    return SceneTake(
        seconds=12,
        beats=(
            Beat(seconds=6, description="Mira grips the lever.", shot_type="close-up"),
            Beat(seconds=6, description="Mira stares into the light.", shot_type="medium"),
        ),
        elements=(Element(name="Mira", images=("https://cdn/front.jpg",)),),
        max_prompt_chars=limit,
        world_state=world_state,
    )


def test_every_beat_of_the_take_holds_the_changed_world():
    beats = _take(world_state=BLACKOUT).multi_prompt()
    for beat in beats:
        assert "stays so" in beat["prompt"], "the late beats are the ones that revert"
        assert "floodlight" in beat["prompt"]


def test_every_beat_still_fits_the_endpoint_with_it():
    """An overrun here is a 422 on the whole scene."""
    from interfaces.scene_take import wire_length

    long_state = "every single floodlight " * 20
    for beat in _take(world_state=long_state).multi_prompt():
        assert wire_length(beat["prompt"]) <= 512
    assert MAX_STATE_CHARS <= 120


def test_a_take_before_the_event_says_nothing_about_it():
    for beat in _take().multi_prompt():
        assert "stays so" not in beat["prompt"]


def test_a_sheet_is_cut_into_the_four_views_it_was_drawn_as():
    from PIL import Image

    uploads = []

    class _Uploader:
        async def upload_file(self, path):
            with Image.open(path) as panel:
                uploads.append(panel.size)
            return f"https://fal/{os.path.basename(path)}"

    sheet = Image.new("RGB", (1024, 1024), "grey")
    buffer = io.BytesIO()
    sheet.save(buffer, format="JPEG")

    class _Response:
        content = buffer.getvalue()

        def raise_for_status(self):
            pass

    class _Http:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _Response()

    import httpx

    original = httpx.AsyncClient
    httpx.AsyncClient = _Http
    try:
        views = _run(sheet_views.split_sheet("https://cdn/sheet.jpg", client=_Uploader()))
    finally:
        httpx.AsyncClient = original

    assert len(views) == 4, "frontal, then the three angles"
    assert uploads == [(512, 512)] * 4


def test_a_photograph_is_never_cut_into_quarters():
    from PIL import Image

    photo = Image.new("RGB", (768, 1024), "grey")  # a 3:4 phone photo
    buffer = io.BytesIO()
    photo.save(buffer, format="JPEG")

    class _Response:
        content = buffer.getvalue()

        def raise_for_status(self):
            pass

    class _Http:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _Response()

    import httpx

    original = httpx.AsyncClient
    httpx.AsyncClient = _Http
    try:
        assert _run(sheet_views.split_sheet("https://cdn/photo.jpg", client=object())) == ()
    finally:
        httpx.AsyncClient = original


def test_the_quadrants_are_in_the_order_the_sheet_is_drawn():
    assert sheet_views.quadrants(1024, 1024) == (
        (0, 0, 512, 512),
        (512, 0, 1024, 512),
        (0, 512, 512, 1024),
        (512, 512, 1024, 1024),
    )


def test_without_the_sheet_flag_the_take_gets_the_portrait_whole(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_CHARACTER_SHEET", raising=False)
    from pipelines.script2video import Script2VideoPipeline

    pipeline = Script2VideoPipeline(api_key="test", demo=False)
    assert _run(pipeline._views_of("https://cdn/portrait.jpg")) == ()
