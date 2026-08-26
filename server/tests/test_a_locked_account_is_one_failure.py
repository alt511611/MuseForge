"""Six correct fail-opens, one cause, and a silent film delivered as a success.

Job 930f11de-4b0 met the same provider answer six times -- foley on three
scenes and lip sync on three:

    HTTP 400: User is locked. Reason: Exhausted balance.

Every stage that met it did the right thing on its own. Foley is the layer a
film can most afford to lose; lip sync ships the unsynced clip rather than
failing a paid job. Nothing was in a position to notice that all six were the
same fact about the ACCOUNT rather than six facts about six calls, so the job
spent sixteen seconds and three more paid requests on refusals it had already
been given, delivered a master that was 75% digital silence over unsynced
mouths, and reported success.

An account out of balance is not a flaky call. It is a job-wide state, and
this is the type that says so.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from tools.muapi_client import (  # noqa: E402
    MuAPIAccountLocked,
    MuAPIError,
    is_account_locked,
)

#: The provider's own words, from the delivered job's log.
DELIVERED = (
    "MuAPI request failed after 1 attempt(s): HTTP 400: User is locked. "
    "Reason: Exhausted balance. Top up your balance at "
    "provider/dashboard/billing. (on /api/v1/predictions/ce93a961/result)"
)


# --- telling the account apart from the call -----------------------------


def test_the_delivered_refusal_is_recognised():
    assert is_account_locked(Exception(DELIVERED)) is True


@pytest.mark.parametrize(
    "message",
    [
        "HTTP 400: reference image does not contain a detectable face",
        "MuAPI job timed out after 600s",
        "HTTP 422: prompt exceeds the maximum length",
        "HTTP 503: upstream unavailable",
    ],
)
def test_an_ordinary_failure_is_not_an_account_lock(message):
    """Narrow on purpose: calling a flaky call terminal would stand down
    features that were about to work on the retry."""
    assert is_account_locked(Exception(message)) is False


def test_it_is_still_a_muapi_error():
    """Every caller that fails open on MuAPIError keeps doing so untouched."""
    assert issubclass(MuAPIAccountLocked, MuAPIError)


# --- the job stops paying for refusals it already has --------------------


async def _no_progress(*args, **kwargs):
    """A progress callback that records nothing; these tests watch the log."""


def _pipeline():
    from pipelines.idea2video import Idea2VideoPipeline

    return Idea2VideoPipeline("test-key-not-real", demo=False)


def test_a_fresh_job_has_not_seen_a_locked_account():
    assert _pipeline().account_locked is False


@pytest.mark.asyncio
async def test_lip_sync_is_not_attempted_after_the_account_has_refused(
    caplog, tmp_path, monkeypatch
):
    """The 16 seconds and three paid requests that came after foley's three."""
    import logging

    # The lock has to be the reason, so every cheaper reason to decline is
    # cleared first: this deployment has the feature on and the job asked.
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")

    pipeline = _pipeline()
    pipeline.account_locked = True

    with caplog.at_level(logging.WARNING):
        result = await pipeline._lipsync_scenes(
            scene_paths=["/tmp/does-not-matter.mp4"],
            dialogue_tracks=[
                {"scene_index": 0, "audio_url": "https://example.test/line.mp3"}
            ],
            working_dir=str(tmp_path),
            progress=_no_progress,
            requested=True,
        )

    assert result == []
    assert "already refusing" in caplog.text


@pytest.mark.asyncio
async def test_an_unlocked_job_still_reaches_the_ordinary_reasons(caplog, tmp_path):
    """The latch must not become a fifth way lip sync silently declines."""
    import logging

    pipeline = _pipeline()

    with caplog.at_level(logging.INFO):
        result = await pipeline._lipsync_scenes(
            scene_paths=[],
            dialogue_tracks=[],
            working_dir=str(tmp_path),
            progress=_no_progress,
            requested=True,
        )

    assert result == []
    # Declined for having nothing to sync, which is the honest reason here.
    assert "already refusing" not in caplog.text
