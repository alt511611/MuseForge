"""Why a silent drama stayed unexplainable for two paid renders.

The job knew exactly why voice generation failed -- it held the provider's
own message -- and told the user "Voice generation failed for every scene",
full stop. That sentence cannot be acted on by anyone: not the user, who
cannot tell an outage from a broken request, and not whoever fixes it, who
has to go digging in server logs for a message the job already had.

The second half is the envelope: a completed prediction was read for exactly
one key, so any other response shape became "Completed but no outputs" -- a
finished, paid-for generation discarded over its wrapper.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --- the reason reaches the user ----------------------------------------


def test_the_provider_message_is_attached_to_the_warning():
    from pipelines.idea2video import _reason_suffix

    suffix = _reason_suffix(["MuAPI job failed: voice_id not found"])

    assert "voice provider reported" in suffix
    assert "voice_id not found" in suffix


def test_identical_failures_are_reported_once():
    """A malformed request fails every scene the same way; five copies of one
    sentence is wallpaper, not information."""
    from pipelines.idea2video import _reason_suffix

    suffix = _reason_suffix(["422 unprocessable"])

    assert suffix.count("422 unprocessable") == 1


def test_no_reason_leaves_the_warning_exactly_as_it_was():
    from pipelines.idea2video import _reason_suffix

    assert _reason_suffix([]) == ""


def test_the_mdn_boilerplate_does_not_crowd_out_the_real_message():
    """Production, verbatim: a 400 reached the user as httpx's link to MDN's
    status-code page, with the provider's own explanation truncated off."""
    from pipelines.idea2video import _provider_reason

    reason = _provider_reason(
        RuntimeError(
            "Client error '400 Bad Request' for url 'https://api.muapi.ai/x' "
            "For more information check: "
            "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/400 "
            "| Response body: {'detail': 'prediction not found'}"
        )
    )

    assert "developer.mozilla.org" not in reason
    assert "prediction not found" in reason


def test_a_sprawling_provider_body_is_collapsed_and_capped():
    """These arrive with the raw response body appended."""
    from pipelines.idea2video import MAX_REASON_CHARS, _provider_reason

    reason = _provider_reason(RuntimeError("failed\n  {'detail': " + "x" * 900 + "}"))

    assert "\n" not in reason
    assert len(reason) <= MAX_REASON_CHARS + 1  # + the ellipsis
    assert reason.startswith("failed")


def test_the_retry_prefix_does_not_crowd_out_the_real_message():
    """Our own wrapper's 40 characters say nothing the user can act on."""
    from pipelines.idea2video import _provider_reason

    reason = _provider_reason(
        RuntimeError("MuAPI request failed after 1 attempt(s): HTTP 400: nope")
    )

    assert reason == "HTTP 400: nope"


def test_the_message_survives_the_envelope_it_arrived_in():
    """Production, verbatim: 214 characters of wrapper in front of the one
    clause that mattered, which is exactly where the cap fell."""
    from pipelines.idea2video import MAX_REASON_CHARS, _provider_reason
    from tools.muapi_client import provider_message

    body = (
        '{"detail":{"id":"bdb3d5cf-8bce-4263-9252-37c896a2aae4",'
        '"status":"failed","error":"Invalid voice parameter: '
        "'JBFqnCBsd6RMkjVDRZzb' is not one of the allowed values\"}}"
    )
    reason = _provider_reason(
        RuntimeError(
            "MuAPI request failed after 1 attempt(s): HTTP 400: "
            + provider_message(body)
        )
    )

    assert "is not one of the allowed values" in reason
    assert "bdb3d5cf" not in reason
    assert len(reason) <= MAX_REASON_CHARS + 1


# --- the provider's own words --------------------------------------------


def test_a_failed_prediction_is_unwrapped_to_its_error():
    from tools.muapi_client import provider_message

    assert provider_message(
        '{"detail":{"id":"x","status":"failed","error":"Invalid voice parameter"}}'
    ) == "Invalid voice parameter"


def test_a_validation_error_keeps_its_field_message():
    from tools.muapi_client import provider_message

    assert provider_message('{"detail":[{"loc":["body","dialogue"],'
                            '"msg":"field required"}]}') == "field required"


def test_a_plain_detail_string_is_read_as_the_message():
    from tools.muapi_client import provider_message

    assert provider_message('{"detail":"prediction not found"}') == (
        "prediction not found"
    )


def test_a_body_that_is_not_json_is_left_for_the_raw_fallback():
    from tools.muapi_client import provider_message

    assert provider_message("<html>502 Bad Gateway</html>") == ""
    assert provider_message("") == ""


def test_a_json_body_with_no_message_field_is_left_alone():
    """Better the raw body than a confidently wrong summary of it."""
    from tools.muapi_client import provider_message

    assert provider_message('{"status":"failed","code":7}') == ""


def test_the_http_failure_leads_with_what_the_provider_said():
    import httpx

    from tools.muapi_client import MuAPIClient

    request = httpx.Request("GET", "https://api.muapi.ai/api/v1/predictions/u/result")
    response = httpx.Response(
        400,
        request=request,
        text='{"detail":{"id":"u","status":"failed","error":"Invalid voice"}}',
    )
    exc = httpx.HTTPStatusError("400", request=request, response=response)

    described = MuAPIClient._describe(exc)

    # The sentence leads; the path follows it, because "refused at submit" and
    # "refused after the scene was generated" otherwise read identically.
    assert described.startswith("HTTP 400: Invalid voice")
    assert "/api/v1/predictions/u/result" in described


def test_a_wordless_failure_still_reports_status_and_path():
    """No message to lead with means the old shape is all there is."""
    import httpx

    from tools.muapi_client import MuAPIClient

    request = httpx.Request("POST", "https://api.muapi.ai/api/v1/flux-3")
    response = httpx.Response(500, request=request, text="upstream exploded")
    exc = httpx.HTTPStatusError("500", request=request, response=response)

    described = MuAPIClient._describe(exc)

    assert "/api/v1/flux-3" in described
    assert "upstream exploded" in described


# --- the envelope --------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"outputs": ["https://cdn/a.mp3"]},
        {"outputs": [{"url": "https://cdn/a.mp3"}]},
        {"output": "https://cdn/a.mp3"},
        {"result": {"audio_url": "https://cdn/a.mp3"}},
        {"url": "https://cdn/a.mp3"},
    ],
)
def test_a_finished_generation_is_found_whatever_wraps_it(payload):
    from tools.muapi_client import extract_output_urls

    assert extract_output_urls(payload) == ["https://cdn/a.mp3"]


def test_the_image_and_video_shape_is_still_read_first():
    """Their behaviour must not move: `outputs` wins even when the response
    also carries something else that looks like a URL."""
    from tools.muapi_client import extract_output_urls

    urls = extract_output_urls(
        {"outputs": ["https://cdn/real.png"], "url": "https://cdn/thumbnail.png"}
    )

    assert urls == ["https://cdn/real.png"]


def test_multiple_outputs_keep_their_order():
    from tools.muapi_client import extract_output_urls

    assert extract_output_urls(
        {"outputs": ["https://cdn/1.mp3", {"audio_url": "https://cdn/2.mp3"}]}
    ) == ["https://cdn/1.mp3", "https://cdn/2.mp3"]


def test_an_empty_prediction_is_still_an_error():
    """Fail-open on the envelope must not become fail-open on nothing."""
    from tools.muapi_client import extract_output_urls

    assert extract_output_urls({"status": "completed", "outputs": []}) == []
    assert extract_output_urls({"status": "completed"}) == []


# --- a job that finishes inline ------------------------------------------


@pytest.mark.asyncio
async def test_an_inline_answer_is_used_instead_of_polling_for_it():
    """Production symptom: a successful submit, then 400 Bad Request on
    /predictions/{id}/result — the id belonged to a record that was never
    queued as a prediction, because the job had already finished."""
    from unittest.mock import AsyncMock

    from tools.muapi_client import MuAPIClient

    client = MuAPIClient("test-key")
    client._submit_raw = AsyncMock(
        return_value={"id": "abc", "audio_url": "https://cdn/scene.mp3"}
    )
    client.poll_result = AsyncMock(side_effect=AssertionError("must not poll"))

    assert await client.generate("elevenlabs-text-to-dialogue-v3", {}) == (
        "https://cdn/scene.mp3"
    )


@pytest.mark.asyncio
async def test_a_queued_job_is_polled_exactly_as_before():
    """Images and video must not move: a ticket with no file means poll."""
    from unittest.mock import AsyncMock

    from tools.muapi_client import MuAPIClient

    client = MuAPIClient("test-key")
    client._submit_raw = AsyncMock(return_value={"request_id": "req-1"})
    client.poll_result = AsyncMock(return_value=["https://cdn/frame.png"])

    assert await client.generate("flux-3", {}) == "https://cdn/frame.png"
    assert client.poll_result.await_args.args[0] == "req-1"


@pytest.mark.asyncio
async def test_an_answer_with_neither_file_nor_ticket_is_an_error():
    from unittest.mock import AsyncMock

    from tools.muapi_client import MuAPIClient, MuAPIError

    client = MuAPIClient("test-key")
    client._submit_raw = AsyncMock(return_value={"status": "queued"})

    with pytest.raises(MuAPIError, match="No request_id"):
        await client.generate("flux-3", {})


# --- end to end ----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_voice_layer_tells_the_user_what_the_provider_said(
    tmp_path, monkeypatch
):
    """The whole point: this warning is what the user actually reads."""
    from unittest.mock import AsyncMock

    from interfaces.character import DramaScript
    from pipelines import idea2video as pipeline_mod

    class FailingVoiceGenerator:
        def __init__(self, api_key, demo=False):
            pass

        def cast_characters(self, characters):
            return {}

        async def generate_scene_dialogue(self, dialogue, is_cancelled=None, language="en"):
            raise RuntimeError(
                "MuAPI request failed after 1 attempt(s): 422 | Response "
                "body: {'detail': 'voice_id is not valid'}"
            )

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")
    monkeypatch.setattr(pipeline_mod, "MuAPIVoiceGenerator", FailingVoiceGenerator)

    pipeline = pipeline_mod.Idea2VideoPipeline("test-key")
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline._lock_location_plate = AsyncMock(return_value=None)
    pipeline.script2video.run = AsyncMock(
        return_value={"path": "scene.mp4", "shots": []}
    )
    pipeline._assemble_final_drama = AsyncMock(return_value=str(tmp_path / "out.mp4"))

    result = await pipeline.continue_from_script(
        DramaScript(
            title="T",
            logline="L",
            scenes=[
                {
                    "action": "She opens it.",
                    "dialogue": [{"character": "Mara", "line": "It's warm."}],
                }
            ],
        ),
        working_dir=str(tmp_path / "job"),
        dialogue_enabled=True,
    )

    warning = next(w for w in result["warnings"] if "Voice generation failed" in w)
    assert "voice_id is not valid" in warning


# --- the words survive the voice -----------------------------------------


def test_a_failed_scene_still_produces_caption_rows():
    from pipelines.idea2video import caption_only_tracks

    tracks = caption_only_tracks(
        [
            {"character": "Mara", "line": "It's warm."},
            {"character": "Mara", "line": "   "},
            {"character": "Dispatch", "line": "Say again?"},
        ],
        scene_index=2,
    )

    assert [t["line"] for t in tracks] == ["It's warm.", "Say again?"]
    assert all(t["scene_index"] == 2 for t in tracks)
    # No audio, ever: these must not be able to reach the mixer or the
    # lipsync pass, both of which key off audio_url.
    assert not any("audio_url" in t for t in tracks)


def test_caption_rows_are_not_mistaken_for_speech():
    from pipelines.idea2video import has_voiced_track

    captions = [{"line": "It's warm.", "scene_index": 0, "caption_only": True}]
    assert has_voiced_track(captions) is False
    assert has_voiced_track(captions + [{"audio_url": "https://cdn/a.mp3"}]) is True
    assert has_voiced_track([]) is False


def test_caption_rows_reach_the_srt_with_estimated_timings():
    """There is no recording to measure, so the SRT has to time the words
    themselves -- which it already does for every line after a scene's
    first."""
    from pipelines.idea2video import build_srt_from_dialogue_tracks, caption_only_tracks

    srt = build_srt_from_dialogue_tracks(
        caption_only_tracks(
            [
                {"character": "Mara", "line": "It's warm."},
                {"character": "Mara", "line": "Something is alive in there."},
            ],
            scene_index=0,
        )
    )

    assert "Mara: It's warm." in srt
    assert "Mara: Something is alive in there." in srt
    assert "00:00:00,000 -->" in srt
    # The second cue starts after the first, not on top of it.
    assert srt.count("-->") == 2


@pytest.mark.asyncio
async def test_a_dead_voice_provider_ships_a_subtitled_film_not_a_mime_show(
    tmp_path, monkeypatch
):
    """The delivered video that prompted this: every voice request failed, so
    the drama shipped silent AND with no trace of the lines that were
    written."""
    from unittest.mock import AsyncMock

    from interfaces.character import DramaScript
    from pipelines import idea2video as pipeline_mod

    class FailingVoiceGenerator:
        def __init__(self, api_key, demo=False):
            pass

        def cast_characters(self, characters):
            return {}

        async def generate_scene_dialogue(self, dialogue, is_cancelled=None, language="en"):
            raise RuntimeError("HTTP 400: Invalid voice parameter")

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")
    monkeypatch.setattr(pipeline_mod, "MuAPIVoiceGenerator", FailingVoiceGenerator)

    captured = {}

    async def _assemble(*args, **kwargs):
        captured["dialogue_tracks"] = kwargs.get("dialogue_tracks")
        return str(tmp_path / "out.mp4")

    pipeline = pipeline_mod.Idea2VideoPipeline("test-key")
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline._lock_location_plate = AsyncMock(return_value=None)
    pipeline.script2video.run = AsyncMock(
        return_value={"path": "scene.mp4", "shots": []}
    )
    pipeline._assemble_final_drama = _assemble

    result = await pipeline.continue_from_script(
        DramaScript(
            title="T",
            logline="L",
            scenes=[
                {
                    "action": "She opens it.",
                    "dialogue": [{"character": "Mara", "line": "It's warm."}],
                }
            ],
        ),
        working_dir=str(tmp_path / "job"),
        dialogue_enabled=True,
    )

    tracks = captured["dialogue_tracks"]
    assert [t["line"] for t in tracks] == ["It's warm."]
    assert not pipeline_mod.has_voiced_track(tracks)
    warning = next(w for w in result["warnings"] if "Voice generation failed" in w)
    assert "captions" in warning
    assert "Invalid voice parameter" in warning


@pytest.mark.asyncio
async def test_a_master_with_nothing_to_mix_still_carries_an_audio_stream(tmp_path):
    """The delivered file had no audio stream at all -- music off plus a dead
    voice provider. A track of silence is the same thing to a viewer and a
    different thing to every editor and upload pipeline that reads the file."""
    from moviepy import ColorClip, VideoFileClip

    from pipelines.idea2video import add_background_music

    source = str(tmp_path / "mute.mp4")
    ColorClip(size=(160, 90), color=(10, 10, 10), duration=1).write_videofile(
        source, fps=12, codec="libx264", audio=False, logger=None
    )
    output = str(tmp_path / "mixed.mp4")

    await add_background_music(source, output, None)

    with VideoFileClip(output) as clip:
        assert clip.audio is not None
