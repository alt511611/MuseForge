"""Lip sync has to survive the wait for a human.

`lipsync_enabled` is not a column on the jobs table. The row reader infers it
from ``result.lipsynced_scenes`` -- a list that only ever contains a scene
whose mouth was ACTUALLY driven, which is exactly what a job that has not
rendered yet cannot have. For a finished job that inference is right. For a
job parked at ``awaiting_script_approval`` it is always False.

That parked state used to be rare. Script approval now defaults ON, so every
job stops and waits for a person to read it — minutes during which the process
can restart or the entry can be evicted, and the resume then rendered with lip
sync silently off, on a run charged a credit per speaking scene.

The fix is to record the INTENT while it is still known, and to prefer it over
the evidence.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pytest  # noqa: E402

import jobs as jobs_mod  # noqa: E402


def _row(status, result):
    return {
        "id": "job-1",
        "status": status,
        "idea": "a drama",
        "result": result,
        "dialogue_enabled": True,
        "plan": "pro",
    }


# ── the regression ──────────────────────────────────────────────────────────


def test_a_job_awaiting_approval_remembers_it_wanted_lip_sync():
    """Nothing is rendered yet, so `lipsynced_scenes` cannot exist. Before the
    intent was recorded this resumed with lip sync off."""
    row = _row(
        "awaiting_script_approval",
        {"script": {"title": "T"}, "_lipsync_enabled": True},
    )

    assert jobs_mod._sb_row_to_dict(row)["lipsync_enabled"] is True


def test_a_job_that_did_not_want_it_does_not_gain_it():
    row = _row(
        "awaiting_script_approval",
        {"script": {"title": "T"}, "_lipsync_enabled": False},
    )

    assert jobs_mod._sb_row_to_dict(row)["lipsync_enabled"] is False


@pytest.mark.asyncio
async def test_the_restored_job_object_carries_the_intent_too(monkeypatch):
    """_sb_row_to_dict feeds the CLIENT. get_or_restore rebuilds the Job that
    actually RESUMES the render, and reading the evidence there was what
    dropped lip sync from every approved script that had been evicted."""
    row = _row(
        "awaiting_script_approval",
        {"script": {"title": "T"}, "_lipsync_enabled": True},
    )

    async def fake_get(job_id):
        return row

    monkeypatch.setattr(jobs_mod, "_sb_get", fake_get)
    store = jobs_mod.JobStore()

    job = await store.get_or_restore("job-1")

    assert job is not None
    assert job.lipsync_enabled is True


# ── the old inference is still right where it was right ─────────────────────


def test_a_finished_job_without_the_intent_falls_back_to_the_evidence():
    """Jobs made before the intent was recorded still report correctly: a
    non-empty `lipsynced_scenes` is proof the run had lip sync on."""
    row = _row("completed", {"lipsynced_scenes": [0, 2]})

    assert jobs_mod._sb_row_to_dict(row)["lipsync_enabled"] is True


def test_a_finished_job_that_never_synced_reports_false():
    row = _row("completed", {"lipsynced_scenes": []})

    assert jobs_mod._sb_row_to_dict(row)["lipsync_enabled"] is False


def test_a_row_with_no_result_at_all_does_not_crash():
    assert jobs_mod._sb_row_to_dict(_row("queued", None))["lipsync_enabled"] is False


# ── the intent must never reach the browser ─────────────────────────────────


def test_the_intent_is_server_side_machinery():
    """Underscore-prefixed keys are stripped before the result goes over the
    wire; the flag is reported on the job, not smuggled inside its result."""
    public = jobs_mod.public_result(
        {"script": {"title": "T"}, "_lipsync_enabled": True, "video_url": "u"}
    )

    assert "_lipsync_enabled" not in public
    assert public["video_url"] == "u"
