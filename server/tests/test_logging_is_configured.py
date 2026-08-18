"""The application's own log lines have to reach the log.

Nothing in this project ever configured logging. uvicorn configures its OWN
loggers ("uvicorn", "uvicorn.access") and leaves the root logger alone, so
every module logger here fell through to logging.lastResort -- which is
WARNING-only, and prints a bare message with no timestamp, level or name.

So 42 logger.info() calls, written over the life of this project precisely so
a delivered job could be explained afterwards, were discarded in production.
Found the direct way: an operator went looking for

    Second budget for job: [...] (total 30s across 3 scenes)

to explain why a 3-scene script rendered 60 seconds of video, and it was not
in the logs. It had never been in the logs. Neither had the line naming which
stage declined lip sync, nor the one reporting how many scenes got foley.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import api as api_mod  # noqa: E402


def test_the_pipeline_s_own_info_lines_are_enabled():
    """The regression, stated as the thing that was actually lost: a job's
    diagnostic trail."""
    assert logging.getLogger("pipelines.idea2video").isEnabledFor(logging.INFO)
    assert logging.getLogger("tools.muapi_lipsync").isEnabledFor(logging.INFO)
    assert logging.getLogger("agents.screenwriter").isEnabledFor(logging.INFO)


def test_the_root_logger_has_somewhere_to_write():
    """Without a handler, logging.lastResort takes over: WARNING and above
    only, and no timestamp or logger name on what does get through."""
    root = logging.getLogger()
    assert root.handlers, "no handler — records fall through to lastResort"


def test_lines_carry_when_where_and_how_bad(caplog):
    handler = logging.getLogger().handlers[0]
    formatted = handler.format(
        logging.LogRecord(
            name="pipelines.idea2video",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="Second budget for job: %s (total %ss across %s scenes)",
            args=([8.0, 10.0, 12.0], 30, 3),
            exc_info=None,
        )
    )

    assert "pipelines.idea2video" in formatted
    assert "INFO" in formatted
    assert "across 3 scenes" in formatted


def test_an_operator_can_turn_the_volume_down(monkeypatch):
    """WARNING restores the old quiet for anyone who wants it, and DEBUG is
    reachable without a code change."""
    monkeypatch.setenv("MUSEFORGE_LOG_LEVEL", "WARNING")
    api_mod._configure_logging()
    try:
        assert not logging.getLogger("pipelines.idea2video").isEnabledFor(logging.INFO)
        assert logging.getLogger("pipelines.idea2video").isEnabledFor(logging.WARNING)
    finally:
        monkeypatch.delenv("MUSEFORGE_LOG_LEVEL", raising=False)
        api_mod._configure_logging()


def test_an_unknown_level_falls_back_to_info_rather_than_crashing(monkeypatch):
    """A typo in an env var must not take the API down on boot."""
    monkeypatch.setenv("MUSEFORGE_LOG_LEVEL", "chatty")
    api_mod._configure_logging()
    try:
        assert logging.getLogger("pipelines.idea2video").isEnabledFor(logging.INFO)
    finally:
        monkeypatch.delenv("MUSEFORGE_LOG_LEVEL", raising=False)
        api_mod._configure_logging()


def test_configuring_twice_does_not_double_every_line():
    """Imported twice, or run under a host that already installed a handler."""
    before = len(logging.getLogger().handlers)
    api_mod._configure_logging()
    api_mod._configure_logging()

    assert len(logging.getLogger().handlers) == before


def test_the_noisy_libraries_stay_at_warning():
    """httpx logs every request and moviepy every frame write. At INFO they
    bury the lines this exists to surface."""
    for noisy in ("httpx", "httpcore", "moviepy"):
        assert not logging.getLogger(noisy).isEnabledFor(logging.INFO)
        assert logging.getLogger(noisy).isEnabledFor(logging.WARNING)
