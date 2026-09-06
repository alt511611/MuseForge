"""Lip sync is only worth buying where the mouth is big enough to read.

Scenes were selected for sync on one question -- "does this scene have
dialogue audio?" -- and nothing ever asked whether the result would be
visible. Delivered job 1ac6d945-b53 is what that costs. Its lip-sync stage ran
311 seconds of an 862-second render (36%, the largest single stage), and its
third scene speaks "What are you--" over a harbour wide with the speaker at
the frame edge, her head about forty pixels tall in a 1080p frame. Roughly a
third of the stage went on a mouth twelve pixels across, plus the rejoin
re-encode behind it, for a difference no viewer can see.

The question is asked of the angles the LINE REACHES, not of the scene: a
scene that opens wide and cuts to a close-up while the words are still running
is still worth syncing, and it is only when every speaking angle is a wide
that the sync buys nothing.

Every step fails OPEN, which is the contract the rest of the pass keeps: no
storyboard, no framing, or an unmeasured line all sync exactly as before.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as mod  # noqa: E402
from interfaces.shot_plan import framing_shows_a_face  # noqa: E402


def _shot(shot_type, seconds=6.04, role="master"):
    """A shot in the shape the pipeline actually carries at sync time.

    A dict, not a StoryboardShot: script2video records `shot.model_dump()`
    into shot_meta, and that is what reaches _lipsync_scenes.
    """
    return {
        "shot_type": shot_type,
        "role": role,
        "duration_seconds": seconds,
        "deliver_seconds": 0.0,
    }


def _line(text="What are you—", seconds=None):
    track = {"line": text, "character": "mira kess"}
    if seconds is not None:
        track["duration"] = seconds
    return track


# ── which framings show a face ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "framing",
    ["wide shot", "extreme wide shot", "establishing shot", "aerial view",
     "long shot", "drone shot", "WIDE"],
)
def test_a_wide_does_not_show_a_face(framing):
    assert framing_shows_a_face(framing) is False


@pytest.mark.parametrize(
    "framing",
    ["medium shot", "close-up", "extreme close-up", "medium close-up",
     "over-the-shoulder", "two shot", "portrait"],
)
def test_a_medium_or_tighter_shows_a_face(framing):
    assert framing_shows_a_face(framing) is True


def test_a_compound_framing_is_decided_by_its_tighter_half():
    """A medium wide is a face. The word it shares with a wide shot is not the
    word that decides it -- and reading it as a wide would decline the sync on
    the most ordinary dialogue framing there is."""
    assert framing_shows_a_face("medium wide") is True
    assert framing_shows_a_face("wide medium shot") is True


@pytest.mark.parametrize("framing", ["", None, "   ", "hero angle"])
def test_an_unknown_framing_is_treated_as_a_face(framing):
    """Fail open: a storyboard that stops filling shot_type loses no feature."""
    assert framing_shows_a_face(framing) is True


# ── the delivered job ───────────────────────────────────────────────────────


def test_the_delivered_job_stops_paying_for_its_climax():
    """Scene 3 of 1ac6d945-b53: 12.08s cut 6.04 + 6.04, a 1.38s line, and the
    words are over long before the second angle opens. The only angle under
    the line is the harbour wide."""
    shots = [_shot("extreme wide shot"), _shot("medium close-up")]

    assert mod._speaks_in_a_readable_framing(
        shots, [_line()], line_seconds=1.38
    ) is False


def test_a_line_that_runs_into_the_close_up_is_still_synced():
    """The same coverage, a longer line. The words are still playing when the
    close-up opens, so there is a mouth worth driving after all."""
    shots = [_shot("extreme wide shot"), _shot("medium close-up")]

    assert mod._speaks_in_a_readable_framing(
        shots, [_line("What are you doing all the way out here in this rain")],
        line_seconds=8.0,
    ) is True


def test_a_scene_shot_entirely_wide_is_declined():
    shots = [_shot("wide shot"), _shot("establishing shot")]

    assert mod._speaks_in_a_readable_framing(
        shots, [_line()], line_seconds=9.0
    ) is False


def test_an_ordinary_single_angle_scene_is_untouched():
    """The overwhelming majority of scenes: one medium, one line, synced as it
    always was."""
    assert mod._speaks_in_a_readable_framing(
        [_shot("medium shot", seconds=8.0)], [_line("Manifest says this bay's empty.")],
        line_seconds=1.76,
    ) is True


# ── failing open ────────────────────────────────────────────────────────────


def test_no_storyboard_syncs_as_before():
    """A regenerated scene, a legacy job record, a demo run: nothing to read a
    framing off, so nothing is declined."""
    assert mod._speaks_in_a_readable_framing(None, [_line()], 1.38) is True
    assert mod._speaks_in_a_readable_framing([], [_line()], 1.38) is True


def test_shots_with_no_framing_sync_as_before():
    assert mod._speaks_in_a_readable_framing(
        [_shot(""), _shot(None)], [_line()], line_seconds=1.38
    ) is True


def test_an_unmeasured_line_falls_back_to_its_words():
    """No measurement (a provider without timings). shots_the_line_reaches
    estimates from the word count at its slowest speaking rate, which is the
    generous direction -- more angles counted as speaking, so the wide is more
    likely to be joined by a close-up and the sync kept."""
    shots = [_shot("extreme wide shot"), _shot("medium close-up")]
    long_line = _line(" ".join(["word"] * 40))

    assert mod._speaks_in_a_readable_framing(
        shots, [long_line], line_seconds=None
    ) is True


def test_a_reaction_cutaway_is_not_counted_as_a_speaking_angle():
    """A reaction shot is the other character listening; there is no mouth in
    it to drive whatever the clock says. So a wide master with a close-up
    REACTION behind it is still declined -- the close-up is not speaking."""
    shots = [
        _shot("wide shot", seconds=10.0),
        _shot("extreme close-up", seconds=2.0, role="reaction"),
    ]

    assert mod._speaks_in_a_readable_framing(
        shots, [_line()], line_seconds=11.0
    ) is False
