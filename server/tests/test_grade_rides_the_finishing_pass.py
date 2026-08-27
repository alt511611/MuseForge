"""The colour grade and the finishing pass are one encode, not two.

The grade -- and the delivery conform that rides with it -- re-encodes every
frame of the master. A few seconds later the finishing pass re-encodes the same
frames again for the fades, the film look and the loudness, with only the audio
mix in between, and that mix copies the picture through untouched (-c:v copy).
Two full passes over the same picture, and a generation loss for the first one,
for filters ffmpeg would have taken in a single graph.

So the grade travels as a filter fragment (build_delivery_filters) and is
applied in the finishing encode. What has to survive the folding is the
fail-open behaviour of both, exactly as it did when the caption burn was folded
in: a finishing pass that cannot carry the grade hands its own input back, and
the caller grades in the pass it has always had.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as mod  # noqa: E402
from pipelines.script2video import build_delivery_filters  # noqa: E402


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

    monkeypatch.setenv("MUSEFORGE_FINISHING", "1")
    monkeypatch.setattr(mod, "concatenate_videos", _concat)
    monkeypatch.setattr(mod, "apply_color_grade", _grade)
    monkeypatch.setattr(mod, "add_background_music", _music)
    return calls, tmp_path


def _finish(calls, *, carries_the_grade=True):
    async def _fake(
        video_path, output_path, caption_filter="", grade_filter="", delivered_size=None
    ):
        calls.append(f"finish({'grade' if grade_filter else 'plain'})")
        if grade_filter and not carries_the_grade:
            # What the real pass does when it cannot run at all: hand back the
            # input, so the caller knows the merge did not happen.
            return video_path
        open(output_path, "wb").write(b"finished")
        return output_path

    return _fake


# ── the assembly chain ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_grade_and_the_finishing_pass_are_one_encode(assembly, monkeypatch):
    calls, tmp_path = assembly
    monkeypatch.setattr(mod, "finalize_master", _finish(calls))

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=False)
    final = await pipeline._assemble_final_drama(
        ["s0.mp4"], str(tmp_path / "job"), plan="pro"
    )

    assert calls == ["concat", "music", "finish(grade)"], (
        "the master was re-encoded twice for filters one encode can carry"
    )
    assert final.endswith("drama_finished.mp4")


@pytest.mark.asyncio
async def test_the_music_mix_reads_the_ungraded_master(assembly, monkeypatch):
    """The grade has not happened yet when the mix runs, and that is fine: the
    mix copies the picture through and only writes audio."""
    calls, tmp_path = assembly
    seen = {}

    async def _music(video_path, output_path, music_url=None, **_kw):
        calls.append("music")
        seen["input"] = os.path.basename(video_path)
        open(output_path, "wb").write(b"music")
        return output_path

    monkeypatch.setattr(mod, "add_background_music", _music)
    monkeypatch.setattr(mod, "finalize_master", _finish(calls))

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(["s0.mp4"], str(tmp_path / "job"), plan="pro")

    assert seen["input"] == "drama_concatenated.mp4"
    assert not os.path.exists(os.path.join(str(tmp_path / "job"), "drama_graded.mp4"))


@pytest.mark.asyncio
async def test_a_finishing_pass_that_cannot_carry_it_grades_on_its_own(
    assembly, monkeypatch
):
    """The whole reason the merge is safe: a finishing failure must not cost
    the drama its look."""
    calls, tmp_path = assembly
    monkeypatch.setattr(
        mod, "finalize_master", _finish(calls, carries_the_grade=False)
    )

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=False)
    final = await pipeline._assemble_final_drama(
        ["s0.mp4"], str(tmp_path / "job"), plan="pro"
    )

    assert calls == ["concat", "music", "finish(grade)", "grade", "finish(plain)"]
    assert final.endswith("drama_finished.mp4")


@pytest.mark.asyncio
async def test_with_finishing_off_the_grade_keeps_its_own_pass(assembly, monkeypatch):
    calls, tmp_path = assembly
    monkeypatch.setenv("MUSEFORGE_FINISHING", "0")
    monkeypatch.setattr(mod, "finalize_master", _finish(calls))

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(["s0.mp4"], str(tmp_path / "job"), plan="pro")

    assert calls == ["concat", "grade", "music"]


# ── the filters themselves ──────────────────────────────────────────────────


def test_the_delivery_filters_conform_before_they_grade():
    """Scale/crop first: a grade is per-pixel either way, but the conform is
    the thing every later filter's geometry is measured against."""
    filters, size = build_delivery_filters(1904, 1072, "noir_mystery", "16:9")

    assert filters[0].startswith("scale=1920:1080")
    assert size == (1920, 1080)
    # The grade is last, and it is the style's own -- noir finishes monochrome.
    assert "hue=s=0" in filters[-1] or "saturation" in filters[-1]


def test_a_master_already_in_shape_is_only_graded():
    filters, size = build_delivery_filters(1920, 1080, "cinematic_balanced", "16:9")

    assert len(filters) == 1 and not filters[0].startswith("scale=")
    assert size == (1920, 1080)


class _Clip:
    size = (1080, 1920)
    duration = 60.0
    audio = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _record_encode(monkeypatch, recorded):
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


@pytest.mark.asyncio
async def test_the_grade_leads_the_chain(monkeypatch, tmp_path):
    """Order is not cosmetic. The conform travels with the grade, so a matte or
    a caption placed before it would be sized for a frame that no longer
    exists by the time it is drawn."""
    recorded = {}
    monkeypatch.setattr(
        mod, "build_film_look_filters", lambda w, h: (["fps=24", "noise=alls=4"], [])
    )
    _record_encode(monkeypatch, recorded)

    src = tmp_path / "master.mp4"
    src.write_bytes(b"master")
    await mod.finalize_master(
        str(src),
        str(tmp_path / "out.mp4"),
        caption_filter="subtitles=x.srt",
        grade_filter="scale=1920:1080,eq=saturation=0.9",
    )

    chain = recorded["vf"].split(",")
    assert chain[0] == "scale=1920:1080" and chain[1] == "eq=saturation=0.9"
    assert chain.index("eq=saturation=0.9") < chain.index("noise=alls=4")
    assert chain.index("noise=alls=4") < chain.index("subtitles=x.srt")
    assert chain.index("subtitles=x.srt") < next(
        i for i, f in enumerate(chain) if f.startswith("fade=t=in")
    )


@pytest.mark.asyncio
async def test_the_film_look_is_sized_from_the_delivered_frame(monkeypatch, tmp_path):
    """The clip on disk is 1080x1920; the conform in this same encode makes it
    1920x1080. The matte has to be told about the frame it will really see."""
    seen = {}
    recorded = {}

    def _look(width, height):
        seen["size"] = (width, height)
        return [], []

    monkeypatch.setattr(mod, "build_film_look_filters", _look)
    _record_encode(monkeypatch, recorded)

    src = tmp_path / "master.mp4"
    src.write_bytes(b"master")
    await mod.finalize_master(
        str(src),
        str(tmp_path / "out.mp4"),
        grade_filter="scale=1920:1080",
        delivered_size=(1920, 1080),
    )

    assert seen["size"] == (1920, 1080)


@pytest.mark.asyncio
async def test_a_finishing_pass_with_no_grade_is_unchanged(monkeypatch, tmp_path):
    """The path a master takes when the grade already ran must not have moved."""
    recorded = {}
    monkeypatch.setattr(mod, "build_film_look_filters", lambda w, h: ([], []))
    _record_encode(monkeypatch, recorded)

    src = tmp_path / "master.mp4"
    src.write_bytes(b"master")
    await mod.finalize_master(str(src), str(tmp_path / "out.mp4"))

    assert recorded["vf"].startswith("fade=t=in")
