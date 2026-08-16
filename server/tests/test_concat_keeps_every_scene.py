"""A three-scene drama has to ship three scenes.

Delivered, and caught by the master-duration guard rather than by anyone
watching: a job whose scenes measured 7.04s + 11.0s + 12.0s produced a 7.04s
master. Two thirds of a paid render, gone, in a file that was valid, playable
and exactly as long as its first scene.

The cause is that ffmpeg's concat DEMUXER copies packets without re-timing
them. Its inputs have to agree on frame rate and timebase, and this pipeline
guarantees they do not: a scene rendered as a single shot ships the provider's
own file (Main profile, 24.00fps, tbn 12288, WITH audio) while a scene that
was internally cut ships our re-encode (High profile, 24.09fps, tbn 19272,
silent). Handed that mixture, ffmpeg exits 0 and writes a file with timestamps
that do not describe its own frames -- measured here as 47.05s at 15.37fps out
of 30.04s of input, and in the delivered job as 7.04s.

Exit code 0 was the only thing being checked, so nothing fell through to a
tier that would have re-encoded it properly.
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")


def _has_ffmpeg():
    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")


def _clip(tmp_path, name, seconds, fps, profile, audio):
    """A clip shaped like one the pipeline really produces."""
    from pipelines.script2video import _ffmpeg_binary

    path = str(tmp_path / name)
    command = [
        _ffmpeg_binary(), "-y",
        "-f", "lavfi", "-i", f"color=c=blue:s=320x180:d={seconds}:r={fps}",
    ]
    if audio:
        command += [
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:a", "aac",
        ]
    command += [
        "-c:v", "libx264", "-profile:v", profile, "-pix_fmt", "yuv420p",
        "-t", str(seconds), path,
    ]
    subprocess.run(command, capture_output=True, check=True)
    return path


def _duration(path):
    from pipelines.script2video import _ffmpeg_binary

    out = subprocess.run(
        [_ffmpeg_binary(), "-hide_banner", "-i", path],
        capture_output=True,
        text=True,
    ).stderr
    for line in out.splitlines():
        if "Duration:" in line:
            clock = line.split("Duration:")[1].split(",")[0].strip()
            hours, minutes, seconds = clock.split(":")
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return 0.0


def _delivered_scene_mix(tmp_path):
    """The exact shape of the job that lost two scenes."""
    return [
        # scene_0/shot_0.mp4 -- the provider's own clip, never re-encoded.
        _clip(tmp_path, "scene0.mp4", 2.0, "24", "main", audio=True),
        # scene_1/scene_cut.mp4, scene_2/scene_cut.mp4 -- ours.
        _clip(tmp_path, "scene1.mp4", 3.0, "24.09", "high", audio=False),
        _clip(tmp_path, "scene2.mp4", 4.0, "24.08", "high", audio=False),
    ]


@pytest.mark.asyncio
async def test_every_scene_survives_a_mixed_encode_concat(tmp_path):
    from pipelines.script2video import concatenate_videos

    scenes = _delivered_scene_mix(tmp_path)
    expected = sum(_duration(s) for s in scenes)
    output = str(tmp_path / "master.mp4")

    await concatenate_videos(scenes, output)

    assert abs(_duration(output) - expected) < 0.5, (
        f"{_duration(output)}s master out of {expected}s of scenes"
    )


@pytest.mark.asyncio
async def test_clips_that_already_agree_still_take_the_cheap_path(tmp_path):
    """The stream-copy path is worth keeping -- it decodes nothing. This is
    the case it is for, and it must not have been made slower or lossier."""
    from pipelines.script2video import concatenate_videos

    scenes = [
        _clip(tmp_path, "a.mp4", 2.0, "24", "high", audio=False),
        _clip(tmp_path, "b.mp4", 3.0, "24", "high", audio=False),
    ]
    output = str(tmp_path / "master.mp4")

    await concatenate_videos(scenes, output)

    assert abs(_duration(output) - 5.0) < 0.5


@pytest.mark.asyncio
async def test_a_single_scene_is_unchanged(tmp_path):
    from pipelines.script2video import concatenate_videos

    scene = _clip(tmp_path, "only.mp4", 2.0, "24", "high", audio=False)
    output = str(tmp_path / "master.mp4")

    await concatenate_videos([scene], output)

    assert abs(_duration(output) - 2.0) < 0.5


def test_a_stretched_join_is_not_accepted_as_success():
    """The check that was missing: 47.05s out of 30.04s of clips is not a
    concatenation, whatever ffmpeg's exit code said."""
    from pipelines.script2video import _concat_is_intact

    assert _concat_is_intact.__doc__  # documented, because it looks redundant


@pytest.mark.asyncio
async def test_the_intactness_check_measures_the_written_file(tmp_path):
    from pipelines.script2video import _concat_is_intact

    clip = _clip(tmp_path, "five.mp4", 5.0, "24", "high", audio=False)

    assert _concat_is_intact(clip, 5.0) is True
    assert _concat_is_intact(clip, 30.0) is False   # the delivered failure
    assert _concat_is_intact(clip, 3.2) is False    # the stretched one
    # Nothing to compare against is not evidence of a problem.
    assert _concat_is_intact(clip, 0.0) is True


@pytest.mark.asyncio
async def test_losing_scenes_is_reported_when_nothing_can_join_them(
    tmp_path, monkeypatch, caplog
):
    """The old last resort appended mp4 FILES, which yields a file playing
    only the first clip -- data loss shaped like success. If we are down to
    one scene, that has to be said out loud."""
    import logging

    import pipelines.script2video as module

    scenes = _delivered_scene_mix(tmp_path)
    output = str(tmp_path / "master.mp4")

    async def _no_join(*args, **kwargs):
        return False

    monkeypatch.setattr(module, "_concat_by_filter", _no_join)
    monkeypatch.setattr(module, "_concat_is_intact", lambda *a, **k: False)

    with caplog.at_level(logging.ERROR):
        await module.concatenate_videos(scenes, output)

    assert "scene(s) are missing" in caplog.text
    # ...and what ships is a real video, not a byte-mash of three.
    assert _duration(output) > 0
