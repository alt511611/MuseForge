"""Pro character library API tests."""
import os
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["MUSEFORGE_DEMO"] = "1"
os.environ.pop("MUAPI_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

import api as _api  # noqa: E402
from auth import AuthUser  # noqa: E402

client = TestClient(_api.app)


@contextmanager
def _auth_as(user_id="user-pro-1", email="pro@example.com"):
    async def _fake_user():
        return AuthUser(user_id, email)

    _api.app.dependency_overrides[_api.get_current_user] = _fake_user
    try:
        yield
    finally:
        _api.app.dependency_overrides.pop(_api.get_current_user, None)


@pytest.fixture(autouse=True)
def _clear_library_mem():
    _api._character_library_mem.clear()
    yield
    _api._character_library_mem.clear()


def test_create_character_forbidden_for_non_pro():
    with _auth_as(), patch.object(_api, "_get_user_plan", AsyncMock(return_value="creator")):
        resp = client.post(
            "/api/characters",
            json={
                "name": "Ava",
                "static_features": "tall woman, dark hair",
                "portrait_url": "https://cdn.example/ava.png",
            },
        )
    assert resp.status_code == 403


def test_create_list_delete_character_for_pro():
    with _auth_as(), patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")):
        create = client.post(
            "/api/characters",
            json={
                "name": "Ava",
                "static_features": "tall woman, dark hair",
                "portrait_url": "https://cdn.example/ava.png",
            },
        )
        assert create.status_code == 200
        body = create.json()
        assert body["name"] == "Ava"
        assert body["static_features"] == "tall woman, dark hair"
        assert body["portrait_url"] == "https://cdn.example/ava.png"
        assert body["id"]

        listed = client.get("/api/characters")
        assert listed.status_code == 200
        chars = listed.json()["characters"]
        assert len(chars) == 1
        assert chars[0]["id"] == body["id"]

        deleted = client.delete(f"/api/characters/{body['id']}")
        assert deleted.status_code == 200
        assert deleted.json()["ok"] is True

        listed2 = client.get("/api/characters")
        assert listed2.json()["characters"] == []


def test_list_characters_empty_for_free_plan():
    # Seed mem as if a prior Pro session saved something — Free must still see [].
    _api._character_library_mem["user-free-1"] = [
        {
            "id": "x",
            "name": "Hidden",
            "static_features": "x",
            "portrait_url": "https://cdn.example/x.png",
        }
    ]
    with _auth_as("user-free-1"), patch.object(
        _api, "_get_user_plan", AsyncMock(return_value="free")
    ):
        resp = client.get("/api/characters")
    assert resp.status_code == 200
    assert resp.json()["characters"] == []


@pytest.mark.asyncio
async def test_screenwriter_uses_preset_characters_in_demo():
    from agents.screenwriter import ScreenwriterAgent

    agent = ScreenwriterAgent(demo=True)
    script = await agent.write_script(
        "A reunion at the pier",
        style="Cinematic",
        num_scenes=2,
        preset_characters=[
            {
                "name": "Kemal",
                "static_features": "weathered fisherman, grey beard",
                "portrait_url": "https://cdn.example/kemal.png",
            }
        ],
    )
    assert script.characters[0].name == "Kemal"
    assert "grey beard" in script.characters[0].description
    assert "PRESET CHARACTERS" in ScreenwriterAgent.SYSTEM_PROMPT
    assert "do NOT redefine" in ScreenwriterAgent.SYSTEM_PROMPT


def test_generate_drops_library_characters_outside_pro():
    """Demo/anon generate must ignore library_characters (Pro-only)."""
    resp = client.post(
        "/api/generate",
        json={
            "idea": "A quiet story unfolds at dawn by the sea",
            "num_scenes": 2,
            "library_characters": [
                {
                    "name": "Ava",
                    "static_features": "tall",
                    "portrait_url": "https://cdn.example/ava.png",
                }
            ],
        },
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    job = _api.job_store.get(job_id)
    assert job is not None
    assert job.library_characters == []
