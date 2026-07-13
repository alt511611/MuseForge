"""
Regression tests for the user-uploaded character photo feature:

  1) upload_base64_image decodes/validates a data URI and (in demo mode)
     returns a deterministic placeholder without a real network call;
  2) an invalid data URI raises InvalidCharacterPhoto instead of crashing;
  3) Idea2VideoPipeline uses the uploaded photo as the character's locked
     portrait instead of generating a fresh AI one;
  4) the full /api/generate -> demo job flow accepts character_image /
     character_name and completes successfully.

All MuAPI network calls are demo-mode (no API key or network access needed).
"""
import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")
os.environ["MUSEFORGE_DEMO"] = "1"

from interfaces.character import CharacterInScene  # noqa: E402
from tools.muapi_uploader import InvalidCharacterPhoto, upload_base64_image  # noqa: E402

TINY_PNG_B64 = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000a49444154789c6360000002000155a5f30a0000000"
    "049454e44ae426082"
)).decode()


@pytest.mark.asyncio
async def test_upload_base64_image_demo_mode_is_deterministic():
    data_uri = f"data:image/png;base64,{TINY_PNG_B64}"
    url1 = await upload_base64_image(data_uri, api_key="", demo=True)
    url2 = await upload_base64_image(data_uri, api_key="", demo=True)
    assert url1 == url2, "same photo should map to the same placeholder URL"
    assert url1.startswith("https://picsum.photos/seed/")


@pytest.mark.asyncio
async def test_upload_base64_image_rejects_garbage_input():
    with pytest.raises(InvalidCharacterPhoto):
        await upload_base64_image("not-a-data-uri", api_key="", demo=True)

    with pytest.raises(InvalidCharacterPhoto):
        await upload_base64_image("data:image/png;base64,not-valid-base64!!!", api_key="", demo=True)


@pytest.mark.asyncio
async def test_lock_character_portraits_uses_uploaded_photo(monkeypatch):
    from pipelines.idea2video import Idea2VideoPipeline

    calls = []

    async def fake_generate_image(self, prompt, aspect_ratio="1:1"):
        calls.append(prompt)
        return "https://fake.cdn/ai-generated-portrait.png"

    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image",
        fake_generate_image,
    )

    pipeline = Idea2VideoPipeline(api_key="test-key-not-real", demo=True)
    characters = [
        CharacterInScene(idx=0, name="Maya", static_features="30s woman", is_visible=True),
        CharacterInScene(idx=1, name="Kai", static_features="20s man", is_visible=True),
    ]

    portraits = await pipeline._lock_character_portraits(
        characters,
        style="Cinematic",
        character_portraits_override={"Maya": "https://uploaded.cdn/maya-photo.png"},
    )

    assert portraits["Maya"] == "https://uploaded.cdn/maya-photo.png"
    assert portraits["Kai"] == "https://fake.cdn/ai-generated-portrait.png"
    # Only Kai should have triggered an AI portrait generation call — Maya's
    # uploaded photo must NOT be overwritten by a fresh AI-generated one.
    assert len(calls) == 1
    assert characters[0].portrait_url == "https://uploaded.cdn/maya-photo.png"


@pytest.mark.asyncio
async def test_full_generation_flow_with_character_photo_demo(monkeypatch):
    from fastapi.testclient import TestClient
    import api

    client = TestClient(api.app)
    resp = client.post(
        "/api/generate",
        json={
            "idea": "A detective chases a shadow through a neon city.",
            "num_scenes": 2,
            "character_image": f"data:image/png;base64,{TINY_PNG_B64}",
            "character_name": "Detective Rae",
        },
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    import asyncio
    for _ in range(200):
        job = api.job_store.get(job_id)
        if job.status.value in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    job = api.job_store.get(job_id)
    assert job.status.value == "completed", job.error
    assert job.result is not None
