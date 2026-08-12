"""Tests for optional background music and Creator/Pro plan differentiation.

Covers:
- Plan-based num_scenes limits (Free = 8, Creator = 16, Pro = 24)
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
async def test_free_plan_rejects_nine_scenes():
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
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 9},
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
        assert "8 scenes" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_creator_plan_capped_at_sixteen_scenes():
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
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 16},
            headers=_auth_headers(),
        )
        assert resp_ok.status_code == 200

        resp_over = tc.post(
            "/api/generate",
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 17},
            headers=_auth_headers(),
        )
        assert resp_over.status_code == 400
        assert "16 scenes" in resp_over.json()["detail"]


@pytest.mark.asyncio
async def test_pro_plan_allows_twenty_four_scenes():
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
            json={"idea": "A lone astronaut drifts through the void", "num_scenes": 24},
            headers=_auth_headers(),
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_estimate_warns_for_long_jobs():
    # The phase budgets live in interfaces/render_eta now, because the LIVE
    # countdown shown during a render is built from the same model -- see that
    # module for why one shared model is the point. api.py holds only the
    # warning threshold. Totals below are unchanged: prologue 55 + epilogue 35
    # is the old flat base of 90.
    import api as _api
    import interfaces.render_eta as _eta
    from fastapi.testclient import TestClient

    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real_key",
                                 "MUSEFORGE_SCENE_CONCURRENCY": "1"}):
        with patch.object(_eta, "SECONDS_PER_SCENE", 100.0), \
             patch.object(_eta, "PROLOGUE_SECONDS", 55.0), \
             patch.object(_eta, "EPILOGUE_SECONDS", 35.0), \
             patch.object(_eta, "MUSIC_SECONDS", 45.0), \
             patch.object(_eta, "DIALOGUE_PER_SCENE", 20.0), \
             patch.object(_api, "WAIT_WARNING_MINUTES", 15):
            tc = TestClient(_api.app, raise_server_exceptions=False)
            # Concurrency pinned to 1: 16 scenes → 90 + 16*100 = 1690s ≈ 28 min → warning
            resp = tc.post(
                "/api/estimate",
                json={"num_scenes": 16, "plan": "creator"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["estimated_seconds"] == 1690
            assert body["wait_warning_minutes"] == 28
            assert "28" in (body.get("wait_warning") or "")

            # Music adds residual wall-clock on eligible plans
            with_music = tc.post(
                "/api/estimate",
                json={"num_scenes": 16, "plan": "creator", "music_enabled": True},
            ).json()
            assert with_music["estimated_seconds"] == 1690 + 45

    # Default (parallel) rendering estimates by BATCH, so the same job is
    # promised far sooner: 16 scenes / concurrency 3 → 6 batches → 90+600.
    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real_key"}, clear=False):
        os.environ.pop("MUSEFORGE_SCENE_CONCURRENCY", None)
        with patch.object(_eta, "SECONDS_PER_SCENE", 100.0), \
             patch.object(_eta, "PROLOGUE_SECONDS", 55.0), \
             patch.object(_eta, "EPILOGUE_SECONDS", 35.0):
            tc = TestClient(_api.app, raise_server_exceptions=False)
            parallel = tc.post(
                "/api/estimate", json={"num_scenes": 16, "plan": "creator"}
            ).json()
            assert parallel["estimated_seconds"] == 690

            # Short jobs stay quiet (3 scenes / concurrency 3 → 1 batch)
            short = tc.post("/api/estimate", json={"num_scenes": 3, "plan": "free"})
            assert short.json()["estimated_seconds"] == 90 + 1 * 100
            assert short.json().get("wait_warning_minutes") is None


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


@pytest.mark.parametrize("plan", ["free", "creator"])
@pytest.mark.asyncio
async def test_dialogue_enabled_silently_ignored_below_pro(plan):
    """Free/Creator requests cannot activate or pay for the Pro dialogue layer."""
    import api as _api
    from fastapi.testclient import TestClient

    deduct_mock = AsyncMock(return_value=True)
    user_id = f"user-dialogue-{plan}"

    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(
             os.environ,
             {"MUAPI_KEY": "real_key", "MUSEFORGE_DIALOGUE_ENABLED": "1"},
         ), \
         patch.object(_api, "_get_user_plan", AsyncMock(return_value=plan)), \
         patch.object(_api, "_deduct_credits", deduct_mock), \
         patch.object(_api, "run_generation_job", AsyncMock()), \
         _patch_auth_user(user_id=user_id):

        tc = TestClient(_api.app, raise_server_exceptions=False)
        resp = tc.post(
            "/api/generate",
            json={
                "idea": "Two travelers argue at a moonlit station",
                "num_scenes": 2,
                "dialogue_enabled": True,
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        deduct_mock.assert_awaited_once_with(user_id, 2, "video_generation")
        job = _api.job_store.get(resp.json()["job_id"])
        assert job is not None
        assert job.dialogue_enabled is False


@pytest.mark.asyncio
async def test_dialogue_enabled_adds_per_scene_surcharge_for_pro():
    """Pro dialogue costs one extra credit for every requested scene."""
    import api as _api
    from fastapi.testclient import TestClient

    deduct_mock = AsyncMock(return_value=True)

    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(
             os.environ,
             {"MUAPI_KEY": "real_key", "MUSEFORGE_DIALOGUE_ENABLED": "1"},
         ), \
         patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")), \
         patch.object(_api, "_deduct_credits", deduct_mock), \
         patch.object(_api, "run_generation_job", AsyncMock()), \
         _patch_auth_user(user_id="user-dialogue-pro"):

        tc = TestClient(_api.app, raise_server_exceptions=False)
        resp = tc.post(
            "/api/generate",
            json={
                "idea": "Two travelers argue at a moonlit station",
                "num_scenes": 3,
                "dialogue_enabled": True,
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        # 3 scene credits + 3 dialogue credits.
        deduct_mock.assert_awaited_once_with(
            "user-dialogue-pro", 6, "video_generation"
        )
        job = _api.job_store.get(resp.json()["job_id"])
        assert job is not None
        assert job.dialogue_enabled is True


@pytest.mark.asyncio
async def test_dialogue_request_needs_infrastructure_flag():
    """A Pro request alone cannot bypass the deployment-level kill switch."""
    import api as _api
    from fastapi.testclient import TestClient

    deduct_mock = AsyncMock(return_value=True)

    with patch.object(_api, "DEMO_FLAG", False), \
         patch.dict(os.environ, {"MUAPI_KEY": "real_key"}, clear=True), \
         patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")), \
         patch.object(_api, "_deduct_credits", deduct_mock), \
         patch.object(_api, "run_generation_job", AsyncMock()), \
         _patch_auth_user(user_id="user-dialogue-kill-switch"):

        tc = TestClient(_api.app, raise_server_exceptions=False)
        resp = tc.post(
            "/api/generate",
            json={
                "idea": "Two travelers argue at a moonlit station",
                "num_scenes": 2,
                "dialogue_enabled": True,
            },
            headers=_auth_headers(),
        )

        assert resp.status_code == 200
        deduct_mock.assert_awaited_once_with(
            "user-dialogue-kill-switch", 2, "video_generation"
        )
        assert _api.job_store.get(resp.json()["job_id"]).dialogue_enabled is False


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
