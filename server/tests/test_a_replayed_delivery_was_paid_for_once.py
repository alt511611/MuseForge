"""What Supabase actually answers when the same payment arrives twice.

On 15 September 2026 Whop replayed `msg_MwxfZCT1U9G1nZKm65Lh...` to the live
endpoint with its ORIGINAL webhook-id -- the replay dialog says so in as many
words -- and the customer was granted the same 4 credits a second time.
`processed_stripe_events` still held exactly one row, the mark written by the
first delivery. Nothing had gone wrong with the mark. What had gone wrong was
reading it:

    "Prefer": "resolution=ignore-duplicates,return=minimal"
    return resp.status_code == 201

PostgREST skips the conflicting row under that Prefer and answers **201 all
the same**, so "did I just claim this event?" and "was it already claimed?"
were the same reply. Every redelivery looked new.

The whole suite was green while this shipped, and that is the lesson worth
keeping. `test_two_processors_cannot_claim_one_event_id` patches
`mark_event_processed` with a set and asserts the DISPATCHER does the right
thing with True and False -- which it does, and always did. Nobody asserted
what the database says. So these tests are written against the HTTP replies
themselves: a plain insert answers 201, a primary-key conflict answers 409,
and everything else is the fail-open case.
"""

import pytest

import billing


class _Resp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class _Supabase:
    """PostgREST for one table with a primary key on event_id."""

    def __init__(self):
        self.rows: set = set()
        self.posts: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None):
        key = (json or {}).get("event_id")
        self.posts.append(key)
        if key in self.rows:
            return _Resp(
                409,
                '{"code":"23505","message":"duplicate key value violates '
                'unique constraint \\"processed_stripe_events_pkey\\""}',
            )
        self.rows.add(key)
        return _Resp(201)


@pytest.fixture
def supabase(monkeypatch):
    client = _Supabase()
    monkeypatch.setattr(billing, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(billing.httpx, "AsyncClient", lambda *a, **k: client)
    return client


@pytest.mark.asyncio
async def test_the_first_delivery_claims_the_event(supabase):
    assert await billing.mark_event_processed("whop", "msg_1") is True


@pytest.mark.asyncio
async def test_the_replay_of_that_delivery_claims_nothing(supabase):
    """The live failure, at the level it actually happened: same id, same
    table, and the second answer has to be False."""
    await billing.mark_event_processed("whop", "msg_MwxfZCT1U9G1nZKm65Lh")
    again = await billing.mark_event_processed("whop", "msg_MwxfZCT1U9G1nZKm65Lh")

    assert again is False, "a replayed delivery is not a second sale"
    assert supabase.posts == [
        "whop:msg_MwxfZCT1U9G1nZKm65Lh",
        "whop:msg_MwxfZCT1U9G1nZKm65Lh",
    ]


@pytest.mark.asyncio
async def test_stripe_is_protected_by_the_same_reply(supabase):
    """The defect was inherited from the Stripe path and had been there since
    the table was added -- Stripe had simply never redelivered an event."""
    assert await billing.mark_event_processed("stripe", "evt_1") is True
    assert await billing.mark_event_processed("stripe", "evt_1") is False


@pytest.mark.asyncio
async def test_a_database_that_cannot_answer_does_not_block_the_payment(monkeypatch):
    """Fail-open, deliberately: a webhook that cannot reach the idempotency
    table is still a payment that has to be credited, and a duplicate grant is
    recoverable in a way an uncredited purchase is not."""
    class _Broken(_Supabase):
        async def post(self, url, json=None, headers=None):
            return _Resp(500, "upstream connect error")

    monkeypatch.setattr(billing, "SUPABASE_URL", "https://sb.test")
    monkeypatch.setattr(billing, "SUPABASE_SERVICE_KEY", "service-key")
    monkeypatch.setattr(billing.httpx, "AsyncClient", lambda *a, **k: _Broken())

    assert await billing.mark_event_processed("whop", "msg_2") is True


@pytest.mark.asyncio
async def test_a_201_is_not_read_as_a_duplicate(supabase):
    """The inverse of the bug, pinned so a future 'tidy-up' cannot restore it:
    two DIFFERENT events must both be claimable."""
    assert await billing.mark_event_processed("whop", "msg_a") is True
    assert await billing.mark_event_processed("whop", "msg_b") is True
