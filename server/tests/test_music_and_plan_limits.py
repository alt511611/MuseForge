"""Tests for optional background music and Creator/Pro plan differentiation.

Covers:
- Plan-based num_scenes limits (Free/Creator = 3, Pro = 5)
- music_enabled is silently ignored for Free plan (no extra credit, no error)
- music_enabled adds a flat +1 credit surcharge for Creator/Pro
- None of this ever triggers in demo mode
"""
import os
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.pop("MUSEFORGE_DEMO", None)
os.environ.pop("MUAPI_KEY", None)


def _auth_headers():
    return {"Authorization": "Bearer fake-token"}


@contextmanager
def _patch_auth_user(user_id="user-1", email="u@example.com"):
    """Override the get_optional_user FastAPI dependency.

    Patching the module attribute wouldn't work here since `Depends(...)`
    captures the original function object at route-registration time.
    """
    import api as _api
    from auth import AuthUser

    async def _fake_user():
        return AuthUser(user_id, email)

    _api.app.dependency_overrides[_api.get_optional_user] = _fake_user
    try:
        yield
    finally:
        _api.app.dependency_overrides.pop(_api.get_optional_user, None)


@pytest.mark.asyncio
async def test_free_plan_scene_limit_enforced():
    import api as _api
    from fastapi.testclient import TestClient

    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real_key"}), \
         patch.object(_api, "_get_user_plan", AsyncMock(return_value="free")), \
         patch.object(_api, "_deduct_credits", AsyncMock(return_value=True)), \
         patch.object(_api, "run_generation_job", AsyncMock()), \
         _patch_auth_user(user_id="user-free-limit"):

        tc = TestClient(_api.app, raise_server_exceptions=False)
        resp = tc.post(
            "/api/generate",
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 4},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert "3 scenes" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_creator_plan_capped_at_three_scenes():
    import api as _api
    from fastapi.testclient import TestClient

    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real_key"}), \
         patch.object(_api, "_get_user_plan", AsyncMock(return_value="creator")), \
         patch.object(_api, "_deduct_credits", AsyncMock(return_value=True)), \
         patch.object(_api, "run_generation_job", AsyncMock()), \
         _patch_auth_user(user_id="user-creator-cap"):

        tc = TestClient(_api.app, raise_server_exceptions=False)
        resp_ok = tc.post(
            "/api/generate",
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 3},
            headers=_auth_headers(),
        )
        assert resp_ok.status_code == 200

        resp_over = tc.post(
            "/api/generate",
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 5},
            headers=_auth_headers(),
        )
        assert resp_over.status_code == 400


@pytest.mark.asyncio
async def test_pro_plan_allows_five_scenes():
    import api as _api
    from fastapi.testclient import TestClient

    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real_key"}), \
         patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")), \
         patch.object(_api, "_deduct_credits", AsyncMock(return_value=True)), \
         patch.object(_api, "run_generation_job", AsyncMock()), \
         _patch_auth_user(user_id="user-pro-scenes"):

        tc = TestClient(_api.app, raise_server_exceptions=False)
        resp = tc.post(
            "/api/generate",
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 5},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_music_enabled_silently_ignored_for_free_plan():
    """Free plan + music_enabled=True → no extra credit, no error, music dropped."""
    import api as _api
    from fastapi.testclient import TestClient

    deduct_mock = AsyncMock(return_value=True)

    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real_key"}), \
         patch.object(_api, "_get_user_plan", AsyncMock(return_value="free")), \
         patch.object(_api, "_deduct_credits", deduct_mock), \
         patch.object(_api, "run_generation_job", AsyncMock()), \
         _patch_auth_user(user_id="user-music-free"):

        tc = TestClient(_api.app, raise_server_exceptions=False)
        resp = tc.post(
            "/api/generate",
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 2, "music_enabled": True},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        # Only the scene credits were deducted — no +1 music surcharge.
        deduct_mock.assert_awaited_once_with("user-music-free", 2, "video_generation")


@pytest.mark.asyncio
async def test_music_enabled_adds_flat_surcharge_for_creator():
    import api as _api
    from fastapi.testclient import TestClient

    deduct_mock = AsyncMock(return_value=True)

    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real_key"}), \
         patch.object(_api, "_get_user_plan", AsyncMock(return_value="creator")), \
         patch.object(_api, "_deduct_credits", deduct_mock), \
         patch.object(_api, "run_generation_job", AsyncMock()), \
         _patch_auth_user(user_id="user-music-creator"):

        tc = TestClient(_api.app, raise_server_exceptions=False)
        resp = tc.post(
            "/api/generate",
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 2, "music_enabled": True},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200
        # num_scenes (2) + flat music surcharge (1) = 3 credits deducted.
        deduct_mock.assert_awaited_once_with("user-music-creator", 3, "video_generation")


@pytest.mark.asyncio
async def test_music_never_triggers_in_demo_mode():
    """Demo mode requests never touch plan lookup or credit deduction."""
    import api as _api
    from fastapi.testclient import TestClient

    plan_mock = AsyncMock(return_value="pro")

    with patch.object(_api, "DEMO_FLAG", True), \
         patch.object(_api, "_get_user_plan", plan_mock):

        tc = TestClient(_api.app, raise_server_exceptions=False)
        resp = tc.post(
            "/api/generate",
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 2, "music_enabled": True},
        )
        assert resp.status_code == 200
        plan_mock.assert_not_awaited()
