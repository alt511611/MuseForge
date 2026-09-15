"""What a share link is allowed to contain, and what must not disappear from it.

The Share button on the results page copied `window.location.href`. On that
page the address bar reads `/generate/{job_id}`, which `client/middleware.js`
sends to `/login` for anyone who is not the owner and which `next.config.js`
serves with `X-Robots-Tag: noindex`. Every link a customer has ever sent went
to a sign-in wall, and every crawler that followed one was told to forget it.
`/s/{slug}` is the fix, and these tests pin the three things that make it a
real page rather than another dead end.

ONE: the projection. A share page is served from a `public.jobs` row, and that
row carries the customer's email, the raw prompt they typed, and
`_render_state` -- the full script, the dialogue tracks, the locked portrait
URLs. `sharing.public_payload` names what goes out instead of deleting what
must not, and the difference matters the next time somebody adds a column.

TWO: the slug. A share URL is a capability. If slugs were just the title, then
publishing "The Last Letter" twice would collide, and anyone could walk the
catalogue by guessing titles.

THREE: the video outliving the link. Storage objects are signed for seven days
and then DELETED by the retention sweep, on the reasoning that an object past
its signature "cannot be opened by anyone anyway". Sharing makes that false: a
share page re-signs on demand, so the sweep has to be told which jobs it may
no longer touch. Without the exemption, every published page goes dark on day
eight -- including the ones Google has by then indexed.
"""

from __future__ import annotations

import asyncio

import pytest

import sharing
from tools import supabase_storage


# ── The projection ────────────────────────────────────────────────────────────

def _row(**over):
    """A jobs row as PostgREST returns it, private fields and all."""
    row = {
        "id": "job-123",
        "share_slug": "the-last-letter-0123456789abcdef",
        "shared_at": "2026-09-14T10:00:00+00:00",
        "status": "completed",
        "style": "Romance",
        "director_style": "warm_nostalgia",
        "aspect_ratio": "16:9",
        "num_scenes": 3,
        "demo": False,
        "created_at": "2026-09-14T09:00:00+00:00",
        "user_id": "user-abc",
        "user_email": "someone@example.com",
        "idea": "a film about my father's last week in the hospital",
        "result": {
            "title": "The Last Letter",
            "logline": "A bookseller walks to an address she wrote at nineteen.",
            "mood": "wistful",
            "scene_count": 3,
            "duration_estimate": 48,
            "language": "en",
            "video_url": "https://storage.example/videos/job-123.mp4?token=expires-soon",
            "video_path": "/tmp/museforge_jobs/job-123/drama_final.mp4",
            "characters": [{"name": "Eda", "portrait_url": "https://cdn/eda.png"}],
            "portraits": {"Eda": "https://cdn/eda.png"},
            "scenes": [
                {"index": 0, "shots": [{"frame_url": "https://cdn/open.png"}]},
            ],
            "_render_state": {"script": {"scenes": ["everything"]}},
        },
    }
    row.update(over)
    return row


def test_the_page_never_carries_who_made_it_or_what_they_typed():
    payload = sharing.public_payload(_row())
    flat = repr(payload)

    assert "someone@example.com" not in flat
    assert "user-abc" not in flat
    assert "my father" not in flat, "the raw idea is the user's own words"
    assert "_render_state" not in payload and "everything" not in flat
    assert "job-123" not in flat, "the job id is not the share's identifier"

    # ...and it does carry the things a page and a crawler need.
    assert payload["title"] == "The Last Letter"
    assert payload["logline"].startswith("A bookseller")
    assert payload["poster_url"] == "https://cdn/open.png"
    assert payload["duration_seconds"] == 48
    assert payload["aspect_ratio"] == "16:9"


def test_the_video_link_is_the_share_route_not_the_signed_url_that_expires():
    payload = sharing.public_payload(_row())
    assert payload["video_url"] == "/api/share/the-last-letter-0123456789abcdef/video"
    assert "token=expires-soon" not in repr(payload)


def test_a_film_with_no_generated_frame_still_has_a_payload():
    row = _row()
    row["result"]["scenes"] = [{"index": 0, "shots": [{"frame_url": None}]}]
    row["result"]["portraits"] = {}
    payload = sharing.public_payload(row)
    assert payload["poster_url"] is None
    assert payload["title"] == "The Last Letter"


def test_a_job_that_finished_with_no_title_is_still_nameable():
    row = _row()
    row["result"].pop("title")
    assert sharing.public_payload(row)["title"]


# ── The slug ──────────────────────────────────────────────────────────────────

def test_two_dramas_with_the_same_title_do_not_get_the_same_link():
    a = sharing.new_slug("The Last Letter")
    b = sharing.new_slug("The Last Letter")
    assert a != b
    assert a.startswith("the-last-letter-") and b.startswith("the-last-letter-")


def test_a_slug_is_not_guessable_from_the_title():
    slug = sharing.new_slug("The Last Letter")
    random_half = slug[len("the-last-letter-"):]
    assert len(random_half) == sharing.SLUG_ENTROPY_CHARS
    assert int(random_half, 16) >= 0  # hex, i.e. 64 bits of it


@pytest.mark.parametrize(
    "title,stem",
    [
        ("Gözlerin Rengi", "gozlerin-rengi"),
        ("  The   Tell  ", "the-tell"),
        ("Café/Noir — 1947", "cafe-noir-1947"),
        ("夜の街", ""),          # folds away entirely
        ("", ""),
    ],
)
def test_a_title_in_any_language_yields_a_url_safe_stem(title, stem):
    assert sharing.slugify(title) == stem


def test_a_title_that_folds_away_still_produces_a_working_slug():
    slug = sharing.new_slug("夜の街")
    assert slug.startswith("scene-")
    assert all(c.isalnum() or c == "-" for c in slug)


# ── The video outliving the link ──────────────────────────────────────────────

class _Recorder:
    """Stands in for the two Storage calls the sweep makes."""

    def __init__(self, names):
        self.names = list(names)
        self.deleted = []


@pytest.fixture
def sweep(monkeypatch):
    """A retention sweep wired to a fake bucket, with the env it insists on."""
    monkeypatch.setattr(supabase_storage, "SUPABASE_URL", "https://sb.example")
    monkeypatch.setattr(supabase_storage, "SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(supabase_storage, "_is_demo", lambda: False)

    rec = _Recorder(["job-shared.mp4", "job-private.mp4"])

    async def _expired(_client, _cutoff):
        return list(rec.names)

    async def _delete(_client, names):
        rec.deleted.extend(names)
        return len(names)

    monkeypatch.setattr(supabase_storage, "_expired_object_names", _expired)
    monkeypatch.setattr(supabase_storage, "_delete_objects", _delete)
    return rec


def test_the_sweep_deletes_an_old_video_nobody_published(sweep):
    removed = asyncio.run(supabase_storage.delete_expired_videos())
    assert removed == 2
    assert sorted(sweep.deleted) == ["job-private.mp4", "job-shared.mp4"]


def test_the_sweep_leaves_the_video_behind_a_published_page_alone(sweep):
    removed = asyncio.run(
        supabase_storage.delete_expired_videos(protected={"job-shared"})
    )
    assert removed == 1
    assert sweep.deleted == ["job-private.mp4"]


async def _one_round_of(loop_kwargs):
    """Start the retention loop, let it reach its first sweep, stop it."""
    task = asyncio.ensure_future(supabase_storage.storage_retention_loop(**loop_kwargs))
    for _ in range(8):
        await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_the_loop_really_does_reach_a_sweep(sweep):
    """The control for the test below: without it, an empty `deleted` list
    would prove the loop never started rather than that it declined to run."""

    async def _provider():
        return {"job-shared"}

    asyncio.run(_one_round_of({"protected_provider": _provider}))
    assert sweep.deleted == ["job-private.mp4"]


def test_a_failed_lookup_of_what_is_shared_cancels_the_sweep_rather_than_emptying_it(sweep):
    """The dangerous reading of an error is "nothing is shared"."""

    async def _provider():
        raise RuntimeError("PostgREST is down")

    asyncio.run(_one_round_of({"protected_provider": _provider}))
    assert sweep.deleted == [], "a sweep that cannot see the exemptions must not run"


def test_shared_job_ids_refuses_to_answer_quietly_when_the_lookup_fails(monkeypatch):
    """The read that feeds the exemption list is the one read that must raise.

    Every other read in sharing.py fails open and returns []. This one cannot:
    [] is a valid answer meaning "nothing is published", and the caller acts on
    it by deleting videos.
    """
    monkeypatch.setattr(sharing, "SUPABASE_URL", "https://sb.example")
    monkeypatch.setattr(sharing, "SUPABASE_SERVICE_KEY", "service-key")

    class _Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            raise RuntimeError("PostgREST is down")

    monkeypatch.setattr(sharing.httpx, "AsyncClient", lambda **k: _Boom())

    with pytest.raises(RuntimeError):
        asyncio.run(sharing.shared_job_ids())
