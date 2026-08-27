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
    """With no finishing pass to ride, the grade keeps the pass it has always
    had: _assemble_final_drama grades the concatenated video BEFORE handing it
    to the music-mixing step.

    (With finishing on -- the default -- the same filters travel into that
    encode instead of paying for this one; see
    test_grade_rides_the_finishing_pass.py.)
    """
    monkeypatch.setenv("MUSEFORGE_FINISHING", "0")
    from pipelines.idea2video import Idea2VideoPipeline

    calls = []

    async def _fake_concat(scene_paths, output_path):
        calls.append(("concat", output_path))
        with open(output_path, "wb") as f:
            f.write(b"concatenated")
        return output_path

    async def _fake_grade(video_path, output_path, director_style="cinematic_balanced", **_kw):
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

    async def _fake_grade(video_path, output_path, director_style="cinematic_balanced", **_kw):
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


async def _route_assembly(tmp_path, monkeypatch, transitions):
    """Run _assemble_final_drama with a transition plan; report which concat ran."""
    monkeypatch.setenv("MUSEFORGE_SCENE_TRANSITIONS", "1")
    from pipelines.idea2video import Idea2VideoPipeline

    calls = {"crossfade": 0, "plain": 0}

    async def _fake_plain(scene_paths, output_path, *_a, **_k):
        calls["plain"] += 1
        with open(output_path, "wb") as f:
            f.write(b"concatenated-plain")
        return output_path

    async def _fake_crossfade_concat(scene_paths, output_path, *_a, **_k):
        calls["crossfade"] += 1
        with open(output_path, "wb") as f:
            f.write(b"concatenated-with-transitions")
        return output_path

    async def _fake_grade(video_path, output_path, director_style="cinematic_balanced", **_kw):
        with open(output_path, "wb") as f:
            f.write(b"graded")
        return output_path

    async def _fake_music(video_path, output_path, music_url=None):
        with open(output_path, "wb") as f:
            f.write(b"with-music")
        return output_path

    monkeypatch.setattr("pipelines.idea2video.concatenate_videos", _fake_plain)
    monkeypatch.setattr(
        "pipelines.idea2video.concatenate_videos_with_transitions", _fake_crossfade_concat
    )
    monkeypatch.setattr("pipelines.idea2video.apply_color_grade", _fake_grade)
    monkeypatch.setattr("pipelines.idea2video.add_background_music", _fake_music)

    pipeline = Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(
        ["scene0.mp4", "scene1.mp4"],
        str(tmp_path / "job"),
        plan="free",
        transitions=transitions,
    )
    return calls


@pytest.mark.asyncio
async def test_planned_dissolve_routes_through_crossfade_concat(tmp_path, monkeypatch):
    calls = await _route_assembly(tmp_path, monkeypatch, transitions=[0.6])
    assert calls == {"crossfade": 1, "plain": 0}


@pytest.mark.asyncio
async def test_all_cut_plan_skips_the_expensive_compositing_path(tmp_path, monkeypatch):
    """The flag is the master switch, but a drama whose every boundary is a
    straight cut has nothing to composite — paying moviepy's memory cost to
    produce a byte-identical result is pure waste."""
    calls = await _route_assembly(tmp_path, monkeypatch, transitions=[0.0])
    assert calls == {"crossfade": 0, "plain": 1}


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

    def _broken_composite(*_a, **_k):
        raise RuntimeError("synthetic compose failure")

    import moviepy

    # Per-boundary overlaps are laid out on an explicit timeline, so the
    # compositing step is CompositeVideoClip -- concatenate_videoclips (the
    # old single-padding call) is no longer on this path at all.
    monkeypatch.setattr(moviepy, "CompositeVideoClip", _broken_composite)

    result = await script2video.concatenate_videos_with_transitions(paths, output)

    assert result == output
    assert os.path.isfile(output)
    # Fallback used the plain concat path (real ffmpeg concat demuxer).
    assert abs(_duration_seconds(output) - 0.8) < 0.3


# --- grade strength ----------------------------------------------------


def test_grade_strength_uses_preset_value_by_default():
    """Each preset tunes its own strength to how aggressive its chain is."""
    from pipelines.script2video import _grade_strength

    assert _grade_strength(0.8) == pytest.approx(0.8)
    assert _grade_strength(1.0) == pytest.approx(1.0)


def test_grade_strength_env_overrides_and_clamps(monkeypatch):
    from pipelines.script2video import _grade_strength

    monkeypatch.setenv("MUSEFORGE_GRADE_STRENGTH", "0.8")
    assert _grade_strength(0.2) == pytest.approx(0.8)

    monkeypatch.setenv("MUSEFORGE_GRADE_STRENGTH", "5")
    assert _grade_strength(0.2) == 1.0
    monkeypatch.setenv("MUSEFORGE_GRADE_STRENGTH", "-2")
    assert _grade_strength(0.2) == 0.0

    # Fail open to the preset rather than breaking rendering on a typo.
    monkeypatch.setenv("MUSEFORGE_GRADE_STRENGTH", "not-a-number")
    assert _grade_strength(0.35) == pytest.approx(0.35)


def test_full_strength_grade_skips_the_blend_chain():
    """At full strength there is nothing to blend, so the chain stays simple."""
    from interfaces.color_grade import ColorGrade
    from pipelines.script2video import build_grade_filter_chain

    grade = ColorGrade(label="T", filter_chain="eq=contrast=1.1", strength=1.0)
    assert build_grade_filter_chain(grade) == "eq=contrast=1.1"


def test_partial_strength_blends_ungraded_over_graded():
    """The blend opacity applies to the UNGRADED top layer, so it must be
    (1 - strength). An inverted opacity made strength=0.0 emit a FULLY
    graded image -- the exact face-crushing look being dialed back."""
    from interfaces.color_grade import ColorGrade
    from pipelines.script2video import build_grade_filter_chain

    grade = ColorGrade(label="T", filter_chain="eq=contrast=1.1", strength=0.25)
    chain = build_grade_filter_chain(grade)
    assert "all_opacity=0.750" in chain, chain
    assert "[grade_a]eq=contrast=1.1[graded]" in chain


@pytest.mark.asyncio
async def test_grade_strength_zero_leaves_picture_ungraded(tmp_path, monkeypatch):
    """End-to-end guard on the opacity direction, through real ffmpeg."""
    from moviepy import ColorClip, VideoFileClip

    from pipelines.script2video import apply_color_grade

    src = str(tmp_path / "flat.mp4")
    skin = (200, 150, 120)  # RGB
    clip = ColorClip(size=(160, 90), color=skin, duration=0.6)
    clip.write_videofile(src, fps=10, codec="libx264", audio=False, logger=None)
    clip.close()

    def _rgb(path):
        with VideoFileClip(path) as graded:
            frame = graded.get_frame(0.2)
            return [float(frame[:, :, c].mean()) for c in range(3)]

    monkeypatch.setenv("MUSEFORGE_GRADE_STRENGTH", "0.0")
    out = str(tmp_path / "ungraded.mp4")
    # noir_mystery is the most aggressive preset -- at strength 0 even it
    # must leave the picture essentially untouched.
    await apply_color_grade(src, out, director_style="noir_mystery")

    for channel, (got, want) in enumerate(zip(_rgb(out), skin)):
        assert abs(got - want) < 12, (
            f"strength=0.0 must be ~ungraded; channel {channel} got {got}, want ~{want}"
        )


@pytest.mark.asyncio
async def test_director_style_selects_a_distinct_grade(tmp_path):
    """The reported issue: every drama got one hardcoded look regardless of
    director style. Noir must finish monochrome and Anime must finish more
    saturated than the source -- through real ffmpeg, not just config."""
    from moviepy import ColorClip, VideoFileClip

    from pipelines.script2video import apply_color_grade

    src = str(tmp_path / "src.mp4")
    clip = ColorClip(size=(160, 90), color=(200, 150, 120), duration=0.6)
    clip.write_videofile(src, fps=10, codec="libx264", audio=False, logger=None)
    clip.close()

    def _rgb(path):
        with VideoFileClip(path) as graded:
            frame = graded.get_frame(0.2)
            return [float(frame[:, :, c].mean()) for c in range(3)]

    def _spread(rgb):
        return max(rgb) - min(rgb)

    source_spread = _spread(_rgb(src))

    noir = str(tmp_path / "noir.mp4")
    await apply_color_grade(src, noir, director_style="noir_mystery")
    assert _spread(_rgb(noir)) < 15, (
        f"noir_mystery must be near-monochrome, got {_rgb(noir)}"
    )

    anime = str(tmp_path / "anime.mp4")
    await apply_color_grade(src, anime, director_style="anime_expressive")
    assert _spread(_rgb(anime)) > source_spread + 10, (
        f"anime_expressive must be more saturated than source, got {_rgb(anime)}"
    )


def test_every_director_style_resolves_to_a_real_grade():
    """No style may silently fall through to the neutral default."""
    from interfaces.camera import DIRECTOR_STYLES
    from interfaces.color_grade import COLOR_GRADES

    for name, style in DIRECTOR_STYLES.items():
        assert style.color_grade in COLOR_GRADES, (
            f"director style {name!r} names grade {style.color_grade!r}, "
            "which has no ColorGrade preset"
        )


def test_unknown_grade_falls_back_instead_of_raising():
    from interfaces.color_grade import COLOR_GRADES, FALLBACK_GRADE, get_color_grade

    assert get_color_grade("no-such-grade") is COLOR_GRADES[FALLBACK_GRADE]
    assert get_color_grade("") is COLOR_GRADES[FALLBACK_GRADE]


@pytest.mark.asyncio
async def test_unknown_director_style_still_grades(tmp_path):
    """A bad style name must degrade to a sane picture, not fail the render."""
    from moviepy import ColorClip

    from pipelines.script2video import apply_color_grade

    src = str(tmp_path / "src.mp4")
    clip = ColorClip(size=(160, 90), color=(200, 150, 120), duration=0.6)
    clip.write_videofile(src, fps=10, codec="libx264", audio=False, logger=None)
    clip.close()

    out = str(tmp_path / "out.mp4")
    assert await apply_color_grade(src, out, director_style="bogus") == out
    assert os.path.getsize(out) > 0


@pytest.mark.asyncio
async def test_assembly_passes_director_style_to_the_grade(tmp_path, monkeypatch):
    """Regression: the grade call site never forwarded the director style, so
    the parameter existed but nothing could ever reach it."""
    import pipelines.idea2video as idea2video_mod

    seen = {}

    async def _fake_grade(video_path, output_path, director_style="cinematic_balanced", **_kw):
        seen["director_style"] = director_style
        with open(output_path, "wb") as f:
            f.write(b"graded")
        return output_path

    async def _fake_concat(paths, out_path):
        with open(out_path, "wb") as f:
            f.write(b"concat")
        return out_path

    async def _fake_music(video_path, output_path, music_url=None, **_kw):
        with open(output_path, "wb") as f:
            f.write(b"music")
        return output_path

    monkeypatch.setattr(idea2video_mod, "apply_color_grade", _fake_grade)
    monkeypatch.setattr(idea2video_mod, "concatenate_videos", _fake_concat)
    monkeypatch.setattr(idea2video_mod, "add_background_music", _fake_music)

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="k", demo=True)
    scene = str(tmp_path / "scene.mp4")
    with open(scene, "wb") as f:
        f.write(b"scene")

    await pipeline._assemble_final_drama(
        [scene], str(tmp_path / "job"), None, None, "pro",
        director_style="noir_mystery",
    )

    assert seen["director_style"] == "noir_mystery"
