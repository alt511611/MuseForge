"""The remaining-time figure shown while a drama renders.

What it must do, and what the constant-countdown it replaced did not:

* never claim a job is finishing while it is still rendering scenes;
* count DOWN within a batch, not up (the old progress-based extrapolation
  climbed every second that progress% stalled against wall-clock);
* correct itself once this deployment's real scene rate is known, in both
  directions -- a provider answering in half the modelled time should shorten
  the estimate, not sit on the prior;
* say nothing at all when it has nothing to measure.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.render_eta import (  # noqa: E402
    EPILOGUE_SECONDS,
    PROLOGUE_SECONDS,
    SECONDS_PER_SCENE,
    RenderEta,
    RenderPlan,
    prior_seconds,
    scene_batches,
)


def _data(done, total=6, concurrency=3):
    return {
        "scenes_completed": done,
        "scenes_total": total,
        "scene_concurrency": concurrency,
    }


def _armed(num_scenes=6, concurrency=3, **kw):
    eta = RenderEta()
    eta.arm(RenderPlan(num_scenes=num_scenes, concurrency=concurrency, **kw), 0.0)
    return eta


# ── The prior ─────────────────────────────────────────────────────────────────

def test_batches_not_scene_count_drive_the_estimate():
    assert scene_batches(6, 3) == 2
    assert scene_batches(5, 3) == 2
    assert scene_batches(7, 3) == 3
    assert scene_batches(1, 3) == 1


def test_the_prior_is_prologue_plus_batches_plus_tail():
    plan = RenderPlan(num_scenes=6, concurrency=3)
    assert prior_seconds(plan) == round(
        PROLOGUE_SECONDS + 2 * SECONDS_PER_SCENE + EPILOGUE_SECONDS
    )


def test_post_production_is_not_quoted_a_prologue():
    """A retake reuses the script, the portraits and the set plate. Charging it
    for a fresh prologue overstates a one-scene retake by a whole minute."""
    retake = RenderPlan(num_scenes=1, concurrency=1, include_prologue=False)
    full = RenderPlan(num_scenes=1, concurrency=1)
    assert prior_seconds(full) - prior_seconds(retake) == round(PROLOGUE_SECONDS)


def test_lipsync_lands_in_the_tail_not_alongside_the_scenes():
    """It cannot start until a scene's clip AND its voice both exist, so it is
    added time after the last scene rather than time hidden under it."""
    plain = RenderPlan(num_scenes=4, concurrency=2)
    synced = RenderPlan(num_scenes=4, concurrency=2, dialogue=True, lipsync=True)
    assert synced.scenes == plain.scenes
    assert synced.tail > plain.tail


# ── Saying nothing rather than guessing ───────────────────────────────────────

def test_an_unarmed_tracker_reports_nothing():
    eta = RenderEta()
    assert eta.remaining(0.0) is None
    # Events on an unarmed tracker must not bring it to life with a default plan.
    eta.observe("video", _data(1), 10.0)
    assert eta.remaining(20.0) is None


# ── Measuring ─────────────────────────────────────────────────────────────────

def test_before_a_scene_lands_it_can_only_offer_the_prior():
    eta = _armed()
    eta.observe("video", _data(0), 55.0)
    total = prior_seconds(eta.plan)
    assert eta.remaining(55.0) == pytest.approx(total - 55, abs=1)
    assert eta.remaining(150.0) == pytest.approx(total - 150, abs=1)


def test_the_measured_rate_replaces_the_prior():
    """The whole point: a provider twice as slow as the model must produce a
    bigger number, derived from what it actually did."""
    eta = _armed()
    eta.observe("video", _data(0), 55.0)
    for n in (1, 2, 3):
        eta.observe("video", _data(n), 255.0)  # first batch took 200s, not 100s

    # One batch left at the MEASURED 200s, plus the finishing tail.
    assert eta.measured_batch_seconds() == pytest.approx(200.0)
    assert eta.remaining(255.0) == pytest.approx(200 + eta.plan.tail, abs=1)


def test_a_fast_provider_shortens_the_estimate():
    eta = _armed()
    eta.observe("video", _data(0), 55.0)
    for n in (1, 2, 3):
        eta.observe("video", _data(n), 95.0)  # batch took 40s
    assert eta.measured_batch_seconds() == pytest.approx(40.0)
    assert eta.remaining(95.0) < prior_seconds(eta.plan) - 95


def test_it_counts_down_inside_a_batch_never_up():
    """The regression that made the old ETA useless: while a batch was merely
    in flight, deriving the rate from `now` inflated it every second, so the
    countdown climbed while the user watched."""
    eta = _armed()
    eta.observe("video", _data(0), 55.0)
    for n in (1, 2, 3):
        eta.observe("video", _data(n), 255.0)

    readings = [eta.remaining(t) for t in range(255, 456, 10)]
    assert readings == sorted(readings, reverse=True), readings
    # And the measurement itself must not drift with idle time.
    assert eta.measured_batch_seconds() == pytest.approx(200.0)


def test_an_overdue_batch_holds_just_above_zero():
    """Past the measured rate we have no evidence for a bigger number, but we
    must not claim the job is done — and must not fall back to a spinner."""
    eta = _armed()
    eta.observe("video", _data(0), 55.0)
    for n in (1, 2, 3):
        eta.observe("video", _data(n), 255.0)
    overdue = eta.remaining(1000.0)
    assert 0 < overdue <= eta.plan.tail + 15


def test_the_tail_is_all_that_is_left_once_scenes_are_done():
    eta = _armed()
    eta.observe("video", _data(0), 55.0)
    for n in range(1, 7):
        eta.observe("video", _data(n), 455.0)
    assert eta.remaining(455.0) == pytest.approx(eta.plan.tail, abs=1)
    assert eta.remaining(455.0 + eta.plan.tail) == 0


def test_a_tail_stage_ends_the_scene_phase_even_if_a_scene_was_skipped():
    """A scene that produced no clip never reaches the counter, so the phase
    has to close on the first finishing stage or the ETA would never come down."""
    eta = _armed()
    eta.observe("video", _data(0), 55.0)
    for n in (1, 2, 3, 4, 5):
        eta.observe("video", _data(n), 300.0)
    eta.observe("assembly", None, 320.0)
    assert eta.remaining(320.0) == pytest.approx(eta.plan.tail, abs=1)


def test_scene_counters_never_go_backwards():
    """Scenes finish concurrently and their events can interleave."""
    eta = _armed()
    eta.observe("video", _data(0), 55.0)
    eta.observe("video", _data(3), 255.0)
    eta.observe("video", _data(2), 256.0)  # a straggler reporting late
    assert eta.scenes_done == 3
    assert eta.scenes_done_at == 255.0


def test_a_finished_run_reports_zero():
    eta = _armed()
    eta.observe("video", _data(0), 55.0)
    eta.observe("complete", None, 300.0)
    assert eta.remaining(300.0) == 0


def test_demo_runs_are_near_instant():
    eta = RenderEta()
    eta.arm(RenderPlan(num_scenes=6, concurrency=3, demo=True), 0.0)
    assert eta.remaining(0.0) <= 5
    assert eta.remaining(30.0) == 0


# ── Wiring: the job actually reports it ───────────────────────────────────────

def test_the_job_exposes_a_measured_eta():
    import jobs as jobs_mod

    job = jobs_mod.Job(id="j1", num_scenes=6)
    assert job.eta_seconds() is None, "an un-started job has nothing to promise"

    jobs_mod.arm_job_eta(job)
    job.status = jobs_mod.JobStatus.RUNNING
    assert job.eta_seconds() > 0
    assert job.to_dict()["eta_seconds"] == pytest.approx(job.eta_seconds(), abs=2)

    job.status = jobs_mod.JobStatus.COMPLETED
    assert job.eta_seconds() == 0


def test_a_job_waiting_on_the_user_promises_nothing():
    """Parked on script approval, any countdown would be measuring how long the
    reader takes with their own script."""
    import jobs as jobs_mod

    job = jobs_mod.Job(id="j2", num_scenes=3)
    jobs_mod.arm_job_eta(job)
    job.status = jobs_mod.JobStatus.AWAITING_SCRIPT_APPROVAL
    assert job.eta_seconds() is None


@pytest.mark.asyncio
async def test_emitted_events_carry_the_eta():
    import jobs as jobs_mod

    store = jobs_mod.JobStore()
    job = jobs_mod.Job(id="j3", num_scenes=6)
    jobs_mod.arm_job_eta(job)
    job.status = jobs_mod.JobStatus.RUNNING

    await store.emit(job, "video", "Rendering 6 scene(s)", 15, _data(0))
    assert job.events[-1].eta_seconds > 0
    assert "eta_seconds" in job.events[-1].to_dict()


# ── The pipeline really reports what the tracker needs ────────────────────────

@pytest.mark.asyncio
async def test_the_pipeline_emits_the_counters_the_eta_measures(tmp_path):
    """The ETA is only as real as this contract.

    If these keys are ever renamed the tracker silently falls back to the prior
    for the whole run — the countdown keeps working, it just stops being true,
    which is precisely the failure that is hard to notice in review.
    """
    from pipelines.idea2video import Idea2VideoPipeline

    events = []

    async def capture(stage, message, progress, data=None):
        events.append((stage, data))

    pipeline = Idea2VideoPipeline(api_key="test-key-not-real", demo=True)
    await pipeline.run(
        idea="A letter left in a lighthouse",
        num_scenes=4,
        working_dir=str(tmp_path),
        progress_callback=capture,
    )

    counter_events = [d for _, d in events if isinstance(d, dict) and "scenes_total" in d]
    assert counter_events, "no scene counters reached the ETA tracker"

    # The phase must be OPENED before the first scene lands, or the tracker has
    # no start time to measure a rate against and can never leave the prior.
    assert counter_events[0]["scenes_completed"] == 0
    assert counter_events[0]["scenes_total"] == 4
    assert counter_events[0]["scene_concurrency"] >= 1

    # ...and it must run all the way to the full count.
    assert counter_events[-1]["scenes_completed"] == 4
    assert [d["scenes_completed"] for d in counter_events] == sorted(
        d["scenes_completed"] for d in counter_events
    )
