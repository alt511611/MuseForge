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


def test_a_sprawling_provider_body_is_collapsed_and_capped():
    """These arrive with the raw response body appended."""
    from pipelines.idea2video import MAX_REASON_CHARS, _provider_reason

    reason = _provider_reason(RuntimeError("failed\n  {'detail': " + "x" * 900 + "}"))

    assert "\n" not in reason
    assert len(reason) <= MAX_REASON_CHARS + 1  # + the ellipsis
    assert reason.startswith("failed")


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
