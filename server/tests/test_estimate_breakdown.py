"""Credit breakdown on POST /api/estimate."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["MUSEFORGE_DEMO"] = "1"
os.environ.pop("MUAPI_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402

client = TestClient(api.app)


def test_estimate_breakdown_base_only_when_addons_off():
    resp = client.post(
        "/api/estimate",
        json={
            "num_scenes": 3,
            "music_enabled": False,
            "dialogue_enabled": False,
            "plan": "pro",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_credits"] == 3
    assert body["breakdown"] == [
        {"label": "Temel üretim (3 sahne)", "credits": 3},
    ]


def test_estimate_breakdown_music_and_dialogue_when_on(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")
    # Re-import gate reads env at call time via is_dialogue_enabled().

    resp = client.post(
        "/api/estimate",
        json={
            "num_scenes": 3,
            "music_enabled": True,
            "dialogue_enabled": True,
            "plan": "pro",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["breakdown"] == [
        {"label": "Temel üretim (3 sahne)", "credits": 3},
        {"label": "Müzik", "credits": 1},
        {"label": "Diyalog", "credits": 3},
    ]
    assert body["total_credits"] == 7


def test_estimate_breakdown_ignores_addons_on_free_plan(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")
    resp = client.post(
        "/api/estimate",
        json={
            "num_scenes": 2,
            "music_enabled": True,
            "dialogue_enabled": True,
            "plan": "free",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_credits"] == 2
    assert body["breakdown"] == [
        {"label": "Temel üretim (2 sahne)", "credits": 2},
    ]


def test_build_credit_breakdown_music_only_for_creator():
    from api import build_credit_breakdown

    result = build_credit_breakdown(
        3, music_enabled=True, dialogue_enabled=True, plan="creator"
    )
    assert result["breakdown"] == [
        {"label": "Temel üretim (3 sahne)", "credits": 3},
        {"label": "Müzik", "credits": 1},
    ]
    assert result["total_credits"] == 4
