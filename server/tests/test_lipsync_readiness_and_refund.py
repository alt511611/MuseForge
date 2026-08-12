"""Two paths that existed in full but could never actually fire.

1. api._lipsync_configured() gated deployment readiness on FAL_KEY alone. MuAPI
   became the DEFAULT lip-sync provider, so a deployment running the default
   reported lipsync_available=False no matter how it was configured: the toggle
   never rendered, and a request asking for it anyway was dropped in generate().

2. jobs._sb_refund_credits() added the refund to profiles.credits. That column
   is a read cache which public.sync_credit_cache() rewrites from credit_lots on
   any credit movement, and api._get_user_credits reads the credit_balance() RPC,
   which sums lots and ignores the cache. Every refund was therefore invisible
   on arrival and erased by the next grant or deduction.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import api as api_mod  # noqa: E402
import jobs as jobs_mod  # noqa: E402


# ── Lip sync readiness ────────────────────────────────────────────────────────

def test_default_muapi_provider_is_ready_on_muapi_key_alone(monkeypatch):
    """The regression: no fal.ai account, default provider, feature switched
    on — the deployment CAN sync, so it must say so."""
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.delenv("MUSEFORGE_LIPSYNC_PROVIDER", raising=False)
    monkeypatch.setenv("MUAPI_KEY", "real-muapi-key")
    monkeypatch.delenv("FAL_KEY", raising=False)

    assert api_mod._lipsync_configured() is True


def test_falai_provider_still_requires_the_fal_key(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_PROVIDER", "falai")
    monkeypatch.setenv("MUAPI_KEY", "real-muapi-key")
    monkeypatch.delenv("FAL_KEY", raising=False)

    assert api_mod._lipsync_configured() is False

    monkeypatch.setenv("FAL_KEY", "real-fal-key")
    assert api_mod._lipsync_configured() is True


def test_the_feature_flag_is_still_the_master_switch(monkeypatch):
    """A key is not consent: an operator who has not switched the feature on
    must never be quoted (or charged) for it."""
    monkeypatch.delenv("MUSEFORGE_LIPSYNC_ENABLED", raising=False)
    monkeypatch.setenv("MUAPI_KEY", "real-muapi-key")
    monkeypatch.setenv("FAL_KEY", "real-fal-key")

    assert api_mod._lipsync_configured() is False


def test_an_unconfigured_deployment_does_not_quote_lipsync(monkeypatch):
    """The credit breakdown is the customer-facing consequence: a stage the
    server cannot run must not appear as a line item."""
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.delenv("MUSEFORGE_LIPSYNC_PROVIDER", raising=False)
    monkeypatch.setenv("MUAPI_KEY", "")
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(api_mod, "is_dialogue_enabled", lambda: True)

    quote = api_mod.build_credit_breakdown(
        3, dialogue_enabled=True, lipsync_enabled=True, plan="pro"
    )
    assert all("senkron" not in row["label"] for row in quote["breakdown"])


def test_a_ready_deployment_does_quote_lipsync(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.delenv("MUSEFORGE_LIPSYNC_PROVIDER", raising=False)
    monkeypatch.setenv("MUAPI_KEY", "real-muapi-key")
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(api_mod, "is_dialogue_enabled", lambda: True)

    quote = api_mod.build_credit_breakdown(
        3, dialogue_enabled=True, lipsync_enabled=True, plan="pro"
    )
    lipsync_rows = [r for r in quote["breakdown"] if "senkron" in r["label"]]
    assert lipsync_rows and lipsync_rows[0]["credits"] == 3


# ── Refunds ───────────────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.text = ""

    def json(self):
        return self._payload


class _RecordingClient:
    """Records every Supabase call so the test can assert WHICH store moved."""

    def __init__(self, grant_status=200):
        self.calls = []
        self._grant_status = grant_status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, headers=None, **kwargs):
        self.calls.append(("POST", url, json))
        if "rpc/grant_credits" in url:
            return _FakeResponse(self._grant_status, 12)
        return _FakeResponse(201)

    async def get(self, url, params=None, headers=None, **kwargs):
        self.calls.append(("GET", url, params))
        return _FakeResponse(200, [{"credits": 4}])

    async def patch(self, url, json=None, params=None, headers=None, **kwargs):
        self.calls.append(("PATCH", url, json))
        return _FakeResponse(204)


@pytest.fixture
def supabase_configured(monkeypatch):
    monkeypatch.setattr(jobs_mod, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(jobs_mod, "SUPABASE_SERVICE_KEY", "service-key")


@pytest.mark.asyncio
async def test_refund_issues_a_credit_lot(supabase_configured, monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(jobs_mod.httpx, "AsyncClient", lambda **kw: client)

    await jobs_mod._sb_refund_credits("user-1", 5, "job-1")

    grants = [c for c in client.calls if "rpc/grant_credits" in c[1]]
    assert grants, "a refund must create a real credit lot, not touch the cache"
    assert grants[0][2]["p_amount"] == 5
    assert grants[0][2]["p_reason"] == "refund"
    assert grants[0][2]["p_days"] == jobs_mod.REFUND_VALIDITY_DAYS

    # The cache is grant_credits' business (sync_credit_cache), not ours.
    assert not [
        c for c in client.calls if c[0] == "PATCH" and "/profiles" in c[1]
    ], "writing profiles.credits directly is what made refunds vanish"


@pytest.mark.asyncio
async def test_refund_is_attributed_to_its_job(supabase_configured, monkeypatch):
    """grant_credits' ledger row carries no job_id — support needs one."""
    client = _RecordingClient()
    monkeypatch.setattr(jobs_mod.httpx, "AsyncClient", lambda **kw: client)

    await jobs_mod._sb_refund_credits("user-1", 5, "job-1")

    ledger_patches = [
        c for c in client.calls if c[0] == "PATCH" and "credit_ledger" in c[1]
    ]
    assert ledger_patches and ledger_patches[0][2] == {"job_id": "job-1"}


@pytest.mark.asyncio
async def test_refund_falls_back_when_grant_credits_is_missing(
    supabase_configured, monkeypatch
):
    """An install that has not replayed the credit_lots migration has no
    grant_credits(). It must keep refunding rather than silently stop."""
    client = _RecordingClient(grant_status=404)
    monkeypatch.setattr(jobs_mod.httpx, "AsyncClient", lambda **kw: client)

    await jobs_mod._sb_refund_credits("user-1", 5, "job-1")

    profile_patches = [
        c for c in client.calls if c[0] == "PATCH" and "/profiles" in c[1]
    ]
    assert profile_patches and profile_patches[0][2] == {"credits": 9}
    assert [c for c in client.calls if c[0] == "POST" and "credit_ledger" in c[1]]


@pytest.mark.asyncio
async def test_a_zero_refund_touches_nothing(supabase_configured, monkeypatch):
    client = _RecordingClient()
    monkeypatch.setattr(jobs_mod.httpx, "AsyncClient", lambda **kw: client)

    await jobs_mod._sb_refund_credits("user-1", 0, "job-1")

    assert client.calls == []
