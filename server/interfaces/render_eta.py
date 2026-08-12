"""How long a render will take — modelled once, then MEASURED.

The number shown while a drama renders used to be a countdown from a constant.
``MUSEFORGE_SECONDS_PER_SCENE`` defaulted to 100, so a 5-scene job promised
"~4 min" whether the provider was answering in 40 seconds or in four minutes,
and the client simply subtracted wall-clock from it. Two consequences, both
of which read to the customer as the product being broken:

* the countdown hit zero long before the video did, and then sat on a rotating
  "almost there…" for the rest of the run — sometimes for another 20 minutes;
* it was never right for THIS job. The estimate the generate page fetched
  carried only ``num_scenes``, so a Pro job with dialogue and lip sync — the
  slowest configuration the product sells — was quoted the time of the
  cheapest one.

The fix is to stop treating the constant as the answer and start treating it
as the prior. A run has a shape that IS known up front (a fixed prologue, N
scenes in ceil(N/concurrency) batches, a fixed finishing tail), and exactly one
unknown: the rate. That rate is measurable — the moment the first batch of
scenes lands, this deployment has told us what a batch costs today, on this
provider, at this queue depth. Everything after that is arithmetic.

So: :func:`prior_seconds` answers "how long will this take" before anything has
run (it is what /api/estimate quotes), and :class:`RenderEta` answers "how long
is left" from what the run has actually done. The two share one model, so the
quote and the live countdown cannot drift apart.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

#: Screenplay, then the cast portraits and the set plate. Everything before the
#: first scene can start. Split out of the old flat "base" constant so the live
#: ETA can tell "still locking the cast" from "still assembling the master" --
#: they sit on opposite sides of the scene loop and cost different amounts.
PROLOGUE_SECONDS = float(os.environ.get("MUSEFORGE_ETA_PROLOGUE_SECONDS", "55"))

#: Concatenate, colour grade, audio mix, caption burn, finishing pass and
#: (Free plan) watermark. Pure ffmpeg on a file that already exists.
EPILOGUE_SECONDS = float(os.environ.get("MUSEFORGE_ETA_EPILOGUE_SECONDS", "35"))

#: Wall-clock for one BATCH of scenes (frame + clip). The prior only; once a
#: batch has actually completed, the measured value replaces it.
SECONDS_PER_SCENE = float(os.environ.get("MUSEFORGE_SECONDS_PER_SCENE", "100"))

#: Residual music cost after overlap with the scene loop (mix + leftover wait).
MUSIC_SECONDS = float(os.environ.get("MUSEFORGE_ESTIMATE_MUSIC_SECONDS", "45"))

#: Per-scene residual for dialogue TTS that may not fully overlap generation.
DIALOGUE_PER_SCENE = float(os.environ.get("MUSEFORGE_ESTIMATE_DIALOGUE_PER_SCENE", "20"))

#: Per speaking scene. Unlike dialogue TTS this cannot overlap generation: it
#: needs the finished clip AND the finished voice before it can start, so it is
#: added time and it lands in the TAIL, after the last scene.
LIPSYNC_PER_SCENE = float(os.environ.get("MUSEFORGE_ESTIMATE_LIPSYNC_PER_SCENE", "40"))

#: Demo mode runs no provider at all.
DEMO_SECONDS = 5

#: A measured rate this far from the prior is more likely a stall or a clock
#: oddity than a real speed-up/slow-down, so it is clamped rather than trusted.
#: Wide on purpose: a provider genuinely being three times slower than the prior
#: is exactly the case the customer most needs told about.
MIN_RATE_FACTOR = 0.2
MAX_RATE_FACTOR = 6.0

#: Floor for the batch currently rendering once it has run past what the
#: measured rate predicted. Keeps the countdown at "any second now" instead of
#: claiming zero while a provider call is still open.
OVERDUE_FLOOR_SECONDS = 10.0


def scene_batches(num_scenes: int, concurrency: int) -> int:
    """How many sequential rounds ``num_scenes`` takes at ``concurrency``."""
    num_scenes = max(1, int(num_scenes or 1))
    concurrency = max(1, int(concurrency or 1))
    return max(1, math.ceil(num_scenes / concurrency))


@dataclass(frozen=True)
class RenderPlan:
    """The shape of one run: what has to happen, and in what order.

    Deliberately not "a number of seconds" -- the phases stay separate because
    the live tracker needs to know which of them is still ahead.
    """

    num_scenes: int = 1
    concurrency: int = 1
    music: bool = False
    dialogue: bool = False
    lipsync: bool = False
    demo: bool = False
    #: False for post-production runs (a retake, a continuity edit). They reuse
    #: the script, the locked portraits and the set plate that the original job
    #: already paid for, so they start at the scene loop -- charging them for a
    #: prologue that will not happen is a minute of pure overestimate.
    include_prologue: bool = True

    @property
    def batches(self) -> int:
        return scene_batches(self.num_scenes, self.concurrency)

    @property
    def prologue(self) -> float:
        return PROLOGUE_SECONDS if self.include_prologue else 0.0

    @property
    def scenes(self) -> float:
        """Prior cost of the whole scene phase."""
        return self.batches * SECONDS_PER_SCENE

    @property
    def tail(self) -> float:
        """Everything after the last scene lands.

        Lip sync belongs here, not alongside the scenes: it is one request per
        speaking scene that cannot begin until that scene's clip and its voice
        both exist.
        """
        seconds = EPILOGUE_SECONDS
        if self.music:
            seconds += MUSIC_SECONDS
        if self.dialogue:
            seconds += self.num_scenes * DIALOGUE_PER_SCENE
        if self.lipsync:
            seconds += self.num_scenes * LIPSYNC_PER_SCENE
        return seconds

    @property
    def total(self) -> float:
        if self.demo:
            return float(DEMO_SECONDS)
        return self.prologue + self.scenes + self.tail


def prior_seconds(plan: RenderPlan) -> int:
    """The estimate to quote before anything has run. At least 1 second."""
    return max(1, int(round(plan.total)))


@dataclass
class RenderEta:
    """Remaining seconds for a run in flight, from what it has actually done.

    Fed by :meth:`observe` on every progress event. Until the first scene
    lands it can only repeat the prior; after that it reports a figure derived
    from this deployment's real throughput, which is the entire point.

    Every method is safe to call at any time and on any job -- a retake, a
    timeline re-cut, a job whose pipeline never reports scene counts -- and
    simply returns ``None`` when it has nothing honest to say. A missing ETA
    renders as no ETA, which beats a confident wrong one.
    """

    plan: RenderPlan = field(default_factory=RenderPlan)
    #: Until a caller arms this with a real plan there is nothing to count down
    #: from, and :meth:`remaining` says so rather than inventing a figure off
    #: the default plan.
    armed: bool = False
    #: Monotonic timestamp for the start of the run, and of the scene phase.
    started: Optional[float] = None
    scenes_started: Optional[float] = None
    scenes_done: int = 0
    #: When the most recent scene landed. The rate MUST be measured against
    #: this rather than against "now": derived from now, a batch that is simply
    #: still running makes the measured per-scene time grow every second, so
    #: the countdown climbs while you watch it -- the exact pathology of the
    #: progress-based extrapolation this replaced.
    scenes_done_at: Optional[float] = None
    #: Set once the last scene has landed and the tail has begun.
    tail_started: Optional[float] = None
    finished: bool = False

    # ── Feeding ───────────────────────────────────────────────────────────────

    def arm(self, plan: RenderPlan, now: float) -> None:
        """Begin tracking a run of this shape, starting now."""
        self.plan = plan
        self.armed = True
        self.started = now
        self.scenes_started = None
        self.scenes_done = 0
        self.scenes_done_at = None
        self.tail_started = None
        self.finished = False

    def observe(self, stage: str, data: Optional[Dict[str, Any]], now: float) -> None:
        """Record one progress event.

        ``data`` carries the scene counters when the pipeline is in its scene
        loop (see idea2video); every other event only moves the phase along.
        """
        if not self.armed:
            return
        if self.started is None:
            self.started = now
        if stage in ("complete", "cancelled", "error"):
            self.finished = True
            return

        if isinstance(data, dict) and data.get("scenes_total"):
            self.plan = RenderPlan(
                num_scenes=int(data["scenes_total"]),
                concurrency=int(data.get("scene_concurrency") or self.plan.concurrency),
                music=self.plan.music,
                dialogue=self.plan.dialogue,
                lipsync=self.plan.lipsync,
                demo=self.plan.demo,
            )
            if self.scenes_started is None:
                self.scenes_started = now
            done = int(data.get("scenes_completed") or 0)
            # Monotonic: scenes finish concurrently and events can interleave,
            # and an ETA that jumps backwards is worse than a stale one.
            if done > self.scenes_done:
                self.scenes_done = done
                self.scenes_done_at = now
            if self.scenes_done >= self.plan.num_scenes and self.tail_started is None:
                self.tail_started = now
            return

        # The scene loop is over the moment a tail stage appears, even if the
        # counters never reached N (a scene that produced no clip is skipped).
        if stage in _TAIL_STAGES and self.tail_started is None and self.scenes_started:
            self.tail_started = now

    # ── Reading ───────────────────────────────────────────────────────────────

    def elapsed(self, now: float) -> float:
        return max(0.0, now - self.started) if self.started is not None else 0.0

    def measured_batch_seconds(self) -> Optional[float]:
        """Wall-clock for one full batch, as this run has actually managed it.

        ``None`` until a scene has landed. Throughput is measured per SCENE and
        then multiplied back up by the concurrency, so the figure means "how
        long the next round will take" rather than "how long one scene took" --
        with three scenes rendering together those are different numbers, and
        the batch is the one that maps onto the clock.

        Takes no ``now``: this is a property of what has already HAPPENED, and
        must not move while a batch is merely in flight.
        """
        if not self.scenes_done or self.scenes_started is None:
            return None
        if self.scenes_done_at is None:
            return None
        scene_elapsed = self.scenes_done_at - self.scenes_started
        if scene_elapsed <= 0:
            return None
        per_scene = scene_elapsed / self.scenes_done
        batch = per_scene * max(1, self.plan.concurrency)
        # Clamp against the prior so one anomalous batch cannot produce a
        # nonsense countdown in either direction.
        return max(
            SECONDS_PER_SCENE * MIN_RATE_FACTOR,
            min(SECONDS_PER_SCENE * MAX_RATE_FACTOR, batch),
        )

    def remaining(self, now: float) -> Optional[int]:
        """Seconds left, or ``None`` when there is nothing honest to report."""
        if not self.armed or self.started is None:
            return None
        if self.finished:
            return 0
        elapsed = self.elapsed(now)

        if self.plan.demo:
            return max(0, int(round(DEMO_SECONDS - elapsed)))

        # ── In the tail: scenes are done, only finishing work is left ─────────
        if self.tail_started is not None:
            spent = now - self.tail_started
            return max(0, int(round(self.plan.tail - spent)))

        # ── In the scene loop, with at least one scene measured ───────────────
        batch_seconds = self.measured_batch_seconds()
        if batch_seconds is not None:
            scenes_left = max(0, self.plan.num_scenes - self.scenes_done)
            batches_left = scene_batches(scenes_left, self.plan.concurrency) if scenes_left else 0
            if not batches_left:
                return max(0, int(round(self.plan.tail)))
            # The batch in flight is already part-spent, so it is counted down
            # second by second rather than as a whole unit — otherwise the
            # figure freezes for a full batch and then drops in a visible step.
            in_flight = max(0.0, now - (self.scenes_done_at or now))
            current_left = batch_seconds - in_flight
            if current_left < OVERDUE_FLOOR_SECONDS:
                # Past what the measured rate predicted. Holding just above zero
                # is the honest reading — the work IS nearly done and we have no
                # evidence for a bigger number — and it beats both a wrong zero
                # and the old "almost there…" that replaced the clock entirely.
                current_left = OVERDUE_FLOOR_SECONDS
            remaining = current_left + (batches_left - 1) * batch_seconds
            return max(0, int(round(remaining + self.plan.tail)))

        # ── Nothing measured yet: the prior, less what has already gone ───────
        return max(0, int(round(self.plan.total - elapsed)))


#: Stages that only ever run after the last scene clip exists.
_TAIL_STAGES = frozenset(
    {"lipsync", "assembly", "grade", "music", "subtitles", "finishing"}
)
