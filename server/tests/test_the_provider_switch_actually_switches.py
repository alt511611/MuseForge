"""Flipping a provider has to either work or say why it did not.

Six stages choose a vendor from an environment variable, and three of them
used to compare the raw string against "falai". Anything else -- a capital, a
trailing newline from a dashboard paste, a "fal" instead of "falai" -- fell
back to MuAPI, rendered a whole film on the vendor the operator was trying to
leave, and put nothing in the log about it.

Delivered job 1ac6d945-b53 shows the split this produced. Every image, video
and lip-sync call went to MuAPI while its VOICE went to ElevenLabs -- and
voice was one of the three stages that normalised its variable.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from tools.provider_choice import resolve_provider  # noqa: E402

KNOWN = ("muapi", "falai", "falai_reference")


@pytest.fixture
def var(monkeypatch):
    """Set MUSEFORGE_TEST_PROVIDER, or delete it, per test."""

    def _set(value):
        if value is None:
            monkeypatch.delenv("MUSEFORGE_TEST_PROVIDER", raising=False)
        else:
            monkeypatch.setenv("MUSEFORGE_TEST_PROVIDER", value)
        return resolve_provider(
            "MUSEFORGE_TEST_PROVIDER", KNOWN, default="muapi", stage="Video"
        )

    return _set


# ── the value the operator actually typed ───────────────────────────────────


@pytest.mark.parametrize(
    "typed",
    ["falai", "FALAI", "Falai", " falai", "falai\n", "  falai  \t", "FaLaI\r\n"],
)
def test_a_value_that_names_the_backend_selects_it(var, typed):
    """A dashboard paste carries whatever whitespace the clipboard had, and a
    human types capitals. None of that is a different backend."""
    assert var(typed) == "falai"


def test_a_multi_word_backend_still_resolves(var):
    assert var(" Falai_Reference\n") == "falai_reference"


def test_an_unset_variable_is_the_shipped_default(var):
    assert var(None) == "muapi"


def test_an_empty_variable_is_the_shipped_default(var):
    """render.yaml declares several of these as `value: ""`, so empty is the
    normal state of a deployment that has not opted in."""
    assert var("") == "muapi"
    assert var("   ") == "muapi"


# ── the typo that used to be invisible ──────────────────────────────────────


def test_an_unknown_backend_falls_back_and_says_so(var, caplog):
    with caplog.at_level(logging.WARNING, logger="tools.provider_choice"):
        assert var("fal") == "muapi"

    assert caplog.records, "a silent fallback is the whole bug"
    message = caplog.records[0].getMessage()
    assert "'fal'" in message, "says what was asked for"
    assert "muapi" in message, "and what will actually run"
    for backend in KNOWN:
        assert backend in message, "and what it could have been"


def test_a_recognised_choice_is_logged_too(var, caplog):
    """Not only the failures. 'I set it and it still ran on MuAPI' and 'I set
    it to MuAPI' are the same log line otherwise, and only one is a bug."""
    with caplog.at_level(logging.INFO, logger="tools.provider_choice"):
        assert var("falai") == "falai"
    assert any("falai" in r.getMessage() for r in caplog.records)


def test_the_default_path_stays_silent(var, caplog):
    """A deployment that never set the variable must be as quiet as it has
    always been -- this line is for operators who changed something."""
    with caplog.at_level(logging.INFO, logger="tools.provider_choice"):
        var(None)
    assert not caplog.records


# ── every stage now reads its variable the same way ─────────────────────────


@pytest.mark.parametrize(
    "factory, env, value, expected_module",
    [
        ("_make_image_generator", "MUSEFORGE_IMAGE_PROVIDER", " FALAI\n", "falai"),
        ("_make_video_generator", "MUSEFORGE_VIDEO_PROVIDER", " FALAI\n", "falai"),
    ],
)
def test_the_image_and_video_factories_normalise_too(
    monkeypatch, factory, env, value, expected_module
):
    """The two that compared raw strings. Built with a key present so the
    fal client constructs; only which CLASS came back is under test."""
    import pipelines.script2video as mod

    monkeypatch.setenv(env, value)
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    generator = getattr(mod, factory)("muapi-key", demo=False)

    assert expected_module in type(generator).__module__, type(generator)


def test_music_normalises_too(monkeypatch):
    import pipelines.idea2video as mod

    monkeypatch.setenv("MUSEFORGE_MUSIC_PROVIDER", "  FalAI ")
    monkeypatch.setenv("FAL_KEY", "test-fal-key")

    assert "falai" in type(mod._make_music_generator("muapi-key", demo=False)).__module__


def test_an_unset_stage_still_builds_the_muapi_backend(monkeypatch):
    """The shipped path, unchanged."""
    import pipelines.script2video as mod

    monkeypatch.delenv("MUSEFORGE_VIDEO_PROVIDER", raising=False)
    assert "muapi" in type(mod._make_video_generator("k", demo=True)).__module__
