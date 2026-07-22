"""Color grading (apply_color_grade) and opt-in crossfade scene
transitions (concatenate_videos_with_transitions) -- pure ffmpeg/moviepy,
no extra API calls or cost. Both fail open to the original/plain video.
"""

import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_clips(tmp_path, count=3, duration=0.4):
    """Create codec/size-matched real MP4 clips."""
    from moviepy import ColorClip

    paths = []
    for idx in range(count):
        path = str(tmp_path / f"clip_{idx}.mp4")
        clip = ColorClip(
            size=(160, 90),
            color=((idx + 1) * 40, 80, 140),
            duration=duration,
        )
        clip.write_videofile(
            path,
            fps=10,
            codec="libx264",
            audio=False,
            logger=None,
        )
        clip.close()
        paths.append(path)
    return paths


def _duration_seconds(path):
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        output = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            text=True,
        )
        return float(output.strip())

    from moviepy import VideoFileClip

    clip = VideoFileClip(path)
    try:
        return float(clip.duration)
    finally:
        clip.close()


@pytest.mark.asyncio
async def test_apply_color_grade_produces_playable_output(tmp_path):
    from pipelines.script2video import apply_color_grade

    [source] = _make_clips(tmp_path, count=1, duration=0.5)
    output = str(tmp_path / "graded.mp4")

    result = await apply_color_grade(source, output)

    assert result == output
    assert os.path.isfile(output)
    assert os.path.getsize(output) > 0
    # Grading must not meaningfully change the clip's duration.
    assert abs(_duration_seconds(output) - 0.5) < 0.25


@pytest.mark.asyncio
async def test_apply_color_grade_fails_open_on_bad_input(tmp_path):
    """Unreadable/invalid source video must ship through untouched rather
    than failing the job -- same fail-open pattern as add_watermark()."""
    from pipelines.script2video import apply_color_grade

    source = str(tmp_path / "not_a_video.mp4")
    with open(source, "wb") as f:
        f.write(b"definitely-not-a-video-file")
    output = str(tmp_path / "graded.mp4")

    result = await apply_color_grade(source, output)

    assert result == output
    with open(output, "rb") as f:
        assert f.read() == b"definitely-not-a-video-file"


@pytest.mark.asyncio
async def test_color_grade_inserted_between_concat_and_music(tmp_path, monkeypatch):
    """_assemble_final_drama must color-grade the concatenated video BEFORE
    handing it to the music-mixing step."""
    from pipelines.idea2video import Idea2VideoPipeline

    calls = []

    async def _fake_concat(scene_paths, output_path):
        calls.append(("concat", output_path))
        with open(output_path, "wb") as f:
            f.write(b"concatenated")
        return output_path

    async def _fake_grade(video_path, output_path, style="cinematic"):
        calls.append(("grade", video_path))
        with open(output_path, "wb") as f:
            f.write(b"graded")
        return output_path

    async def _fake_music(video_path, output_path, music_url=None):
        calls.append(("music", video_path))
        with open(output_path, "wb") as f:
            f.write(b"with-music")
        return output_path

    monkeypatch.setattr("pipelines.idea2video.concatenate_videos", _fake_concat)
    monkeypatch.setattr("pipelines.idea2video.apply_color_grade", _fake_grade)
    monkeypatch.setattr("pipelines.idea2video.add_background_music", _fake_music)

    pipeline = Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(["scene0.mp4"], str(tmp_path / "job"), plan="pro")

    steps = [c[0] for c in calls]
    assert steps == ["concat", "grade", "music"], steps
    # Music must receive the GRADED file's path, not the raw concatenated one.
    graded_path_used_for_music = calls[2][1]
    concatenated_path_used_for_grade = calls[1][1]
    assert os.path.basename(concatenated_path_used_for_grade) == "drama_concatenated.mp4"
    assert os.path.basename(graded_path_used_for_music) == "drama_graded.mp4"


def test_scene_transitions_disabled_by_default(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_SCENE_TRANSITIONS", raising=False)
    from pipelines.script2video import is_scene_transitions_enabled

    assert is_scene_transitions_enabled() is False


def test_scene_transitions_enabled_via_env(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_SCENE_TRANSITIONS", "1")
    from pipelines.script2video import is_scene_transitions_enabled

    assert is_scene_transitions_enabled() is True


@pytest.mark.asyncio
async def test_transitions_default_off_uses_plain_concat(tmp_path, monkeypatch):
    """Without the env var, _assemble_final_drama must use the plain
    (transition-less) concat path, never the heavier crossfade one."""
    monkeypatch.delenv("MUSEFORGE_SCENE_TRANSITIONS", raising=False)
    from pipelines.idea2video import Idea2VideoPipeline

    def _must_not_run(*_a, **_k):
        raise AssertionError("crossfade concat must not run when disabled")

    async def _fake_plain_concat(scene_paths, output_path):
        with open(output_path, "wb") as f:
            f.write(b"concatenated")
        return output_path

    async def _fake_grade(video_path, output_path, style="cinematic"):
        with open(output_path, "wb") as f:
            f.write(b"graded")
        return output_path

    async def _fake_music(video_path, output_path, music_url=None):
        with open(output_path, "wb") as f:
            f.write(b"with-music")
        return output_path

    monkeypatch.setattr("pipelines.idea2video.concatenate_videos", _fake_plain_concat)
    monkeypatch.setattr(
        "pipelines.idea2video.concatenate_videos_with_transitions", _must_not_run
    )
    monkeypatch.setattr("pipelines.idea2video.apply_color_grade", _fake_grade)
    monkeypatch.setattr("pipelines.idea2video.add_background_music", _fake_music)

    pipeline = Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(["scene0.mp4"], str(tmp_path / "job"), plan="free")


@pytest.mark.asyncio
async def test_transitions_enabled_routes_through_crossfade_concat(tmp_path, monkeypatch):
    monkeypatch.setenv("MUSEFORGE_SCENE_TRANSITIONS", "1")
    from pipelines.idea2video import Idea2VideoPipeline

    calls = {"crossfade": 0, "plain": 0}

    async def _must_not_run_plain(*_a, **_k):
        calls["plain"] += 1
        raise AssertionError("plain concat must not run when transitions enabled")

    async def _fake_crossfade_concat(scene_paths, output_path):
        calls["crossfade"] += 1
        with open(output_path, "wb") as f:
            f.write(b"concatenated-with-transitions")
        return output_path

    async def _fake_grade(video_path, output_path, style="cinematic"):
        with open(output_path, "wb") as f:
            f.write(b"graded")
        return output_path

    async def _fake_music(video_path, output_path, music_url=None):
        with open(output_path, "wb") as f:
            f.write(b"with-music")
        return output_path

    monkeypatch.setattr("pipelines.idea2video.concatenate_videos", _must_not_run_plain)
    monkeypatch.setattr(
        "pipelines.idea2video.concatenate_videos_with_transitions", _fake_crossfade_concat
    )
    monkeypatch.setattr("pipelines.idea2video.apply_color_grade", _fake_grade)
    monkeypatch.setattr("pipelines.idea2video.add_background_music", _fake_music)

    pipeline = Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(
        ["scene0.mp4", "scene1.mp4"], str(tmp_path / "job"), plan="free"
    )

    assert calls == {"crossfade": 1, "plain": 0}


@pytest.mark.asyncio
async def test_crossfade_concat_real_clips_preserves_approx_duration(tmp_path):
    """Real crossfade concat of 3 clips (0.5s crossfade overlap each) must
    produce a shorter-than-sum-but-still-substantial output, not crash."""
    from pipelines.script2video import concatenate_videos_with_transitions

    paths = _make_clips(tmp_path, count=3, duration=1.0)
    output = str(tmp_path / "crossfade.mp4")

    result = await concatenate_videos_with_transitions(paths, output, transition_duration=0.3)

    assert result == output
    assert os.path.isfile(output)
    # 3 clips x 1.0s each, minus 2 overlaps x 0.3s = ~2.4s.
    assert 1.5 < _duration_seconds(output) < 3.2


@pytest.mark.asyncio
async def test_crossfade_concat_fails_open_to_plain_concat(tmp_path, monkeypatch):
    """If the crossfade render itself errors, fall back to the plain
    (transition-less) concatenate_videos() path rather than failing."""
    import pipelines.script2video as script2video

    paths = _make_clips(tmp_path, count=2, duration=0.4)
    output = str(tmp_path / "crossfade_fallback.mp4")

    def _broken_concatenate_videoclips(*_a, **_k):
        raise RuntimeError("synthetic compose failure")

    import moviepy

    monkeypatch.setattr(moviepy, "concatenate_videoclips", _broken_concatenate_videoclips)

    result = await script2video.concatenate_videos_with_transitions(paths, output)

    assert result == output
    assert os.path.isfile(output)
    # Fallback used the plain concat path (real ffmpeg concat demuxer).
    assert abs(_duration_seconds(output) - 0.8) < 0.3
