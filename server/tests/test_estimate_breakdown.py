"""Credit breakdown on POST /api/estimate.

Each row carries a translation KEY and its variables as well as a rendered
`label`. The label alone was Turkish, hardcoded, and the client renders it
verbatim -- so a customer reading the site in any of the other nineteen
locales was quoted a price in a language they had not chosen, at the moment
they were deciding whether to spend credits.

The assertions below check the shape a client can localise from, not the exact
dicts: the label is the compatibility fallback for a browser holding the
previous bundle, and pinning its wording here would make it the contract
again."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interfaces.second_budget import SECONDS_PER_CREDIT  # noqa: E402
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
    assert [(r["key"], r["credits"]) for r in body["breakdown"]] == [
        ("estimate_row_base", 3),
    ]
    base = body["breakdown"][0]
    # The numbers a client needs to render the row itself, rather than a
    # sentence it can only print.
    assert base["vars"] == {"scenes": 3, "seconds": int(3 * SECONDS_PER_CREDIT)}
    assert base["label"]


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
    assert [(r["key"], r["credits"]) for r in body["breakdown"]] == [
        ("estimate_row_base", 3),
        ("estimate_row_music", 1),
        ("estimate_row_dialogue", 3),
    ]
    # Every row is renderable without the server's own wording.
    assert all(r.get("key") and "vars" in r for r in body["breakdown"])
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
    assert [(r["key"], r["credits"]) for r in body["breakdown"]] == [
        ("estimate_row_base", 2),
    ]
    assert body["breakdown"][0]["vars"] == {
        "scenes": 2,
        "seconds": int(2 * SECONDS_PER_CREDIT),
    }


def test_build_credit_breakdown_music_only_for_creator():
    from api import build_credit_breakdown

    result = build_credit_breakdown(
        3, music_enabled=True, dialogue_enabled=True, plan="creator"
    )
    assert [(r["key"], r["credits"]) for r in result["breakdown"]] == [
        ("estimate_row_base", 3),
        ("estimate_row_music", 1),
    ]
    assert result["total_credits"] == 4
