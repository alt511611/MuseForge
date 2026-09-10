"""A scene rendered in one generation, with its cuts inside it.

Every scene this pipeline has made was assembled: each angle its own image,
its own video generation and its own file, joined afterwards by ffmpeg. That
was not a design, it was the only thing the models could do -- one still in,
five silent seconds out.

The arithmetic that follows from it is the part that shows. A second angle is
a second whole generation, so delivered job 4c7bbe85-e5c covered 30 seconds in
six shots: 5.04 seconds of unbroken picture on average, the bottom of the band
short-form retention research recommends. The framing count was not a
directing decision, it was what the price list allowed.

Billed per second of SCENE, extra cuts cost nothing.
"""

import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interfaces.scene_take import (
    MIN_BEAT_SECONDS,
    Beat,
    Element,
    SceneTake,
    plan_scene_take,
)
from interfaces.video_backend import backend_for


def _shots(*specs):
    from interfaces.shot import StoryboardShot

    return [
        StoryboardShot(
            idx=i,
            visual_desc=visual,
            motion_desc=motion,
            shot_type=framing,
            duration_seconds=seconds,
        )
        for i, (visual, motion, framing, seconds) in enumerate(specs)
    ]


def _three_shots():
    return _shots(
        ("Vivian deals, chips stacked", "slow push in", "medium shot", 5),
        ("Julian's eyes flick to her hands", "hold", "close-up", 4),
        ("the card turns over", "snap", "extreme close-up", 3),
    )


MULTISHOT = "fal-ai/kling-video/v3/standard/image-to-video"
SINGLE = "kling-v3.0-standard-image-to-video"


# --------------------------------------------------------------------------
# The decision: one take, or the path this pipeline has always taken
# --------------------------------------------------------------------------

def test_a_backend_that_cannot_cut_gets_no_take():
    """Returning None is the answer for every endpoint used here so far.

    A backend declaring max_beats of 1 is saying "a scene is a take, and a
    second angle is a second generation" -- which is true, and was the only
    option. The caller's per-shot path must be untouched by this feature
    existing.
    """
    assert plan_scene_take(12, _three_shots(), backend_for(SINGLE)) is None
    assert plan_scene_take(12, _three_shots(), None) is None


def test_a_scene_with_nothing_described_is_not_a_take():
    assert plan_scene_take(12, [], backend_for(MULTISHOT)) is None


# --------------------------------------------------------------------------
# The beats add up
# --------------------------------------------------------------------------

def test_the_beats_sum_to_exactly_what_the_backend_was_asked_for():
    """A take whose parts do not add up to its whole comes back the wrong
    length, which is the failure the second budget exists to prevent."""
    take = plan_scene_take(12, _three_shots(), backend_for(MULTISHOT))
    assert take.seconds == 12
    assert sum(beat.seconds for beat in take.beats) == 12
    assert take.beat_count == 3


@pytest.mark.parametrize("scene_seconds", [6, 7, 8, 9, 10, 11, 12])
def test_every_budget_in_the_scene_range_divides_exactly(scene_seconds):
    """MIN_SCENE_SECONDS is 6 and MAX_SCENE_SECONDS is 12; all of it must work."""
    take = plan_scene_take(scene_seconds, _three_shots(), backend_for(MULTISHOT))
    assert sum(beat.seconds for beat in take.beats) == take.seconds == scene_seconds
    assert all(beat.seconds >= MIN_BEAT_SECONDS for beat in take.beats)


def test_a_short_scene_holds_fewer_beats_rather_than_shorter_ones():
    """A beat below MIN_BEAT_SECONDS is a flash, not a shot.

    Six seconds cannot hold four beats without one of them being a flash, so
    it holds three.
    """
    take = plan_scene_take(6, _three_shots() + _three_shots(), backend_for(MULTISHOT))
    assert take.beat_count == 3
    assert all(beat.seconds >= MIN_BEAT_SECONDS for beat in take.beats)
    assert sum(beat.seconds for beat in take.beats) == 6


def test_surplus_angles_are_merged_not_dropped():
    """Dropping throws away coverage the storyboard designed AND shortens the
    scene; merging keeps every description and costs only a cut."""
    backend = backend_for(MULTISHOT)
    many = _three_shots() * 3  # nine angles against a ceiling of five
    take = plan_scene_take(12, many, backend)

    assert take.beat_count == backend.max_beats == 5
    assert sum(beat.seconds for beat in take.beats) == 12
    merged = " ".join(beat.description for beat in take.beats)
    for shot in many:
        assert shot.visual_desc in merged, "A described angle was thrown away."


def test_the_scene_length_is_snapped_to_what_the_backend_accepts():
    """The budget asks; the endpoint's duration field decides."""
    take = plan_scene_take(40, _three_shots(), backend_for(MULTISHOT))
    assert take.seconds == 15, "Kling v3 tops out at 15."
    assert sum(beat.seconds for beat in take.beats) == 15


# --------------------------------------------------------------------------
# What the model is actually told
# --------------------------------------------------------------------------

def test_each_beat_carries_its_framing_and_its_length():
    """A beat is an OBJECT with its own duration, not a sentence about one.

    This first went out as a list of strings with the length written into the
    prose ("Shot 1 (3s): ..."), which is the syntax Kling's own interface
    documents. The endpoint answered with one error per entry: "Input should
    be a valid dictionary or object to extract fields from".
    """
    take = plan_scene_take(12, _three_shots(), backend_for(MULTISHOT))
    beats = take.multi_prompt()

    assert len(beats) == 3
    assert set(beats[0]) == {"prompt", "duration"}
    assert [b["duration"] for b in beats] == ["5", "4", "3"], (
        "STRINGS, not integers -- the integer is a 422; and proportional to "
        "the lengths the storyboard designed"
    )
    assert sum(int(b["duration"]) for b in beats) == 12
    assert "medium shot" in beats[0]["prompt"]
    assert "Vivian deals" in beats[0]["prompt"]
    assert "Shot 1" not in beats[0]["prompt"], (
        "the length is a field now; repeating it in the prose spends prompt "
        "on something the model is already being told"
    )


def test_the_cast_clause_says_which_token_is_whom():
    """A model handed @Element1 and a beat that reads "she deals" has to guess
    which of two people that is, and guessing is how the wrong face speaks."""
    take = plan_scene_take(
        12,
        _three_shots(),
        backend_for(MULTISHOT),
        elements=[
            Element(name="Vivian Marsh", images=("v1.png", "v2.png")),
            Element(name="Julian Voss", images=("j1.png",)),
        ],
    )
    clause = take.cast_clause()
    assert "@Element1 is Vivian Marsh" in clause
    assert "@Element2 is Julian Voss" in clause


def test_elements_are_trimmed_to_what_the_backend_reads():
    backend = backend_for(MULTISHOT)
    crowd = [Element(name=f"Extra {i}", images=(f"{i}.png",)) for i in range(12)]
    take = plan_scene_take(12, _three_shots(), backend, elements=crowd)
    assert len(take.elements) == backend.max_elements == 7


def test_a_take_with_no_elements_has_no_cast_clause():
    take = plan_scene_take(12, _three_shots(), backend_for(MULTISHOT))
    assert take.cast_clause() == ""


# --------------------------------------------------------------------------
# The payload
# --------------------------------------------------------------------------

def _generator():
    from tools.falai_video_generator import FalAIVideoGenerator

    return FalAIVideoGenerator(api_key="test-key", demo=False)


@pytest.mark.asyncio
async def test_a_multi_beat_take_sends_a_shot_list_and_pins_the_cuts():
    generator = _generator()
    sent = {}

    async def fake_run(payload, endpoint, is_cancelled=None):
        sent.update({"payload": payload, "endpoint": endpoint})
        return "https://cdn/scene.mp4"

    generator._run = fake_run
    take = plan_scene_take(
        12,
        _three_shots(),
        backend_for(MULTISHOT),
        elements=[Element(name="Vivian Marsh", images=("v1.png", "v2.png"))],
        start_image="https://cdn/frame.png",
    )

    result = await generator.generate_scene_take(take)

    assert result == "https://cdn/scene.mp4"
    payload = sent["payload"]
    assert payload["start_image_url"] == "https://cdn/frame.png"
    assert payload["duration"] == "12"
    assert payload["generate_audio"] is True
    assert len(payload["multi_prompt"]) == 3
    assert payload["shot_type"] == "customize", (
        "'intelligent' lets the model pick its own cuts, throwing away the "
        "storyboard."
    )
    assert "prompt" not in payload
    # The shape the endpoint's own 422 spelled out: a main view plus up to
    # three more angles. There is no `name` field, which is why the cast
    # clause below is the only thing that says who @Element1 is.
    assert payload["elements"] == [
        {"frontal_image_url": "v1.png", "reference_image_urls": ["v2.png"]}
    ]
    assert "@Element1 is Vivian Marsh" in payload["multi_prompt"][0]["prompt"]


@pytest.mark.asyncio
async def test_a_single_beat_take_is_not_a_multi_shot_request():
    """A one-item list asks a multi-shot planner to plan nothing."""
    generator = _generator()
    sent = {}

    async def fake_run(payload, endpoint, is_cancelled=None):
        sent.update(payload)
        return "https://cdn/scene.mp4"

    generator._run = fake_run
    take = SceneTake(seconds=6, beats=(Beat(seconds=6, description="a wide of the room"),))
    await generator.generate_scene_take(take)

    assert "multi_prompt" not in sent
    assert "shot_type" not in sent
    assert sent["prompt"] == "a wide of the room", (
        "a single beat sends `prompt`, which is a plain string -- not the "
        "object multi_prompt takes"
    )


@pytest.mark.asyncio
async def test_a_voice_id_rides_the_element_when_one_is_mapped():
    """Bound by ID, not by uploaded sample.

    The plan this was built from assumed a 5-30 second clip could be attached
    to the element. The endpoint takes `voice_id` from its own voice library
    and has nowhere to put a clip -- so keeping a film's cast through a
    native-audio take means MAPPING characters onto that library, which is a
    different job and is not done yet. This pins the plumbing for when it is.
    """
    generator = _generator()
    sent = {}

    async def fake_run(payload, endpoint, is_cancelled=None):
        sent.update(payload)
        return "https://cdn/scene.mp4"

    generator._run = fake_run
    take = plan_scene_take(
        12,
        _three_shots(),
        backend_for(MULTISHOT),
        elements=[
            Element(
                name="Julian Voss",
                images=("j1.png",),
                voice_id="kling-voice-042",
            )
        ],
    )
    await generator.generate_scene_take(take)

    assert sent["elements"][0]["voice_id"] == "kling-voice-042"


@pytest.mark.asyncio
async def test_audio_can_be_turned_off_for_a_scene_the_pipeline_will_voice():
    """A film in a language the backend does not speak keeps the old path."""
    generator = _generator()
    sent = {}

    async def fake_run(payload, endpoint, is_cancelled=None):
        sent.update(payload)
        return "https://cdn/scene.mp4"

    generator._run = fake_run
    take = plan_scene_take(12, _three_shots(), backend_for(MULTISHOT))
    await generator.generate_scene_take(take, generate_audio=False)

    assert sent["generate_audio"] is False


@pytest.mark.asyncio
async def test_an_element_with_no_images_is_not_sent_at_all():
    """An empty element is a slot spent on nothing."""
    generator = _generator()
    sent = {}

    async def fake_run(payload, endpoint, is_cancelled=None):
        sent.update(payload)
        return "https://cdn/scene.mp4"

    generator._run = fake_run
    take = plan_scene_take(
        12,
        _three_shots(),
        backend_for(MULTISHOT),
        elements=[Element(name="Nobody", images=())],
    )
    await generator.generate_scene_take(take)
    assert "elements" not in sent


@pytest.mark.asyncio
async def test_the_take_goes_to_the_multi_shot_endpoint_not_the_single_one():
    generator = _generator()
    sent = {}

    async def fake_run(payload, endpoint, is_cancelled=None):
        sent["endpoint"] = endpoint
        return "https://cdn/scene.mp4"

    generator._run = fake_run
    take = plan_scene_take(12, _three_shots(), backend_for(MULTISHOT))
    await generator.generate_scene_take(take)

    assert sent["endpoint"] == generator.MULTISHOT_ENDPOINT
    assert sent["endpoint"] != generator.ENDPOINT


# --------------------------------------------------------------------------
# The economics this exists for
# --------------------------------------------------------------------------

def test_extra_cuts_cost_nothing_once_the_bill_is_per_second():
    """The reason a delivered 30-second film only ever had six shots."""
    single = backend_for(SINGLE)
    multi = backend_for(MULTISHOT)

    # Today: a 12-second scene covered in three angles is three generations.
    assert single.max_beats == 1
    three_angles_today = 3 * single.cost(12)

    # With cuts inside one take, the scene is billed once, by its length.
    one_take = multi.cost(12)

    assert one_take < three_angles_today
    # And a fourth and fifth cut change the bill not at all.
    assert multi.cost(12) == one_take


# --------------------------------------------------------------------------
# The pipeline actually takes the route
# --------------------------------------------------------------------------

class _FakeMultishotGenerator:
    """Stands in for FalAIVideoGenerator with multishot selected."""

    MULTISHOT_ENDPOINT = MULTISHOT

    def __init__(self):
        self.multishot = True
        self.takes = []

    async def generate_scene_take(self, take, is_cancelled=None, generate_audio=True):
        self.takes.append({"take": take, "audio": generate_audio})
        return "https://fake.cdn/scene.mp4"

    async def generate_video_from_image(self, *args, **kwargs):  # pragma: no cover
        raise AssertionError(
            "The one-take path must not fall through to a per-shot render."
        )


def _wire(monkeypatch, tmp_path, generator, characters, shots):
    import agents.storyboard_artist as sb_mod
    import pipelines.script2video as s2v_mod
    import tools.muapi_image_generator as img_mod

    frames = []

    async def fake_design_storyboard(self, *a, **k):
        return list(shots)

    async def fake_ref(self, prompt, references, aspect_ratio="16:9", is_cancelled=None):
        frames.append(references)
        return "https://fake.cdn/opening.png"

    async def fake_plain(self, prompt, aspect_ratio="16:9", is_cancelled=None):
        frames.append(None)
        return "https://fake.cdn/opening.png"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_ref)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image", fake_plain)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)
    return frames


def _two_hander():
    from interfaces.character import CharacterInScene

    return [
        CharacterInScene(idx=0, name="Vivian Marsh", static_features="woman, thirties"),
        CharacterInScene(idx=1, name="Julian Voss", static_features="man, forties"),
    ]


@pytest.mark.asyncio
async def test_a_scene_becomes_one_generation_with_its_cuts_inside(monkeypatch, tmp_path):
    from pipelines.script2video import Script2VideoPipeline

    os.environ.setdefault("MUAPI_KEY", "test-key")
    characters = _two_hander()
    shots = _three_shots()
    shots[0].visual_desc = "Vivian Marsh deals, chips stacked"

    generator = _FakeMultishotGenerator()
    _wire(monkeypatch, tmp_path, generator, characters, shots)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    pipeline.video_gen = generator

    result = await pipeline.run(
        script="Vivian Marsh deals. Julian Voss watches.",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits={
            "Vivian Marsh": "https://cdn/vivian.png",
            "Julian Voss": "https://cdn/julian.png",
        },
        scene_duration=12,
        has_dialogue=True,
        scene_dialogue="Play your cards, Mr. Voss.",
        voice_ids={"Julian Voss": "kling-voice-042"},
    )

    assert len(generator.takes) == 1, "One generation for the whole scene."
    take = generator.takes[0]["take"]
    assert take.beat_count == 3, "The storyboard's three angles became three beats."
    assert sum(b.seconds for b in take.beats) == 12
    assert take.start_image == "https://fake.cdn/opening.png"
    assert result["path"].endswith("scene_output.mp4")
    assert os.path.exists(result["path"])
    assert len(result["shots"]) == 3, (
        "Downstream still sees the framings the storyboard designed."
    )


@pytest.mark.asyncio
async def test_the_opening_frame_is_drawn_from_the_same_faces_as_a_per_shot_render(
    monkeypatch, tmp_path
):
    """The two routes must not disagree about who is in the scene.

    Both call resolve_frame_references, which is why they cannot -- and this
    pins it, because a second copy of that logic is exactly how they would.
    """
    from pipelines.script2video import Script2VideoPipeline

    characters = _two_hander()
    shots = _three_shots()
    shots[0].visual_desc = "Vivian Marsh deals as Julian Voss watches"

    generator = _FakeMultishotGenerator()
    frames = _wire(monkeypatch, tmp_path, generator, characters, shots)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    pipeline.video_gen = generator
    await pipeline.run(
        script="Vivian Marsh deals as Julian Voss watches.",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits={
            "Vivian Marsh": "https://cdn/vivian.png",
            "Julian Voss": "https://cdn/julian.png",
        },
        location_plate_url="https://cdn/plate.png",
        scene_duration=12,
    )

    assert len(frames) == 1, "One opening frame, not one per angle."
    assert frames[0] == [
        "https://cdn/vivian.png",
        "https://cdn/julian.png",
        "https://cdn/plate.png",
    ]


@pytest.mark.asyncio
async def test_the_cast_reaches_the_take_as_elements_with_their_voices(
    monkeypatch, tmp_path
):
    from pipelines.script2video import Script2VideoPipeline

    characters = _two_hander()
    shots = _three_shots()
    shots[0].visual_desc = "Vivian Marsh deals as Julian Voss watches"

    generator = _FakeMultishotGenerator()
    _wire(monkeypatch, tmp_path, generator, characters, shots)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    pipeline.video_gen = generator
    await pipeline.run(
        script="Vivian Marsh deals as Julian Voss watches.",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits={
            "Vivian Marsh": "https://cdn/vivian.png",
            "Julian Voss": "https://cdn/julian.png",
        },
        scene_duration=12,
        voice_ids={
            "Vivian Marsh": "kling-voice-011",
            "Julian Voss": "kling-voice-042",
        },
    )

    take = generator.takes[0]["take"]
    names = [e.name for e in take.elements]
    assert names == ["Vivian Marsh", "Julian Voss"], "Anchor first."
    assert take.elements[0].voice_id == "kling-voice-011"


@pytest.mark.asyncio
async def test_a_language_the_backend_cannot_speak_keeps_the_old_audio_path(
    monkeypatch, tmp_path
):
    """"Has native audio" is not a property an endpoint has; a LANGUAGE is.

    Kling v3 speaks English and Chinese. A Turkish film rendered on it must
    come back mute and keep the dialogue and lip-sync passes it always had --
    silently accepting the model's own voice would ship a Turkish drama spoken
    in translated English.
    """
    from pipelines.script2video import Script2VideoPipeline

    characters = _two_hander()
    shots = _three_shots()
    generator = _FakeMultishotGenerator()
    _wire(monkeypatch, tmp_path, generator, characters, shots)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    pipeline.video_gen = generator

    for language, expected in (("en", True), ("tr", False)):
        generator.takes.clear()
        await pipeline.run(
            script="Vivian Marsh deals.",
            characters=characters,
            working_dir=str(tmp_path),
            character_portraits={"Vivian Marsh": "https://cdn/vivian.png"},
            scene_duration=12,
            has_dialogue=True,
            scene_dialogue="a line",
            language=language,
        )
        assert generator.takes[0]["audio"] is expected, (
            f"language={language} should render audio={expected}"
        )


@pytest.mark.asyncio
async def test_a_silent_scene_never_asks_for_audio(monkeypatch, tmp_path):
    from pipelines.script2video import Script2VideoPipeline

    characters = _two_hander()
    generator = _FakeMultishotGenerator()
    _wire(monkeypatch, tmp_path, generator, characters, _three_shots())

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    pipeline.video_gen = generator
    await pipeline.run(
        script="the room, empty",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits={"Vivian Marsh": "https://cdn/vivian.png"},
        scene_duration=12,
        has_dialogue=False,
        language="en",
    )
    assert generator.takes[0]["audio"] is False


def test_the_route_is_chosen_by_selection_and_capability_together():
    """Either half alone must not change how a scene renders.

    The capability without the selection would change how an existing
    MUSEFORGE_VIDEO_PROVIDER=falai deployment renders; the selection without
    the capability would send a shot list to something that cannot cut.
    """
    from pipelines.script2video import scene_take_backend

    class NotSelected:
        MULTISHOT_ENDPOINT = MULTISHOT
        multishot = False

        async def generate_scene_take(self, *a, **k):  # pragma: no cover
            ...

    class Selected:
        MULTISHOT_ENDPOINT = MULTISHOT
        multishot = True

        async def generate_scene_take(self, *a, **k):  # pragma: no cover
            ...

    class SelectedButIncapable:
        MULTISHOT_ENDPOINT = SINGLE
        multishot = True

        async def generate_scene_take(self, *a, **k):  # pragma: no cover
            ...

    assert scene_take_backend(NotSelected()) is None
    assert scene_take_backend(SelectedButIncapable()) is None
    assert scene_take_backend(Selected()) is not None
    assert scene_take_backend(object()) is None
