"""Dialogue straight from ElevenLabs, and the timings that come with it."""

import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

AUDIO = base64.b64encode(b"ID3-not-really-an-mp3").decode()

LINES = [
    {"character": "Mara", "line": "Priya, you seeing this?"},
    {"character": "Priya", "line": "Negative. Finish your round."},
]


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError("boom", request=None, response=self)


class _Client:
    """Stands in for httpx.AsyncClient, recording what was sent."""

    posted = None
    payload = None
    status = 200

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        type(self).posted = {"url": url, "headers": headers, "json": json}
        return _Response(type(self).payload, type(self).status)

    async def get(self, url, headers=None):
        type(self).posted = {"url": url, "headers": headers}
        return _Response(type(self).payload, type(self).status)


@pytest.fixture(autouse=True)
def _clean():
    _Client.posted = None
    _Client.payload = None
    _Client.status = 200
    yield


def _generator(tmp_path, monkeypatch):
    from tools import elevenlabs_voice_generator as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", _Client)
    return mod.ElevenLabsVoiceGenerator("key", working_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_the_request_uses_the_providers_own_field_names(tmp_path, monkeypatch):
    """MuAPI's wrapper renamed the list to `dialogue`; the real endpoint calls
    it `inputs`, and sending the wrong one is a 422 before a note is sung."""
    _Client.payload = {"audio_base64": AUDIO, "voice_segments": []}
    generator = _generator(tmp_path, monkeypatch)

    await generator.generate_scene_dialogue(LINES)

    sent = _Client.posted
    assert sent["url"].endswith("/text-to-dialogue/with-timestamps")
    assert sent["headers"]["xi-api-key"] == "key"
    assert [turn["text"] for turn in sent["json"]["inputs"]] == [
        "Priya, you seeing this?",
        "Negative. Finish your round.",
    ]
    assert "dialogue" not in sent["json"]


@pytest.mark.asyncio
async def test_measured_timings_replace_the_word_count_guess(tmp_path, monkeypatch):
    """The reason to come here at all, beyond the voices working: every cue
    bug in this product came from estimating a line's length from its word
    count. This endpoint measures the speech it just made."""
    _Client.payload = {
        "audio_base64": AUDIO,
        "voice_segments": [
            {"dialogue_input_index": 0, "start_time_seconds": 0.0, "end_time_seconds": 1.9},
            {"dialogue_input_index": 1, "start_time_seconds": 2.2, "end_time_seconds": 4.6},
        ],
    }
    tracks = await _generator(tmp_path, monkeypatch).generate_scene_dialogue(LINES)

    assert tracks[0]["start_seconds"] == 0.0
    assert tracks[0]["end_seconds"] == 1.9
    assert tracks[1]["start_seconds"] == 2.2
    assert tracks[1]["duration_seconds"] == pytest.approx(2.4)


@pytest.mark.asyncio
async def test_a_line_is_matched_to_its_own_segment_not_its_position(
    tmp_path, monkeypatch
):
    """Segments carry dialogue_input_index precisely because their order is
    not promised."""
    _Client.payload = {
        "audio_base64": AUDIO,
        "voice_segments": [
            {"dialogue_input_index": 1, "start_time_seconds": 2.2, "end_time_seconds": 4.6},
            {"dialogue_input_index": 0, "start_time_seconds": 0.0, "end_time_seconds": 1.9},
        ],
    }
    tracks = await _generator(tmp_path, monkeypatch).generate_scene_dialogue(LINES)

    assert tracks[0]["end_seconds"] == 1.9
    assert tracks[1]["end_seconds"] == 4.6


@pytest.mark.asyncio
async def test_missing_segments_fall_back_to_an_estimate(tmp_path, monkeypatch):
    """No timings is a smaller loss than no dialogue."""
    _Client.payload = {"audio_base64": AUDIO}
    tracks = await _generator(tmp_path, monkeypatch).generate_scene_dialogue(LINES)

    assert "start_seconds" not in tracks[0]
    assert tracks[0]["duration_seconds"] > 0


@pytest.mark.asyncio
async def test_the_scene_audio_lands_on_disk_and_only_on_the_first_track(
    tmp_path, monkeypatch
):
    """One combined file per scene: the mixer plays what is in `audio_url`, so
    repeating it would speak the scene twice."""
    _Client.payload = {"audio_base64": AUDIO, "voice_segments": []}
    tracks = await _generator(tmp_path, monkeypatch).generate_scene_dialogue(LINES)

    path = tracks[0]["audio_url"]
    assert os.path.isfile(path)
    assert open(path, "rb").read() == b"ID3-not-really-an-mp3"
    assert "audio_url" not in tracks[1]


@pytest.mark.asyncio
async def test_the_providers_own_words_reach_the_caller(tmp_path, monkeypatch):
    """A voice failure that says nothing is what cost this feature three
    delivered dramas."""
    from tools.elevenlabs_voice_generator import ElevenLabsError

    _Client.status = 400
    _Client.payload = {"detail": {"message": "voice_id not found"}}

    with pytest.raises(ElevenLabsError, match="voice_id not found"):
        await _generator(tmp_path, monkeypatch).generate_scene_dialogue(LINES)


@pytest.mark.asyncio
async def test_casting_matches_the_gender_in_the_description(tmp_path, monkeypatch):
    """Same rule as the MuAPI path: a character written as a woman is not
    voiced by George."""
    from types import SimpleNamespace

    generator = _generator(tmp_path, monkeypatch)
    cast = generator.cast_characters(
        [
            SimpleNamespace(name="Mara", static_features="a woman in her late 30s"),
            SimpleNamespace(name="Tomas", static_features="a man in his 40s"),
        ]
    )

    assert cast["mara"] in generator.FEMALE_VOICE_IDS
    assert cast["tomas"] in generator.MALE_VOICE_IDS


@pytest.mark.asyncio
async def test_no_key_is_reported_rather_than_silently_skipped(tmp_path):
    from tools.elevenlabs_voice_generator import (
        ElevenLabsError,
        ElevenLabsVoiceGenerator,
    )

    generator = ElevenLabsVoiceGenerator("", working_dir=str(tmp_path))
    with pytest.raises(ElevenLabsError, match="not configured"):
        await generator.generate_scene_dialogue(LINES)


def test_the_provider_switch_defaults_to_muapi(monkeypatch):
    from pipelines.idea2video import _make_voice_generator
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    monkeypatch.delenv("MUSEFORGE_VOICE_PROVIDER", raising=False)
    assert isinstance(_make_voice_generator("k", False), MuAPIVoiceGenerator)


def test_the_provider_switch_opts_into_elevenlabs(monkeypatch, tmp_path):
    from pipelines.idea2video import _make_voice_generator
    from tools.elevenlabs_voice_generator import ElevenLabsVoiceGenerator

    monkeypatch.setenv("MUSEFORGE_VOICE_PROVIDER", "elevenlabs")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "key")
    generator = _make_voice_generator("k", False, str(tmp_path))

    assert isinstance(generator, ElevenLabsVoiceGenerator)
    assert generator.working_dir == str(tmp_path)


def test_measured_timings_are_read_as_scene_relative():
    """ElevenLabs measures from the start of the audio it just made -- this
    SCENE's audio, which the mixer lays down at the scene's offset. Read as
    absolute, every measured cue in the drama would pile onto the opening
    shot."""
    from pipelines import idea2video

    original = idea2video._scene_boundaries
    idea2video._scene_boundaries = lambda paths: [0.0, 6.0, 15.0]
    try:
        srt = idea2video.build_srt_from_dialogue_tracks(
            [
                {
                    "character": "Priya",
                    "line": "Step back from it.",
                    "scene_index": 1,
                    "start_seconds": 0.5,
                    "end_seconds": 2.4,
                }
            ],
            scene_paths=["a", "b"],
        )
    finally:
        idea2video._scene_boundaries = original

    assert "00:00:06,500 --> 00:00:08,400" in srt


def test_absolute_timings_from_a_caller_without_scenes_are_untouched():
    """A caller that timed the whole master itself passes no scene_index."""
    from pipelines.idea2video import build_srt_from_dialogue_tracks

    srt = build_srt_from_dialogue_tracks(
        [{"character": "Ava", "line": "Now.", "start_seconds": 4.0, "end_seconds": 5.0}]
    )

    assert "00:00:04,000 --> 00:00:05,000" in srt
