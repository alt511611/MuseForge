"""API-level tests using FastAPI's TestClient (demo mode, fully offline)."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["MUSEFORGE_DEMO"] = "1"
os.environ.pop("MUAPI_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402

client = TestClient(api.app)


def test_health_reports_demo_mode():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["demo_mode"] is True


def test_director_styles_endpoint():
    resp = client.get("/api/director-styles")
    assert resp.status_code == 200
    assert "slow_cinematic" in resp.json()


def test_estimate_endpoint():
    resp = client.post("/api/estimate", json={"num_scenes": 4})
    assert resp.status_code == 200
    body = resp.json()
    assert body["num_scenes"] == 4
    assert body["asset_count"]["frames"] == 4


def test_generate_validation_rejects_short_idea():
    resp = client.post("/api/generate", json={"idea": "hi"})
    assert resp.status_code == 422


def test_generate_rejects_unknown_director_style():
    resp = client.post("/api/generate", json={"idea": "A quiet story unfolds", "director_style": "nope"})
    assert resp.status_code == 400


def test_full_generation_flow_demo():
    resp = client.post(
        "/api/generate",
        json={"idea": "A lighthouse keeper meets a stranger at dawn.", "num_scenes": 2},
    )
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]
    assert resp.json()["demo"] is True

    # BackgroundTasks run after the response in TestClient, so the job is done.
    for _ in range(50):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)

    assert job["status"] == "completed", job.get("error")
    assert job["result"]["scene_count"] == 2
    assert job["result"]["video_url"]

    video = client.get(f"/api/jobs/{job_id}/video", follow_redirects=False)
    assert video.status_code in (302, 307)


def test_get_missing_job_404():
    assert client.get("/api/jobs/does-not-exist").status_code == 404
