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

from tools.muapi_lipsync import TRUTHY

#: What the running service is configured to do. See deploy/coolify.env.
SHIPPED_CONFIG = os.path.join(
    os.path.dirname(__file__), "..", "..", "deploy", "coolify.env"
)


def _shipped_config() -> dict:
    """deploy/coolify.env as a dict, comments and blank lines dropped."""
    config = {}
    with open(SHIPPED_CONFIG, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            config[name.strip()] = value.strip().lower()
    return config
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


def test_the_shipped_configuration_switches_the_feature_on():
    """The flag was declared with an empty value, which is the same as absent
    everywhere it is read: /api/health reported lipsync_available=false, the Pro
    toggle never rendered, and a request that asked for lip sync anyway was
    dropped in generate(). Delivered dramas came back with the voice laid over
    closed, motionless mouths.

    Readiness is not spending. The per-job opt-in still sits behind the Pro
    toggle and still charges +1 credit per speaking scene, so an operator who
    wants the old behaviour turns the flag off; nobody is billed by this line.

    Read from deploy/coolify.env, which replaced render.yaml when Coolify
    became the only deployment. Coolify keeps its environment in a database
    rather than in the repository, so without that file nothing in version
    control would say what the running service is configured to do -- and this
    assertion, which is the only thing that has ever caught this flag going
    quiet, would have had nothing to read.
    """
    assert _shipped_config()["MUSEFORGE_LIPSYNC_ENABLED"] in TRUTHY, (
        "declared but empty reads as OFF, which is how the feature shipped "
        "unreachable in its own default configuration"
    )


def test_the_shipped_configuration_can_speak_before_it_syncs():
    """Lip sync on with dialogue off is the one pairing that cannot work.

    There is nothing to drive a mouth from without a generated voice, so the
    sync pass runs over silence and the film ships with the voice -- when one
    is finally switched on -- laid across closed mouths. The two flags were in
    exactly that state in the blueprint this file used to read.
    """
    config = _shipped_config()
    if config["MUSEFORGE_LIPSYNC_ENABLED"] in TRUTHY:
        assert config.get("MUSEFORGE_DIALOGUE_ENABLED", "") in TRUTHY, (
            "lip sync is on and dialogue is off: the sync pass has no voice "
            "to drive a mouth from"
        )


def test_the_shipped_configuration_holds_no_secrets():
    """deploy/coolify.env is committed. Nothing that authenticates goes in it.

    Named rather than pattern-matched: a check that looks for "KEY" in a
    variable name would pass a file with a Stripe price id in it and fail on
    MUAPI_KONTEXT_MODEL, which is neither a secret nor a key.
    """
    forbidden = (
        "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "FAL_KEY", "MUAPI_KEY",
        "SUPABASE_ANON_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_URL",
        "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
    )
    config = _shipped_config()
    leaked = sorted(name for name in forbidden if name in config)
    assert not leaked, (
        f"{leaked} must live in Coolify and nowhere else; this file is "
        "committed"
    )


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
