"""The videos bucket only ever grew, and most of what filled it was dead.

Two facts about this codebase met and produced a quota bill. upload_video
signs a URL for SIGNED_URL_TTL_SECONDS and nothing anywhere re-signs one, so a
week after delivery the customer's video is already unreachable -- the
re-export path meets the dead URL and answers 502. And nothing ever deleted
from the bucket: jobs._sb_delete drops the job ROW, which does not remove the
object, it only strands it with nothing left pointing at its name.

So the bucket accumulated masters that no one could open, forever, until a
deployment hit its plan quota at 1.12 GB -- about a dozen films, because a
1080p CRF 18 scene is 15-25 MB.

These tests pin the one property that makes deleting them safe: the retention
window is DERIVED from the signed-URL TTL, so the sweep can only ever reach
objects whose URLs have already stopped working. Configure the two
independently and the day someone extends the TTL, retention keeps deleting on
the old schedule and starts destroying videos that still work.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from tools import supabase_storage as st  # noqa: E402


def _iso(dt: datetime) -> str:
    """Storage's own timestamp shape: ISO-8601 with a Z."""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _obj(name: str, age_days: float) -> dict:
    return {
        "name": name,
        "created_at": _iso(datetime.now(timezone.utc) - timedelta(days=age_days)),
        "metadata": {"size": 20_000_000},
    }


class _FakeResponse:
    status_code = 200

    def __init__(self, payload=None):
        self._payload = payload if payload is not None else []

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeBucket:
    """One page-able bucket that records what the sweep asks of it."""

    def __init__(self, objects):
        self.objects = list(objects)
        self.list_calls: list = []
        self.deleted: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        assert "/object/list/" in url, url
        self.list_calls.append(json)
        offset = int(json.get("offset", 0))
        limit = int(json.get("limit", st._LIST_PAGE_SIZE))
        return _FakeResponse(self.objects[offset : offset + limit])

    async def request(self, method, url, json=None, headers=None):
        assert method == "DELETE", method
        self.deleted.extend(json["prefixes"])
        return _FakeResponse()


def _install(monkeypatch, objects):
    bucket = _FakeBucket(objects)
    monkeypatch.setattr(st.httpx, "AsyncClient", lambda *a, **k: bucket)
    monkeypatch.setattr(st, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(st, "SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setenv("MUSEFORGE_DEMO", "")
    monkeypatch.setenv("MUSEFORGE_STORAGE_RETENTION", "")
    return bucket


# --- the window is the TTL, not a number that sits next to it ----------------


def test_the_window_is_the_signed_url_ttl_plus_grace(monkeypatch):
    monkeypatch.setattr(st, "SIGNED_URL_TTL_SECONDS", 7 * 24 * 3600)
    monkeypatch.setattr(st, "RETENTION_GRACE_SECONDS", 24 * 3600)

    assert st.retention_seconds() == 8 * 24 * 3600


def test_a_longer_ttl_moves_the_window_with_it(monkeypatch):
    """The coupling this whole file exists to protect.

    A deployment that promises thirty days raises the TTL; retention must
    follow, or it deletes videos whose URLs are still live.
    """
    monkeypatch.setattr(st, "RETENTION_GRACE_SECONDS", 24 * 3600)

    monkeypatch.setattr(st, "SIGNED_URL_TTL_SECONDS", 7 * 24 * 3600)
    short = st.retention_seconds()

    monkeypatch.setattr(st, "SIGNED_URL_TTL_SECONDS", 30 * 24 * 3600)
    long = st.retention_seconds()

    assert long - short == 23 * 24 * 3600


# --- what the sweep may and may not touch ------------------------------------


@pytest.mark.asyncio
async def test_a_dead_object_goes_and_a_live_one_stays(monkeypatch):
    monkeypatch.setattr(st, "SIGNED_URL_TTL_SECONDS", 7 * 24 * 3600)
    monkeypatch.setattr(st, "RETENTION_GRACE_SECONDS", 24 * 3600)
    bucket = _install(
        monkeypatch,
        [
            _obj("old.mp4", age_days=30),
            _obj("yesterday.mp4", age_days=1),
            _obj("just-past-the-window.mp4", age_days=8.5),
            _obj("still-signed.mp4", age_days=6),
        ],
    )

    removed = await st.delete_expired_videos()

    assert removed == 2
    assert sorted(bucket.deleted) == ["just-past-the-window.mp4", "old.mp4"]


@pytest.mark.asyncio
async def test_an_object_inside_the_grace_is_left_alone(monkeypatch):
    """Between the TTL and the end of the grace, nothing is touched.

    The object is written before its URL is signed and neither clock is ours,
    so the boundary is not a place to be exact.
    """
    monkeypatch.setattr(st, "SIGNED_URL_TTL_SECONDS", 7 * 24 * 3600)
    monkeypatch.setattr(st, "RETENTION_GRACE_SECONDS", 24 * 3600)
    bucket = _install(monkeypatch, [_obj("borderline.mp4", age_days=7.5)])

    assert await st.delete_expired_videos() == 0
    assert bucket.deleted == []


@pytest.mark.asyncio
async def test_an_unreadable_timestamp_is_not_evidence_of_age(monkeypatch):
    """A missing created_at means we do not know, and the only thing this
    list feeds is a delete."""
    bucket = _install(
        monkeypatch,
        [
            {"name": "no-timestamp.mp4", "created_at": None},
            {"name": "garbled.mp4", "created_at": "not a date"},
            _obj("genuinely-old.mp4", age_days=60),
        ],
    )

    await st.delete_expired_videos()

    assert bucket.deleted == ["genuinely-old.mp4"]


# --- the shape of the calls it makes -----------------------------------------


@pytest.mark.asyncio
async def test_the_delete_is_one_batched_request_with_prefixes(monkeypatch):
    """Storage's bulk delete takes {"prefixes": [...]} on a DELETE with a body
    -- which is why this goes through client.request, not client.delete."""
    bucket = _install(monkeypatch, [_obj(f"{i}.mp4", age_days=60) for i in range(3)])

    await st.delete_expired_videos()

    assert sorted(bucket.deleted) == ["0.mp4", "1.mp4", "2.mp4"]


@pytest.mark.asyncio
async def test_the_whole_bucket_is_walked_not_just_the_first_page(monkeypatch):
    """Old objects behind a young one must still be found.

    The sweep does not sort-and-stop, precisely so that a young object early in
    the listing cannot hide everything after it.
    """
    monkeypatch.setattr(st, "_LIST_PAGE_SIZE", 2)
    bucket = _install(
        monkeypatch,
        [
            _obj("fresh.mp4", age_days=0),
            _obj("page1-old.mp4", age_days=40),
            _obj("page2-old.mp4", age_days=40),
            _obj("page3-old.mp4", age_days=40),
        ],
    )

    removed = await st.delete_expired_videos()

    assert removed == 3
    assert "fresh.mp4" not in bucket.deleted
    assert len(bucket.list_calls) >= 2


# --- when it must not run at all ---------------------------------------------


@pytest.mark.asyncio
async def test_demo_mode_touches_no_network(monkeypatch):
    bucket = _install(monkeypatch, [_obj("old.mp4", age_days=60)])
    monkeypatch.setenv("MUSEFORGE_DEMO", "1")

    assert await st.delete_expired_videos() == 0
    assert bucket.list_calls == []
    assert bucket.deleted == []


@pytest.mark.asyncio
async def test_an_unconfigured_deployment_deletes_nothing(monkeypatch):
    bucket = _install(monkeypatch, [_obj("old.mp4", age_days=60)])
    monkeypatch.setattr(st, "SUPABASE_SERVICE_KEY", "")

    assert await st.delete_expired_videos() == 0
    assert bucket.deleted == []


@pytest.mark.asyncio
async def test_the_switch_turns_it_off(monkeypatch):
    bucket = _install(monkeypatch, [_obj("old.mp4", age_days=60)])
    monkeypatch.setenv("MUSEFORGE_STORAGE_RETENTION", "off")

    assert await st.delete_expired_videos() == 0
    assert bucket.deleted == []


def test_it_is_on_when_nothing_is_configured(monkeypatch):
    """A bucket nothing prunes is the state that caused the quota bill."""
    monkeypatch.delenv("MUSEFORGE_STORAGE_RETENTION", raising=False)
    assert st.retention_enabled() is True


# --- the blueprint's way of saying "leave this alone" ------------------------


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "not a number"],
    ids=["empty", "whitespace", "garbage"],
)
def test_an_empty_setting_falls_back_instead_of_killing_the_import(monkeypatch, raw):
    """A deployment writes an unset knob as an empty value, not as an absence.

    Render's blueprint wrote ``value: ""``; Coolify's environment editor stores
    ``NAME=``. Either way the variable exists and is empty, so a bare
    int(os.environ.get(...)) never sees its default and raises. These are read
    at module scope, so the failure is not a bad setting, it is an API that
    will not import.
    """
    monkeypatch.setenv("MUSEFORGE_SIGNED_URL_TTL", raw)

    assert st._int_env("MUSEFORGE_SIGNED_URL_TTL", 604800) == 604800


# --- a failing sweep is not a failing server ---------------------------------


@pytest.mark.asyncio
async def test_a_storage_outage_is_swallowed(monkeypatch):
    """This runs in a background loop next to the generation pipeline. A bad
    hour at Storage must not take anything else down with it."""
    monkeypatch.setattr(st, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(st, "SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setenv("MUSEFORGE_DEMO", "")
    monkeypatch.setenv("MUSEFORGE_STORAGE_RETENTION", "")

    class _Broken:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *a, **k):
            raise RuntimeError("storage is having a day")

    monkeypatch.setattr(st.httpx, "AsyncClient", lambda *a, **k: _Broken())

    assert await st.delete_expired_videos() == 0
