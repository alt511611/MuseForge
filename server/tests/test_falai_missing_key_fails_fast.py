"""Verify fal.ai clients fail IMMEDIATELY and CLEARLY when FAL_KEY is
missing/empty, instead of silently constructing a key=None client that
could fail unpredictably deep inside the first real network call --
found during a deep audit after a generation produced zero logs at all,
with FAL_KEY missing from Render's environment as the leading suspect.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_make_fal_client_raises_immediately_on_empty_key():
    from tools.falai_common import make_fal_client

    with pytest.raises(RuntimeError, match="FAL_KEY is not set"):
        make_fal_client("")

    with pytest.raises(RuntimeError, match="FAL_KEY is not set"):
        make_fal_client("   \n")  # whitespace-only also counts as empty


def test_make_fal_client_demo_mode_never_raises():
    from tools.falai_common import make_fal_client

    # Demo mode never makes a real network call, so it must not require
    # a real key either.
    client = make_fal_client("", demo=True)
    assert client is not None


def test_falai_video_generator_raises_immediately_on_empty_key(monkeypatch):
    from tools.falai_video_generator import FalAIVideoGenerator

    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(RuntimeError, match="FAL_KEY is not set"):
        FalAIVideoGenerator("", demo=False)

    # Demo mode must not raise even with no key.
    gen = FalAIVideoGenerator("", demo=True)
    assert gen is not None
