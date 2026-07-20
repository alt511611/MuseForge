"""Reference frames use flux-pulid, with flux-dev-image fail-open fallback."""

import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.mark.asyncio
async def test_reference_generation_uses_flux_pulid_schema():
    from tools.muapi_image_generator import MuAPIImageGenerator

    generator = MuAPIImageGenerator(api_key="test-key", demo=False)
    generator.client.generate = AsyncMock(return_value="https://cdn.example/frame.png")

    result = await generator.generate_image_with_reference(
        prompt="Maya walks along the pier",
        reference_url="https://cdn.example/maya-portrait.png",
        aspect_ratio="9:16",
    )

    assert result == "https://cdn.example/frame.png"
    call = generator.client.generate.await_args
    assert call.args[0] == generator.KONTEXT_ENDPOINT
    assert generator.KONTEXT_ENDPOINT == "flux-pulid"
    payload = call.args[1]
    assert payload["image_url"] == "https://cdn.example/maya-portrait.png"
    assert payload["aspect_ratio"] == "9:16"
    assert "image" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [404, 422])
async def test_flux_pulid_rejection_falls_back_to_flux_dev(status):
    from tools.muapi_client import MuAPIError
    from tools.muapi_image_generator import MuAPIImageGenerator

    generator = MuAPIImageGenerator(api_key="test-key", demo=False)
    generator.client.generate = AsyncMock(
        side_effect=[
            MuAPIError(f"MuAPI request failed: {status} endpoint/schema rejected"),
            "https://cdn.example/fallback-frame.png",
        ]
    )

    result = await generator.generate_image_with_reference(
        prompt="Maya walks along the pier",
        reference_url="https://cdn.example/maya-portrait.png",
        aspect_ratio="16:9",
    )

    assert result == "https://cdn.example/fallback-frame.png"
    assert generator.client.generate.await_count == 2

    pulid_call, fallback_call = generator.client.generate.await_args_list
    assert pulid_call.args[0] == generator.KONTEXT_ENDPOINT
    assert pulid_call.args[1]["image_url"] == (
        "https://cdn.example/maya-portrait.png"
    )

    assert fallback_call.args[0] == generator.IMAGE_ENDPOINT
    fallback_payload = fallback_call.args[1]
    assert fallback_payload["image"] == "https://cdn.example/maya-portrait.png"
    assert "image_url" not in fallback_payload
    assert fallback_payload["size"] == "1344*768"


@pytest.mark.asyncio
async def test_flux_pulid_internal_runtime_failure_falls_back_to_flux_dev():
    """Accepted PuLID jobs that fail internally must not fail the whole job."""
    from tools.muapi_client import MuAPIError
    from tools.muapi_image_generator import MuAPIImageGenerator

    generator = MuAPIImageGenerator(api_key="test-key", demo=False)
    generator.client.generate = AsyncMock(
        side_effect=[
            MuAPIError(
                'MuAPI generation failed: {"status": "failed", '
                '"error": "Internal error while processing image"}'
            ),
            "https://cdn.example/fallback-frame.png",
        ]
    )

    result = await generator.generate_image_with_reference(
        prompt="Maya walks along the pier",
        reference_url="https://cdn.example/maya-portrait.png",
        aspect_ratio="16:9",
    )

    assert result == "https://cdn.example/fallback-frame.png"
    assert generator.client.generate.await_count == 2
    pulid_call, fallback_call = generator.client.generate.await_args_list
    assert pulid_call.args[0] == generator.KONTEXT_ENDPOINT
    assert fallback_call.args[0] == generator.IMAGE_ENDPOINT
    assert fallback_call.args[1]["image"] == (
        "https://cdn.example/maya-portrait.png"
    )


@pytest.mark.asyncio
async def test_non_schema_flux_pulid_error_is_not_hidden():
    from tools.muapi_client import MuAPIError
    from tools.muapi_image_generator import MuAPIImageGenerator

    generator = MuAPIImageGenerator(api_key="test-key", demo=False)
    generator.client.generate = AsyncMock(
        side_effect=MuAPIError("MuAPI request failed: 500 provider unavailable")
    )

    with pytest.raises(MuAPIError):
        await generator.generate_image_with_reference(
            prompt="Maya walks",
            reference_url="https://cdn.example/maya.png",
        )

    assert generator.client.generate.await_count == 1
