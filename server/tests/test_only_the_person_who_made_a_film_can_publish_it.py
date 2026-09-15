"""Who may turn a job into a public page, and when the page stops existing.

Publishing is the one action in this product that makes a customer's work
readable by strangers and by crawlers, so the gate on it is worth pinning
separately from the payload it produces (which
`test_a_share_link_that_leads_to_a_sign_in_wall_is_not_a_share.py` covers).

Four things are being fixed in place here:

  * Someone else's job is not publishable, and the 403 must not depend on the
    job happening to still be in the in-memory store -- an eviction is not an
    authorisation.

  * An anonymous job is not publishable by anyone. The landing page generates
    without an account, so those rows have `user_id = null`, and `null` is not
    a user that any caller can prove they are. Left open, "publish the job I
    just made anonymously" is also "publish any anonymous job whose id I can
    guess".

  * A job still rendering is not publishable. A share page for a queued job is
    a URL its owner will paste that resolves to nothing.

  * Pressing Share twice yields ONE link. The slug is what the customer has
    already pasted into Slack; minting a second one silently orphans the first.
    Revoking, on the other hand, must not be undoable by re-sharing into the
    same slug -- a link the owner took back does not come back.
"""

import os
import sys
from contextlib import contextmanager

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["MUSEFORGE_DEMO"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

import api as _api  # noqa: E402
import sharing  # noqa: E402
from auth import AuthUser  # noqa: E402
from jobs import Job, JobStatus  # noqa: E402

client = TestClient(_api.app)

OWNER = "user-owner"
FINISHED_RESULT = {
    "title": "The Tell",
    "logline": "A dealer realises the man opposite is copying her own tell.",
    "scene_count": 3,
    "duration_estimate": 40,
    "scenes": [{"index": 0, "shots": [{"frame_url": "https://cdn/open.png"}]}],
    "video_url": "https://storage.example/videos/job-tell.mp4?token=abc",
}


@contextmanager
def _auth_as(user_id=OWNER, email="owner@example.com", is_admin=False):
    async def _fake_user():
        user = AuthUser(user_id, email)
        if is_admin:
            user.is_admin = True
        return user

    _api.app.dependency_overrides[_api.get_current_user] = _fake_user
    try:
        yield
    finally:
        _api.app.dependency_overrides.pop(_api.get_current_user, None)


def _put_job(job_id="job-tell", user_id=OWNER, status=JobStatus.COMPLETED):
    job = Job(id=job_id, user_id=user_id, status=status, idea="a card game")
    if status == JobStatus.COMPLETED:
        job.result = dict(FINISHED_RESULT)
    _api.job_store._jobs[job_id] = job
    return job


@pytest.fixture(autouse=True)
def _clean_state():
    """No Supabase in the suite, so sharing uses its in-memory fallback."""
    sharing._shares_mem.clear()
    _api.job_store._jobs.clear()
    yield
    sharing._shares_mem.clear()
    _api.job_store._jobs.clear()


def test_the_owner_of_a_finished_film_gets_a_public_path():
    _put_job()
    with _auth_as():
        resp = client.post("/api/jobs/job-tell/share")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["path"] == f"/s/{body['slug']}"
    assert body["slug"].startswith("the-tell-")


def test_somebody_elses_film_is_not_publishable():
    _put_job(user_id="user-someone-else")
    with _auth_as():
        resp = client.post("/api/jobs/job-tell/share")
    assert resp.status_code == 403


def test_a_film_made_without_an_account_is_publishable_by_nobody():
    _put_job(user_id=None)
    with _auth_as():
        resp = client.post("/api/jobs/job-tell/share")
    assert resp.status_code == 403
    assert "Sign in" in resp.json()["detail"]


@pytest.mark.parametrize(
    "status",
    [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.FAILED, JobStatus.CANCELLED],
)
def test_a_film_that_is_not_finished_has_nothing_to_publish(status):
    _put_job(status=status)
    with _auth_as():
        resp = client.post("/api/jobs/job-tell/share")
    assert resp.status_code == 409


def test_a_job_nobody_has_ever_heard_of_is_a_404():
    with _auth_as():
        assert client.post("/api/jobs/job-nope/share").status_code == 404


def test_pressing_share_twice_yields_one_link():
    _put_job()
    with _auth_as():
        first = client.post("/api/jobs/job-tell/share").json()
        second = client.post("/api/jobs/job-tell/share").json()
    assert first["slug"] == second["slug"]


def test_a_published_page_is_readable_without_signing_in():
    _put_job()
    with _auth_as():
        slug = client.post("/api/jobs/job-tell/share").json()["slug"]

    # No auth override in scope: this is an anonymous request.
    resp = client.get(f"/api/share/{slug}")
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["title"] == "The Tell"
    assert payload["video_url"] == f"/api/share/{slug}/video"
    assert "job-tell" not in repr(payload)


def test_revoking_takes_the_page_down_and_does_not_hand_the_link_back():
    _put_job()
    with _auth_as():
        slug = client.post("/api/jobs/job-tell/share").json()["slug"]
        assert client.delete("/api/jobs/job-tell/share").status_code == 200

    assert client.get(f"/api/share/{slug}").status_code == 404

    with _auth_as():
        new_slug = client.post("/api/jobs/job-tell/share").json()["slug"]
    assert new_slug != slug
    assert client.get(f"/api/share/{slug}").status_code == 404
    assert client.get(f"/api/share/{new_slug}").status_code == 200


def test_a_slug_nobody_minted_is_a_404_not_an_empty_page():
    assert client.get("/api/share/made-up-slug").status_code == 404
    assert client.get("/api/share/made-up-slug/video").status_code == 404


def test_the_gallery_leaves_demo_renders_out():
    """A demo render is a stand-in made without paying a provider. A public
    page is a claim about what this product makes; the two are not the same."""
    real = _put_job("job-real")
    demo = _put_job("job-demo")
    demo.demo = True

    with _auth_as():
        client.post("/api/jobs/job-real/share")
        client.post("/api/jobs/job-demo/share")

    items = client.get("/api/shares").json()["items"]
    titles = [i["slug"] for i in items]
    assert len(titles) == 1, "the demo render must not be in the gallery"

    # ...but its own link still works for the person who made it.
    demo_slug = sharing._shares_mem["job-demo"]["share_slug"]
    assert client.get(f"/api/share/{demo_slug}").status_code == 200
