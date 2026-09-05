"""Leaving MuAPI: the foley backend, and what a lip-sync endpoint is sent.

Foley was the last stage with no fal.ai route, so a deployment that had moved
video, images, music, voice and lip sync still had to hold a MUAPI_KEY alive
for a call that costs one cent a scene. What has to hold:

1. The foley provider is SELECTABLE and the default does not move.
2. The two routes agree about what foley IS -- same model, same prompt, same
   clamp -- because they are two roads to MMAudio v2, not two sound designs.
3. A lip-sync endpoint is sent only the fields it declares. fal validates the
   input, so an undeclared field is a 422, the module fails open, and every
   speaking scene in the drama quietly keeps a closed mouth.
4. A LOCAL audio path is uploaded, not sent. The direct ElevenLabs voice
   provider hands the pipeline bytes on disk, and that pairing -- ElevenLabs
   voice + fal lip sync -- is exactly where a deployment leaving MuAPI lands.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")
os.environ.setdefault("FAL_KEY", "fal-key-not-real")

import tools.falai_lipsync as fal_lipsync  # noqa: E402
import tools.falai_sfx_generator as fal_sfx  # noqa: E402
import tools.muapi_sfx_generator as sfx  # noqa: E402


# --- 1. the foley provider is selectable ---------------------------------


def test_foley_still_goes_to_muapi_unless_asked_otherwise(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_SFX_PROVIDER", raising=False)
    assert isinstance(sfx.make_sfx_generator("k"), sfx.MuAPISFXGenerator)


def test_foley_can_be_moved_to_fal_with_one_env_var(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_SFX_PROVIDER", "falai")
    monkeypatch.setenv("FAL_KEY", "fal-key-not-real")
    assert isinstance(sfx.make_sfx_generator(""), fal_sfx.FalAISFXGenerator)


def test_an_unknown_provider_name_is_not_a_broken_deployment(monkeypatch):
    """A typo picks the default rather than raising on every job with sound."""
    monkeypatch.setenv("MUSEFORGE_SFX_PROVIDER", "fal.ai")
    assert isinstance(sfx.make_sfx_generator("k"), sfx.MuAPISFXGenerator)


# --- 2. the same sound, by a different road ------------------------------


def test_both_routes_ask_for_the_same_model():
    """MuAPI's slug is bare, fal's is prefixed. Neither is a default for the
    other -- the unprefixed spelling 404s on fal, per scene."""
    assert sfx.SFX_ENDPOINT == "mmaudio-v2/text-to-audio"
    assert fal_sfx.SFX_ENDPOINT == "fal-ai/mmaudio-v2/text-to-audio"


def test_the_prompt_and_the_clamp_are_shared_not_copied():
    """Two copies would drift, and the drift would be foley arriving with its
    own score under the score."""
    assert fal_sfx.build_prompt is sfx.build_prompt
    assert fal_sfx.clamp_duration is sfx.clamp_duration
    assert fal_sfx.is_foley_enabled is sfx.is_foley_enabled


@pytest.mark.asyncio
async def test_demo_mode_generates_nothing_on_either_route():
    generator = fal_sfx.FalAISFXGenerator(api_key="", demo=True)
    assert await generator.generate_scene_sfx("a door slamming", 6.0) == ""


@pytest.mark.asyncio
async def test_foley_asks_for_the_scenes_own_length_and_refuses_music(monkeypatch):
    sent = {}

    async def _fake_generate(client, endpoint, payload, **kwargs):
        sent["endpoint"] = endpoint
        sent["payload"] = payload
        return {"audio": {"url": "https://fal.media/foley.wav"}}

    monkeypatch.setattr(fal_sfx, "fal_generate", _fake_generate)
    generator = fal_sfx.FalAISFXGenerator(api_key="fal-key-not-real")
    url = await generator.generate_scene_sfx("a glass breaking on tile", 6.4)

    assert url == "https://fal.media/foley.wav"
    assert sent["endpoint"] == "fal-ai/mmaudio-v2/text-to-audio"
    assert sent["payload"]["duration"] == 6
    assert "NO music" in sent["payload"]["prompt"]
    assert "music" in sent["payload"]["negative_prompt"]


@pytest.mark.asyncio
async def test_a_completed_call_with_no_audio_is_a_failure_not_a_silent_scene(
    monkeypatch,
):
    async def _fake_generate(client, endpoint, payload, **kwargs):
        return {"audio": None}

    monkeypatch.setattr(fal_sfx, "fal_generate", _fake_generate)
    generator = fal_sfx.FalAISFXGenerator(api_key="fal-key-not-real")
    with pytest.raises(RuntimeError):
        await generator.generate_scene_sfx("a door", 8.0)


# --- 3. only the fields the endpoint declares ----------------------------


def test_the_syncso_endpoint_gets_the_knob_that_protects_the_length():
    payload = fal_lipsync.build_payload(
        "https://v/1.mp4", "https://a/1.mp3", "fal-ai/sync-lipsync/v2"
    )
    assert payload["sync_mode"] == "silence"
    assert payload["model"] == "lipsync-2"


def test_latentsync_is_sent_two_fields_because_it_declares_two():
    """It exposes no sync_mode and no model. Sending either is a 422, and a
    422 here reads as "no lip sync in this drama"."""
    payload = fal_lipsync.build_payload(
        "https://v/1.mp4", "https://a/1.mp3", "fal-ai/latentsync"
    )
    assert payload == {"video_url": "https://v/1.mp4", "audio_url": "https://a/1.mp3"}


def test_the_pro_variant_takes_sync_mode_but_not_a_model_name():
    payload = fal_lipsync.build_payload(
        "https://v/1.mp4", "https://a/1.mp3", "fal-ai/sync-lipsync/v2/pro"
    )
    assert payload["sync_mode"] == "silence"
    assert "model" not in payload


def test_an_endpoint_we_have_no_schema_for_gets_the_narrowest_payload():
    """Guessing wide costs the whole feature; guessing narrow costs a knob."""
    payload = fal_lipsync.build_payload(
        "https://v/1.mp4", "https://a/1.mp3", "some/model-published-next-week"
    )
    assert payload == {"video_url": "https://v/1.mp4", "audio_url": "https://a/1.mp3"}


def test_the_poll_ceiling_is_not_inside_the_providers_own_spread():
    """360s was a coin toss on measured syncs of ~322s and ~367s. Scenes sync
    concurrently, so patience costs the slowest scene, not their sum."""
    assert fal_lipsync.DEFAULT_MAX_POLLS * fal_lipsync.DEFAULT_POLL_INTERVAL >= 720


# --- 4. a local voice track is uploaded, not sent ------------------------


class _FakeHandle:
    request_id = "req-1"


class _FakeCompleted:
    error = None


class _FakeFalClient:
    """Records what was uploaded and what was submitted."""

    def __init__(self):
        self.uploaded = []
        self.submitted = None

    async def upload_file(self, path):
        self.uploaded.append(path)
        return f"https://fal.media/uploaded/{os.path.basename(path)}"

    async def submit(self, endpoint, arguments):
        self.submitted = (endpoint, arguments)
        return _FakeHandle()

    async def status(self, endpoint, request_id, with_logs=False):
        return _FakeCompleted()

    async def result(self, endpoint, request_id):
        return {"video": {"url": "https://fal.media/synced.mp4"}}


@pytest.mark.asyncio
async def test_a_voice_track_on_disk_is_uploaded_before_the_sync(
    monkeypatch, tmp_path
):
    """ElevenLabs-direct writes dialogue into the job directory. Handed to fal
    verbatim it fails on every speaking scene, fails open, and the drama ships
    with closed mouths and no obvious cause."""
    monkeypatch.setattr(fal_lipsync.fal_client, "Completed", _FakeCompleted)
    clip = tmp_path / "scene_1.mp4"
    clip.write_bytes(b"video")
    voice = tmp_path / "scene_1_dialogue.mp3"
    voice.write_bytes(b"audio")

    backend = fal_lipsync.FalAILipsync(api_key="fal-key-not-real")
    fake = _FakeFalClient()
    backend.client = fake

    synced = await backend.sync(str(clip), str(voice))

    assert synced == "https://fal.media/synced.mp4"
    assert fake.uploaded == [str(clip), str(voice)]
    _, arguments = fake.submitted
    assert arguments["audio_url"].startswith("https://")


@pytest.mark.asyncio
async def test_a_voice_track_that_is_missing_costs_the_mouth_not_the_job(tmp_path):
    clip = tmp_path / "scene_1.mp4"
    clip.write_bytes(b"video")

    backend = fal_lipsync.FalAILipsync(api_key="fal-key-not-real")
    backend.client = _FakeFalClient()

    assert await backend.sync(str(clip), str(tmp_path / "gone.mp3")) is None


# --- 5. a misconfigured provider costs the layer, not the drama ----------


@pytest.mark.asyncio
async def test_foley_pointed_at_fal_with_no_key_still_delivers_the_film(monkeypatch):
    """MUSEFORGE_SFX_PROVIDER=falai with no FAL_KEY raises at CONSTRUCTION,
    outside the per-scene try. _generate_foley promises never to raise."""
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_FOLEY", "1")
    monkeypatch.setenv("MUSEFORGE_SFX_PROVIDER", "falai")
    monkeypatch.setenv("FAL_KEY", "")

    pipeline = object.__new__(Idea2VideoPipeline)
    pipeline.demo = False
    pipeline.api_key = "muapi-key-not-real"

    tracks = await pipeline._generate_foley(
        [{"clip_index": 0, "shots": [{"audio_desc": "a door"}]}],
        ["/tmp/scene_0.mp4"],
    )
    assert tracks == []


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(test_demo_mode_generates_nothing_on_either_route())
