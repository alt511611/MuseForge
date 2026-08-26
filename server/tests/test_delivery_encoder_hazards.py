"""Three ways the delivery encoders quietly ruined a finished drama.

All three were found on one delivered master and the host that made it, and
all three are silent by construction -- every stage here fails open, so the
job still "succeeds" and the viewer gets the damage:

* **The mix hung forever**, in two places at once. A bare ``apad`` behind the
  ducking compressor never stops manufacturing silence, and ``adelay=0:all=1``
  -- which is what a line starting at 0.0 asks for, i.e. the first line of
  most dramas -- is its own loop. Nothing timed the mix, so the job sat at 99%
  burning a core until someone killed it.
* **The captions vanished.** ``subtitles`` and ``ass`` are libass filters and
  a stock Homebrew ffmpeg has neither. The filter failed to parse, the caption
  pass fell open, and the drama shipped with no captions and a warning.
* **The audio was re-encoded down.** The ffmpeg paths ask for 192k; moviepy
  asks for nothing and takes the encoder's default. A delivered master
  measured 65kbps.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines import idea2video  # noqa: E402
from pipelines.idea2video import (  # noqa: E402
    DELIVERY_AUDIO_BITRATE,
    build_audio_mix_graph,
    ffmpeg_can_burn_captions,
    resolve_caption_ffmpeg_binary,
)


# --- the mix that never finished ----------------------------------------


def test_a_layer_that_starts_at_zero_is_not_delayed_by_zero():
    """The hang, at its source: no adelay at all for a layer at 0.0."""
    graph = build_audio_mix_graph(1, [(2, 0.0)], [(3, 0.0)], 6.0)

    assert "adelay=0" not in graph
    # Not by dropping the layers -- they are still in the mix, just undelayed.
    assert "[2:a]aformat" in graph
    assert "[3:a]volume" in graph


def test_a_layer_that_starts_late_still_gets_its_delay():
    graph = build_audio_mix_graph(1, [(2, 1.25)], [], 6.0)

    assert "adelay=1250:all=1" in graph


def test_a_delay_rounding_down_to_nothing_is_dropped_too():
    """400 microseconds is not a delay either, and rounds to the same hang."""
    graph = build_audio_mix_graph(None, [(1, 0.0004)], [], 6.0)

    assert "adelay" not in graph


def test_the_pad_is_told_where_to_stop():
    """The second hang, and the one the foley suite actually caught.

    A bare ``apad`` pads forever and leaves atrim to end it. Behind amix and
    sidechaincompress, ffmpeg 9 never gets that far -- it generates and throws
    away silence at 100% CPU until something kills it.
    """
    graph = build_audio_mix_graph(1, [(2, 0.5)], [], 6.0)

    assert "apad=whole_dur=6.000" in graph
    assert ",apad," not in graph
    # The exact cut is still atrim's job; the pad only stops manufacturing.
    assert "atrim=0:6.000" in graph


@pytest.mark.asyncio
async def test_a_stuck_mixer_is_killed_rather_than_held_open(tmp_path, monkeypatch):
    """Whatever a future ffmpeg finds to hang on, the job does not wait for it."""
    import time

    # An "ffmpeg" that ignores its arguments and never returns, standing in for
    # the adelay=0 loop. A real one would outlive this test run.
    # exec, so the kill lands on the process actually holding the pipes rather
    # than on a shell that leaves a child behind still holding them.
    stuck = tmp_path / "stuck_ffmpeg"
    stuck.write_text("#!/bin/sh\nexec sleep 120\n", encoding="utf-8")
    stuck.chmod(0o755)

    monkeypatch.setattr(idea2video, "MIX_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(idea2video, "_probe_video_duration", lambda path: 6.0)
    monkeypatch.setattr(idea2video, "resolve_ffmpeg_binary", lambda: str(stuck))

    started = time.monotonic()
    result = await idea2video.mix_audio_layers(
        str(tmp_path / "in.mp4"),
        str(tmp_path / "out.mp4"),
        music_url=str(tmp_path / "music.wav"),
    )
    elapsed = time.monotonic() - started

    # None is the caller's signal to fall back to the moviepy mixer.
    assert result is None
    # The timeout is what ended it, not the process finishing on its own.
    assert elapsed < 30, f"the mixer was waited on for {elapsed:.1f}s"
    assert elapsed >= 1


# --- the captions that were not there ------------------------------------


def test_an_ffmpeg_without_libass_is_not_asked_to_burn_captions(monkeypatch):
    """A PATH ffmpeg built without libass loses the argument to the bundled one."""
    monkeypatch.setattr(idea2video, "resolve_ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(idea2video, "_bundled_ffmpeg_binary", lambda: "/bundled/ffmpeg")
    monkeypatch.setattr(
        idea2video,
        "ffmpeg_can_burn_captions",
        lambda binary: binary == "/bundled/ffmpeg",
    )

    assert resolve_caption_ffmpeg_binary() == "/bundled/ffmpeg"


def test_a_capable_ffmpeg_is_left_alone(monkeypatch):
    monkeypatch.setattr(idea2video, "resolve_ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(idea2video, "ffmpeg_can_burn_captions", lambda binary: True)

    assert resolve_caption_ffmpeg_binary() == "/usr/bin/ffmpeg"


def test_no_better_ffmpeg_means_the_configured_one_still_gets_its_try(monkeypatch):
    """With nothing to fall back to, the caller's own fail-open decides."""
    monkeypatch.setattr(idea2video, "resolve_ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setattr(idea2video, "_bundled_ffmpeg_binary", lambda: "")
    monkeypatch.setattr(idea2video, "ffmpeg_can_burn_captions", lambda binary: False)

    assert resolve_caption_ffmpeg_binary() == "/usr/bin/ffmpeg"


def test_an_unreadable_answer_does_not_demote_a_working_ffmpeg():
    """A probe that cannot run is not evidence of anything."""
    ffmpeg_can_burn_captions.cache_clear()
    assert ffmpeg_can_burn_captions("/definitely/not/an/ffmpeg") is True


@pytest.mark.skipif(
    not os.path.isfile(
        (lambda: __import__("shutil").which("ffmpeg") or "")()
    ),
    reason="ffmpeg not available",
)
def test_the_probe_agrees_with_the_ffmpeg_actually_installed():
    """Whatever this host's ffmpeg is, the probe's answer is the true one."""
    import shutil

    binary = shutil.which("ffmpeg")
    ffmpeg_can_burn_captions.cache_clear()
    probed = ffmpeg_can_burn_captions(binary)

    listed = subprocess.run(
        [binary, "-hide_banner", "-filters"], capture_output=True, timeout=30
    ).stdout.decode("utf-8", errors="replace")
    assert probed is (" subtitles " in listed)


# --- the audio that was thrown away --------------------------------------


def test_every_moviepy_pass_that_carries_audio_is_told_the_bitrate():
    """moviepy's default is not the delivery spec, and it does not ask."""
    source = open(idea2video.__file__, encoding="utf-8").read()

    audio_writes = source.count('audio_codec="aac"')
    bitrate_writes = source.count("audio_bitrate=DELIVERY_AUDIO_BITRATE")

    assert audio_writes, "no moviepy audio write found -- has this moved?"
    assert bitrate_writes == audio_writes


def test_both_encoders_read_the_delivery_bitrate_from_one_place():
    """The ffmpeg paths and the moviepy paths cannot drift apart again."""
    source = open(idea2video.__file__, encoding="utf-8").read()

    assert DELIVERY_AUDIO_BITRATE == "192k"
    # No stray literal to fall out of step with the constant.
    assert '"-b:a",\n        "192k"' not in source
    assert '"-b:a",\n            "192k"' not in source
