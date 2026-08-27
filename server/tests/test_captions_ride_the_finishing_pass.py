"""Captions and the finishing pass are one encode, not two.

Measured on the delivered 60-second master: the caption burn took 237 seconds
and the finishing pass 325, back to back, over the same frames. Nine and a half
minutes of a thirty-three minute job spent writing the same picture twice --
and a generation loss for it, because each pass re-encodes what the last one
wrote.

They fold together cleanly: the caption burn is a video filter, the finishing
pass is a video filter chain plus an audio one, and ffmpeg will take them in a
single graph. What has to survive the folding is the FAIL-OPEN behaviour of
both. Separately, a caption failure costs captions and a finishing failure
costs the fades; merged naively, either failure costs both. So a finishing
pass that cannot carry the captions hands its own input back, and the caller
runs the two passes exactly as it always did.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as mod  # noqa: E402


TRACKS = [{"scene_index": 0, "line": "Söz.", "audio_url": "https://cdn/s0.mp3"}]


@pytest.fixture
def assembly(monkeypatch, tmp_path):
    """The assembly chain with every encode stubbed, recording what ran."""
    calls = []

    async def _concat(scene_paths, output_path):
        calls.append("concat")
        open(output_path, "wb").write(b"concat")
        return output_path

    async def _grade(video_path, output_path, **_kw):
        calls.append("grade")
        open(output_path, "wb").write(b"graded")
        return output_path

    async def _music(video_path, output_path, music_url=None, **_kw):
        calls.append("music")
        open(output_path, "wb").write(b"music")
        return output_path

    async def _burn(video_path, output_path, tracks, scene_paths=None):
        calls.append("burn")
        open(output_path, "wb").write(b"burned")
        return output_path

    def _caption_filter(video_path, tracks=None, scene_paths=None, size=None):
        if not tracks:
            return "", None
        path = os.path.join(str(tmp_path), "captions.srt")
        open(path, "w").write("1\n")
        return f"subtitles={path}", path

    monkeypatch.setenv("MUSEFORGE_FINISHING", "1")
    monkeypatch.setattr(mod, "concatenate_videos", _concat)
    monkeypatch.setattr(mod, "apply_color_grade", _grade)
    monkeypatch.setattr(mod, "add_background_music", _music)
    monkeypatch.setattr(mod, "burn_subtitles", _burn)
    monkeypatch.setattr(mod, "build_caption_filter", _caption_filter)
    return calls, tmp_path


def _finish(calls, *, carries_captions=True):
    async def _fake(
        video_path, output_path, caption_filter="", grade_filter="", delivered_size=None
    ):
        calls.append(f"finish({'captions' if caption_filter else 'plain'})")
        if caption_filter and not carries_captions:
            # What the real pass does when it cannot run with them: hand back
            # the input so the caller knows the merge did not happen.
            return video_path
        open(output_path, "wb").write(b"finished")
        return output_path

    return _fake


@pytest.mark.asyncio
async def test_captions_and_finishing_are_one_pass(assembly, monkeypatch):
    calls, tmp_path = assembly
    monkeypatch.setattr(mod, "finalize_master", _finish(calls))

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=False)
    final = await pipeline._assemble_final_drama(
        ["s0.mp4"], str(tmp_path / "job"), plan="pro", dialogue_tracks=list(TRACKS)
    )

    assert calls == ["concat", "music", "finish(captions)"], (
        "the master was re-encoded twice for two filters"
    )
    assert final.endswith("drama_finished.mp4")


@pytest.mark.asyncio
async def test_a_finishing_pass_that_cannot_carry_them_falls_back_to_two(
    assembly, monkeypatch
):
    """The whole reason the merge is safe. Both stages fail open on their own;
    merged, a single failure must not cost the captions AND the fades."""
    calls, tmp_path = assembly
    monkeypatch.setattr(mod, "finalize_master", _finish(calls, carries_captions=False))

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=False)
    final = await pipeline._assemble_final_drama(
        ["s0.mp4"], str(tmp_path / "job"), plan="pro", dialogue_tracks=list(TRACKS)
    )

    assert calls == [
        "concat",
        "music",
        "finish(captions)",
        # The grade was riding on that encode too, so the fallback runs it in
        # the pass it would otherwise have had, before the captions.
        "grade",
        "burn",
        "finish(plain)",
    ]
    assert final.endswith("drama_finished.mp4")


@pytest.mark.asyncio
async def test_with_finishing_off_the_captions_burn_on_their_own(
    assembly, monkeypatch
):
    calls, tmp_path = assembly
    monkeypatch.setenv("MUSEFORGE_FINISHING", "0")
    monkeypatch.setattr(mod, "finalize_master", _finish(calls))

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=False)
    final = await pipeline._assemble_final_drama(
        ["s0.mp4"], str(tmp_path / "job"), plan="pro", dialogue_tracks=list(TRACKS)
    )

    assert calls == ["concat", "grade", "music", "burn"]
    assert final.endswith("drama_subtitled.mp4")


@pytest.mark.asyncio
async def test_a_silent_drama_still_just_finishes(assembly, monkeypatch):
    calls, tmp_path = assembly
    monkeypatch.setattr(mod, "finalize_master", _finish(calls))

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(
        ["s0.mp4"], str(tmp_path / "job"), plan="pro"
    )

    assert calls == ["concat", "music", "finish(plain)"]


@pytest.mark.asyncio
async def test_the_caption_file_is_cleaned_up(assembly, monkeypatch):
    calls, tmp_path = assembly
    monkeypatch.setattr(mod, "finalize_master", _finish(calls))

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(
        ["s0.mp4"], str(tmp_path / "job"), plan="pro", dialogue_tracks=list(TRACKS)
    )

    assert not os.path.exists(os.path.join(str(tmp_path), "captions.srt"))


# ── the filter graph itself ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_captions_sit_after_the_look_and_before_the_fades(
    monkeypatch, tmp_path
):
    """Order is not cosmetic. After the matte, or a scope crop takes the line
    off the bottom of the frame; after the grain, so the text stays crisp;
    before the fades, or a caption sits at full brightness over a picture
    fading to black."""
    recorded = {}

    class _Clip:
        size = (1920, 1080)
        duration = 60.0
        audio = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod, "build_film_look_filters", lambda w, h: (["fps=24", "noise=alls=4"], [])
    )

    async def _fake_exec(*cmd, **kwargs):
        recorded["vf"] = cmd[cmd.index("-vf") + 1]

        class _Proc:
            returncode = 0

            async def communicate(self):
                open(cmd[-1], "wb").write(b"finished")
                return b"", b""

        return _Proc()

    import moviepy

    monkeypatch.setattr(moviepy, "VideoFileClip", lambda path: _Clip(), raising=False)
    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", _fake_exec)

    src = tmp_path / "master.mp4"
    src.write_bytes(b"master")
    await mod.finalize_master(
        str(src), str(tmp_path / "out.mp4"), caption_filter="subtitles=x.srt"
    )

    chain = recorded["vf"].split(",")
    assert chain.index("noise=alls=4") < chain.index("subtitles=x.srt")
    assert chain.index("subtitles=x.srt") < next(
        i for i, f in enumerate(chain) if f.startswith("fade=t=in")
    )


@pytest.mark.asyncio
async def test_a_finishing_pass_with_no_captions_is_byte_identical(
    monkeypatch, tmp_path
):
    """The path every silent drama takes must not have moved."""
    recorded = {}

    class _Clip:
        size = (1920, 1080)
        duration = 60.0
        audio = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod, "build_film_look_filters", lambda w, h: ([], []))

    async def _fake_exec(*cmd, **kwargs):
        recorded["vf"] = cmd[cmd.index("-vf") + 1]

        class _Proc:
            returncode = 0

            async def communicate(self):
                open(cmd[-1], "wb").write(b"finished")
                return b"", b""

        return _Proc()

    import moviepy

    monkeypatch.setattr(moviepy, "VideoFileClip", lambda path: _Clip(), raising=False)
    monkeypatch.setattr(mod.asyncio, "create_subprocess_exec", _fake_exec)

    src = tmp_path / "master.mp4"
    src.write_bytes(b"master")
    await mod.finalize_master(str(src), str(tmp_path / "out.mp4"))

    assert "subtitles" not in recorded["vf"] and "ass=" not in recorded["vf"]
    assert recorded["vf"].startswith("fade=t=in")


@pytest.mark.asyncio
async def test_a_master_too_short_to_fade_declines_rather_than_swallowing_them(
    monkeypatch, tmp_path
):
    """finalize_master leaves a very short clip alone. With captions folded in
    that has to be reported, not copied through -- the caller is holding the
    only other way they reach the picture."""

    class _Clip:
        size = (1920, 1080)
        duration = 1.0
        audio = None

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import moviepy

    monkeypatch.setattr(moviepy, "VideoFileClip", lambda path: _Clip(), raising=False)

    src = tmp_path / "master.mp4"
    src.write_bytes(b"master")
    out = tmp_path / "out.mp4"

    assert await mod.finalize_master(str(src), str(out), caption_filter="subtitles=x") == str(src)
    # ...and without captions it behaves exactly as it always has.
    assert await mod.finalize_master(str(src), str(out)) == str(out)
