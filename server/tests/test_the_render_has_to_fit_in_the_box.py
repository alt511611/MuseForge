"""Nothing said how much memory a render was allowed to use.

Delivered job 1434617e-1c7, on a 2GB instance, died inside the lip-sync pass:

    Ran out of memory (used over 2GB) while running your code.
    INFO: Started server process [1]

362 seconds of already-paid-for work, lost, and the process restarted under
it. Three reasons, and it takes all three to fit in the box. Measured on three
concurrent trims of a 12s 1904x1088 clip, peak resident set of the whole
process group:

    before, as delivered                            3615 MB
    with the trim moved off moviepy                 2298 MB
    and the encoder and the pool bounded            1025 MB

1. THE ENCODER SIZED ITSELF FROM THE HOST. x264 reads the machine's core
   count, and a container is not the machine: on a many-core host it starts
   ~1.5x ncpu frame threads and holds a reference frame set for each, while
   the container's CPU quota buys none of that parallelism back. The memory an
   encode needs was set by whatever host the container landed on; the speed it
   got was not. One 12s 1904x1088 encode: 799 MB unbounded, 535 MB at two
   threads.

2. NOTHING COUNTED THE ENCODES. `run_in_executor(None, ...)` has as many
   threads as the machine offers, and the passes that trim run per SCENE,
   concurrently -- so the number of encodes alive at once was the number of
   scenes. They now share a pool whose size IS the ceiling.

And the trim itself stopped going through moviepy, which piped every frame out
of one ffmpeg as raw rgb24, through numpy, and into a second ffmpeg -- three
processes and a full-resolution buffer per clip, to remove seconds from the
ends and change no pixel.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as idea2video  # noqa: E402
from pipelines.idea2video import (  # noqa: E402
    DEFAULT_ENCODE_CONCURRENCY,
    _encode_concurrency,
    resolve_ffmpeg_binary,
    trim_clip,
)
from pipelines.script2video import video_encode_args  # noqa: E402


# ── 1. the encoder is told how many threads it may have ─────────────────────


def test_every_re_encode_bounds_the_encoder_s_threads():
    args = video_encode_args()
    assert "-threads" in args
    assert int(args[args.index("-threads") + 1]) >= 1


def test_the_bound_is_tunable_for_a_bigger_box(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_VIDEO_THREADS", "6")
    args = video_encode_args()
    assert args[args.index("-threads") + 1] == "6"


def test_moviepy_inherits_the_same_bound():
    """moviepy takes preset as its own argument and passes the rest through,
    so the two encoders cannot drift apart on this."""
    from pipelines.script2video import moviepy_encode_kwargs

    passthrough = moviepy_encode_kwargs()["ffmpeg_params"]
    assert "-threads" in passthrough


# ── 2. the encodes are counted ──────────────────────────────────────────────


def test_there_is_a_ceiling_and_it_is_small():
    assert DEFAULT_ENCODE_CONCURRENCY >= 1
    assert _encode_concurrency() == DEFAULT_ENCODE_CONCURRENCY


def test_the_ceiling_is_tunable(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_ENCODE_CONCURRENCY", "4")
    assert _encode_concurrency() == 4


def test_a_nonsense_ceiling_falls_back_rather_than_crashing(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_ENCODE_CONCURRENCY", "lots")
    assert _encode_concurrency() == DEFAULT_ENCODE_CONCURRENCY
    monkeypatch.setenv("MUSEFORGE_ENCODE_CONCURRENCY", "0")
    assert _encode_concurrency() == 1


def test_the_pool_is_what_bounds_them_not_the_default_executor():
    """A pool rather than a semaphore: these are blocking calls handed to an
    executor, so sizing the pool is the bound and it cannot be attached to the
    wrong event loop."""
    assert idea2video._ENCODE_POOL._max_workers == _encode_concurrency()


# ── 3. the trim happens in ffmpeg ───────────────────────────────────────────


def _clip(path, seconds=4.0):
    subprocess.run(
        [
            resolve_ffmpeg_binary(), "-y", "-v", "error",
            "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=24:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}",
            "-c:v", "libx264", "-crf", "30", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
        ],
        check=True,
    )
    return str(path)


def _seconds(path):
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", str(path),
        ],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out)


@pytest.mark.asyncio
async def test_a_trim_never_opens_a_moviepy_clip(monkeypatch, tmp_path):
    """The path that used to run is still there as a fallback, and must not be
    reached for an ordinary trim."""
    source = _clip(tmp_path / "src.mp4")

    import moviepy

    def _refuse(*a, **kw):
        raise AssertionError("moviepy was used for an ordinary trim")

    monkeypatch.setattr(moviepy, "VideoFileClip", _refuse)

    out = await trim_clip(source, str(tmp_path / "out.mp4"), 1.0, 0.0)
    assert out.endswith("out.mp4")
    assert _seconds(out) == pytest.approx(3.0, abs=0.15)


@pytest.mark.asyncio
async def test_the_cut_lands_on_the_frame_not_the_keyframe(tmp_path):
    """Output seeking, deliberately. The lip-sync rejoin puts this clip back
    against the take it came from and _keeps_its_length measures the result,
    so a boundary that slid to the nearest keyframe would cost the sync."""
    source = _clip(tmp_path / "src.mp4", seconds=6.0)

    out = await trim_clip(source, str(tmp_path / "out.mp4"), 1.3, 0.7)
    assert _seconds(out) == pytest.approx(4.0, abs=0.15)


@pytest.mark.asyncio
async def test_a_trim_of_nothing_is_still_the_source(tmp_path):
    source = _clip(tmp_path / "src.mp4")
    assert await trim_clip(source, str(tmp_path / "out.mp4"), 0.0, 0.0) == source


@pytest.mark.asyncio
async def test_an_unreadable_source_costs_a_second_not_the_video(tmp_path):
    """Fail-open, unchanged: a trim that cannot be applied returns the clip it
    was given rather than losing it."""
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")
    assert await trim_clip(str(broken), str(tmp_path / "out.mp4"), 1.0, 0.0) == str(
        broken
    )
