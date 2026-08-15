"""Acting: the micro-expression map and the start-to-end frame interpolation.

The chain this pins, end to end:

    scene emotion tag
      -> interfaces/acting beat (onset + peak + voice tag), deterministic
      -> shot.expression_desc / shot.expression_peak_desc
      -> motion prompt states the PERFORMANCE ARC (both ends, not one pose)
      -> an edited end frame reaches the video model as `last_image`
      -> ...unless the endpoint has no such field, where it is dropped, not 422'd

The failure being guarded is the one that makes AI drama look like AI drama:
a face that holds one unchanging expression for the whole clip.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces import acting  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    Script2VideoPipeline,
    build_motion_prompt,
)
from tools.muapi_video_generator import MuAPIVideoGenerator  # noqa: E402


def _shot(**overrides):
    base = dict(
        idx=0,
        visual_desc="Mother and daughter at the kitchen table",
        motion_desc="slow push-in",
        expression_desc="",
        shot_type="close-up",
        camera_movement="static",
        lens="50mm",
        duration_seconds=8.0,
    )
    base.update(overrides)
    return StoryboardShot(**base)


# --- the map itself ----------------------------------------------------


def test_every_beat_is_anatomical_not_abstract():
    """A peak the camera cannot see is a peak that does not get acted."""
    for keys, beat in acting._BEATS:
        assert beat.peak, keys
        # Each peak has to name at least one piece of visible anatomy; a
        # description like "she feels betrayed" gives the model nothing to draw.
        assert any(
            part in beat.peak
            for part in ("eye", "jaw", "brow", "mouth", "lip", "chin", "cheek",
                         "shoulder", "throat", "breath", "tear", "head", "face",
                         "teeth", "gaze", "neck", "colour")
        ), f"{beat.label} peak is not anatomical: {beat.peak}"
        assert 0.0 <= beat.stability <= 1.0


def test_beat_is_deterministic():
    """Same tag, same performance -- a retake must not re-act the film."""
    assert acting.resolve("cold rage") is acting.resolve("cold rage")
    assert acting.peak_expression("tearful goodbye") == acting.peak_expression(
        "tearful goodbye"
    )


def test_turkish_emotion_tags_hit_the_map():
    """The screenwriter writes the tag in the drama's own language."""
    assert acting.resolve("öfkeli yüzleşme").label == "rage"
    assert acting.resolve("gözyaşlarıyla veda").label == "grief"
    assert acting.resolve("sessiz utanç").label == "shame"


def test_unknown_emotion_still_gets_a_change_to_play():
    beat = acting.resolve("something nobody mapped")
    assert beat is acting.NEUTRAL
    # Even the fallback names a shift, because "no expression" is the bug.
    assert beat.peak.strip()


def test_onset_keeps_the_agents_own_words_first():
    written = "chin trembling, eyes brimming"
    onset = acting.onset_expression("tearful reconciliation", written)
    assert onset.startswith(written)
    assert "jaw" in onset  # ...and the mapped floor underneath it


def test_onset_leaves_an_already_specific_expression_alone():
    """The frame prompt is over budget on a normal scene; padding a good
    expression only makes it likelier to be dropped."""
    written = "x" * acting.ALREADY_SPECIFIC_CHARS
    assert acting.onset_expression("grief", written) == written


def test_voice_tag_is_bracketed_or_empty():
    assert acting.voice_tag("cold rage") == "[furious] "
    assert acting.voice_tag("something nobody mapped") == ""
    assert acting.voice_stability("cold rage") < 0.5


# --- storyboard fills both ends, on every path -------------------------


@pytest.mark.asyncio
async def test_template_path_fills_onset_and_peak():
    artist = StoryboardArtist(api_key="")
    artist.muapi_key = ""
    shots = await artist.design_storyboard(
        script="She finally says it.",
        characters=[CharacterInScene(idx=0, name="Ayse", static_features="50s woman")],
        scene_emotion="quiet shame",
    )
    assert shots[0].expression_peak_desc == acting.peak_expression("quiet shame")


def test_peak_is_set_even_when_the_agent_wrote_a_good_expression():
    """The LLM is never asked for the peak, so nothing else can fill it."""
    shots = [_shot(expression_desc="eyes narrowing, breath held")]
    StoryboardArtist._apply_acting_beats(shots, "cold rage")
    assert shots[0].expression_peak_desc == acting.peak_expression("cold rage")


# --- the arc reaches the video model -----------------------------------


def test_motion_prompt_states_both_ends_of_the_performance():
    shot = _shot(
        expression_desc="jaw tight, eyes dry",
        expression_peak_desc="a single tear spilling over the lower lid",
    )
    prompt = build_motion_prompt(shot)
    assert "jaw tight, eyes dry" in prompt
    assert "a single tear spilling over the lower lid" in prompt
    assert "LANDS on" in prompt


def test_motion_prompt_without_a_peak_keeps_the_old_single_beat_shape():
    prompt = build_motion_prompt(_shot(expression_desc="jaw tight"))
    assert "stays true to the beat" in prompt
    assert "LANDS on" not in prompt


# --- the end frame -----------------------------------------------------


class _RecordingImageGen:
    def __init__(self, result="https://cdn/end.png", fail=False):
        self.result = result
        self.fail = fail
        self.calls = []

    async def edit_image(self, prompt, image_url, aspect_ratio="16:9", is_cancelled=None):
        self.calls.append({"prompt": prompt, "image_url": image_url})
        if self.fail:
            raise RuntimeError("provider said no")
        return self.result


def _pipeline(image_gen):
    pipeline = Script2VideoPipeline(api_key="test", demo=True)
    pipeline.image_gen = image_gen
    return pipeline


@pytest.mark.asyncio
async def test_end_frame_is_off_by_default(monkeypatch):
    """It costs an extra generation per shot, so it is opted into."""
    monkeypatch.delenv("MUSEFORGE_ACTING_END_FRAME", raising=False)
    image_gen = _RecordingImageGen()
    result = await _pipeline(image_gen)._render_end_frame(
        frame_url="https://cdn/start.png",
        shot=_shot(expression_peak_desc="tears breaking over the lid"),
        matched_char=CharacterInScene(idx=0, name="Ayse", static_features="50s woman"),
    )
    assert result is None
    assert image_gen.calls == []


@pytest.mark.asyncio
async def test_end_frame_edit_forbids_recomposition(monkeypatch):
    """Interpolating between two DIFFERENT compositions is a warp, not acting."""
    monkeypatch.setenv("MUSEFORGE_ACTING_END_FRAME", "1")
    image_gen = _RecordingImageGen()
    result = await _pipeline(image_gen)._render_end_frame(
        frame_url="https://cdn/start.png",
        shot=_shot(expression_peak_desc="tears breaking over the lid"),
        matched_char=CharacterInScene(idx=0, name="Ayse", static_features="50s woman"),
    )
    assert result == "https://cdn/end.png"
    prompt = image_gen.calls[0]["prompt"]
    # The edit is applied to the START FRAME, never to the portrait.
    assert image_gen.calls[0]["image_url"] == "https://cdn/start.png"
    assert "identical framing" in prompt
    assert "Do not re-frame" in prompt
    assert "tears breaking over the lid" in prompt


@pytest.mark.asyncio
async def test_end_frame_failure_is_fail_open(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_ACTING_END_FRAME", "1")
    result = await _pipeline(_RecordingImageGen(fail=True))._render_end_frame(
        frame_url="https://cdn/start.png",
        shot=_shot(expression_peak_desc="tears"),
        matched_char=CharacterInScene(idx=0, name="Ayse", static_features="50s woman"),
    )
    assert result is None


@pytest.mark.asyncio
async def test_no_end_frame_for_a_shot_with_no_face(monkeypatch):
    """An establishing plate has no expression to land."""
    monkeypatch.setenv("MUSEFORGE_ACTING_END_FRAME", "1")
    image_gen = _RecordingImageGen()
    result = await _pipeline(image_gen)._render_end_frame(
        frame_url="https://cdn/plate.png",
        shot=_shot(expression_peak_desc="tears"),
        matched_char=None,
    )
    assert result is None
    assert image_gen.calls == []


@pytest.mark.asyncio
async def test_no_end_frame_when_the_provider_cannot_edit(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_ACTING_END_FRAME", "1")

    class _NoEdit:
        pass

    result = await _pipeline(_NoEdit())._render_end_frame(
        frame_url="https://cdn/start.png",
        shot=_shot(expression_peak_desc="tears"),
        matched_char=CharacterInScene(idx=0, name="Ayse", static_features="50s woman"),
    )
    assert result is None


# --- payload: only endpoints that declare the field get it -------------


def test_last_image_reaches_kling_v3_payload():
    payload = MuAPIVideoGenerator(api_key="k")._payload(
        "prompt",
        "https://cdn/start.png",
        8,
        last_image="https://cdn/end.png",
        endpoint="kling-v3.0-standard-image-to-video",
    )
    assert payload["last_image"] == "https://cdn/end.png"


def test_last_image_is_dropped_for_endpoints_without_the_field():
    """Turbo takes prompt/image_url/duration only; sending more is a 422,
    which the fallback chain would read as 'this model does not exist'."""
    payload = MuAPIVideoGenerator(api_key="k")._payload(
        "prompt",
        "https://cdn/start.png",
        8,
        last_image="https://cdn/end.png",
        endpoint="kling-v3-turbo-standard-image-to-video",
    )
    assert "last_image" not in payload


# --- endpoint schemas that are narrower than Kling's -------------------
#
# Verified against each model's API Reference on muapi.ai (2026-08-14). These
# are the failures that do NOT announce themselves: MuAPI answers a bad field
# with a 422, the fallback chain reads a 422 as "this endpoint does not exist"
# and demotes the shot to Standard -- so a routed model appears to be
# configured and simply never runs.


def test_veo_gets_the_only_duration_it_accepts():
    """Veo's duration is the enum [8], not Kling's 3-15 range."""
    payload = MuAPIVideoGenerator(api_key="k")._payload(
        "prompt", "https://cdn/start.png", 6, endpoint="veo3.1-lite-image-to-video"
    )
    assert payload["duration"] == 8


def test_kling_keeps_its_range():
    payload = MuAPIVideoGenerator(api_key="k")._payload(
        "prompt", "https://cdn/start.png", 6,
        endpoint="kling-v3.0-standard-image-to-video",
    )
    assert payload["duration"] == 6


def test_a_square_job_does_not_break_a_veo_shot():
    """Veo takes 16:9 and 9:16; this product also sells 1:1."""
    payload = MuAPIVideoGenerator(api_key="k")._payload(
        "prompt", "https://cdn/start.png", 8,
        endpoint="veo3.1-lite-image-to-video", aspect_ratio="1:1",
    )
    assert "aspect_ratio" not in payload

    vertical = MuAPIVideoGenerator(api_key="k")._payload(
        "prompt", "https://cdn/start.png", 8,
        endpoint="veo3.1-lite-image-to-video", aspect_ratio="9:16",
    )
    assert vertical["aspect_ratio"] == "9:16"


def test_veo_carries_the_acted_end_frame():
    """The cheapest flat-priced i2v endpoint on the list also takes the peak."""
    payload = MuAPIVideoGenerator(api_key="k")._payload(
        "prompt", "https://cdn/start.png", 8,
        last_image="https://cdn/end.png",
        endpoint="veo3.1-lite-image-to-video",
    )
    assert payload["last_image"] == "https://cdn/end.png"
