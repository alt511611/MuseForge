"""The on-site Whop form is opened with the checkout configuration id
(`ch_...`), because that configuration is what carries the user-id metadata the
webhook credits from. The id has to survive `create_checkout_session`, which
callers (and other tests) still treat as a plain URL string."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import whop_integration as wi  # noqa: E402


class _Resp:
    status_code = 200
    text = ""

    def json(self):
        return {"id": "ch_abc123", "purchase_url": "https://whop.com/checkout/ch_abc123"}


class _Client:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        return _Resp()


def test_the_session_id_rides_along_on_a_string_url(monkeypatch):
    monkeypatch.setattr(wi, "WHOP_API_KEY", "k")
    monkeypatch.setattr(wi.httpx, "AsyncClient", _Client)
    url = asyncio.run(wi.create_checkout_session("plan_x", "user-1"))
    assert isinstance(url, str)
    assert url == "https://whop.com/checkout/ch_abc123"
    assert url.session_id == "ch_abc123"
