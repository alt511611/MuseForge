"""Burn-in captions from dialogue_tracks (.srt + ffmpeg subtitles filter)."""

import os
from unittest.mock import AsyncMock

import pytest


def test_build_srt_from_dialogue_tracks_timestamps_and_text():
    from pipelines.idea2video import build_srt_from_dialogue_tracks

    tracks = [
        {
            "character": "Ava",
            "line": "We leave at dawn.",
            "start_seconds": 1.5,
            "end_seconds": 3.25,
        },
        {
            "character": "Ben",
            "line": "I'll be ready.",
            "start_seconds": 4.0,
            "duration_seconds": 2.0,
        },
    ]
    srt = build_srt_from_dialogue_tracks(tracks)

    assert "1\n" in srt
    assert "00:00:01,500 --> 00:00:03,250" in srt
    assert "Ava: We leave at dawn." in srt
    assert "2\n" in srt
    assert "00:00:04,000 --> 00:00:06,000" in srt
    assert "Ben: I'll be ready." in srt


def test_build_srt_skips_empty_lines():
    from pipelines.idea2video import build_srt_from_dialogue_tracks

    srt = build_srt_from_dialogue_tracks(
        [
            {"character": "A", "line": "  ", "start_seconds": 0, "end_seconds": 1},
            {
                "character": "B",
                "line": "Hello",
                "start_seconds": 1,
                "end_seconds": 2,
            },
        ]
    )
    assert "A:" not in srt
    assert "1\n00:00:01,000 --> 00:00:02,000\nB: Hello\n" in srt


def _cue_times(srt):
    """(start, end) of every cue, in seconds."""

    def _seconds(stamp):
        hours, minutes, rest = stamp.split(":")
        secs, millis = rest.split(",")
        return int(hours) * 3600 + int(minutes) * 60 + int(secs) + int(millis) / 1000

    times = []
    for row in srt.splitlines():
        if "-->" in row:
            start, end = (part.strip() for part in row.split("-->"))
            times.append((_seconds(start), _seconds(end)))
    return times


def test_a_caption_row_is_not_probed_for_audio_it_never_had():
    """Opening "" as an audio clip left a moviepy reader to die mid-init, and
    its traceback -- one per line, per scene -- was the loudest thing in the
    log of a drama whose voice provider had failed."""
    from pipelines.idea2video import _probe_audio_duration_seconds

    assert _probe_audio_duration_seconds("") is None
    assert _probe_audio_duration_seconds("   ") is None


def test_captions_never_overrun_into_the_next_scene(monkeypatch):
    """The delivered failure: the estimated duration of a scene's last line
    ran past the cut, so two cues were on screen at once -- once with the same
    speaker named on both rows, which reads as a broken renderer."""
    from pipelines import idea2video

    # Two 4-second shots holding lines that "want" far longer than that.
    monkeypatch.setattr(
        idea2video, "_scene_boundaries", lambda paths: [0.0, 4.0, 8.0]
    )
    tracks = [
        {"character": "Mira", "line": "Tomas — the lights—", "scene_index": 0},
        {
            "character": "Tomas",
            "line": "Voss, walk away from it. Now, before it opens.",
            "scene_index": 0,
        },
        {"character": "Tomas", "line": "Get away from it! Voss, get away!", "scene_index": 1},
    ]

    times = _cue_times(
        idea2video.build_srt_from_dialogue_tracks(tracks, scene_paths=["a", "b"])
    )

    assert len(times) == 3
    for (_, end), (next_start, _) in zip(times, times[1:]):
        assert end <= next_start
    assert times[1][1] <= 4.0  # scene 0's last word is gone before the cut
    assert times[2][0] >= 4.0
    # Squeezed, not truncated: every line still gets a share of its shot.
    assert times[0][1] > times[0][0]


def test_captions_keep_their_estimated_length_when_the_scene_fits(monkeypatch):
    """Scaling is for lines that do not fit. A shot with room to spare must
    time its captions exactly as before."""
    from pipelines import idea2video

    monkeypatch.setattr(idea2video, "_scene_boundaries", lambda paths: [0.0, 60.0])

    times = _cue_times(
        idea2video.build_srt_from_dialogue_tracks(
            [
                {"character": "Mara", "line": "It's warm.", "scene_index": 0},
                {"character": "Mara", "line": "Something is alive.", "scene_index": 0},
            ],
            scene_paths=["a"],
        )
    )

    assert times[0] == (0.0, 1.2)  # the estimator's floor, untouched
    assert times[1][0] == pytest.approx(1.4)  # + the 0.2s breath


def test_an_unprobeable_scene_is_not_squeezed_to_nothing(monkeypatch):
    """A clip that would not open reports a 0-length span. Unknown is not the
    same as "no room" -- treating it as room would collapse every caption in
    that scene onto one frame."""
    from pipelines import idea2video

    monkeypatch.setattr(idea2video, "_scene_boundaries", lambda paths: [0.0, 0.0])

    times = _cue_times(
        idea2video.build_srt_from_dialogue_tracks(
            [
                {"character": "Mara", "line": "It's warm.", "scene_index": 0},
                {"character": "Mara", "line": "Something is alive.", "scene_index": 0},
            ],
            scene_paths=["a"],
        )
    )

    assert times[0][1] == 1.2
    assert times[1][0] > times[0][1]


@pytest.mark.asyncio
async def test_burn_subtitles_fails_open_when_ffmpeg_fails(tmp_path, monkeypatch):
    from pipelines import idea2video

    src = tmp_path / "in.mp4"
    out = tmp_path / "out.mp4"
    payload = b"ORIGINAL-VIDEO-BYTES"
    src.write_bytes(payload)

    class _FakeProc:
        returncode = 1

        async def communicate(self):
            return b"", b"Error: subtitles filter not found"

    async def _fake_exec(*args, **kwargs):
        # Simulate a partial/corrupt write that must be replaced.
        out.write_bytes(b"CORRUPT")
        return _FakeProc()

    monkeypatch.setattr(idea2video.asyncio, "create_subprocess_exec", _fake_exec)

    result = await idea2video.burn_subtitles(
        str(src),
        str(out),
        [
            {
                "character": "Ava",
                "line": "Hello there",
                "start_seconds": 0.0,
                "end_seconds": 1.5,
            }
        ],
    )

    assert result == str(out)
    assert out.read_bytes() == payload


@pytest.mark.asyncio
async def test_burn_subtitles_noop_when_tracks_empty(tmp_path):
    from pipelines.idea2video import burn_subtitles

    src = tmp_path / "in.mp4"
    out = tmp_path / "out.mp4"
    src.write_bytes(b"ORIGINAL")
    result = await burn_subtitles(str(src), str(out), [])
    assert result == str(out)
    assert out.read_bytes() == b"ORIGINAL"


@pytest.mark.asyncio
async def test_assemble_burns_subtitles_before_watermark(tmp_path, monkeypatch):
    """Order: concat -> grade -> music -> subtitles -> watermark (when tracks).

    Finishing (fades/loudness) is disabled here so this test stays focused on
    the subtitle/watermark ordering it names; the finishing step has its own
    ordering test in test_finishing_master.py.
    """
    monkeypatch.setenv("MUSEFORGE_FINISHING", "0")
    from pipelines.idea2video import Idea2VideoPipeline

    calls = []

    async def _fake_concat(scene_paths, output_path):
        calls.append("concat")
        with open(output_path, "wb") as f:
            f.write(b"concat")
        return output_path

    async def _fake_grade(video_path, output_path, director_style="cinematic_balanced", **_kw):
        calls.append("grade")
        with open(output_path, "wb") as f:
            f.write(b"graded")
        return output_path

    async def _fake_music(video_path, output_path, music_url=None, **kwargs):
        calls.append("music")
        with open(output_path, "wb") as f:
            f.write(b"music")
        return output_path

    async def _fake_subs(video_path, output_path, dialogue_tracks, scene_paths=None):
        calls.append("subtitles")
        assert os.path.basename(video_path) == "drama_with_music.mp4"
        with open(output_path, "wb") as f:
            f.write(b"subs")
        return output_path

    async def _fake_wm(video_path, output_path):
        calls.append("watermark")
        assert os.path.basename(video_path) == "drama_subtitled.mp4"
        with open(output_path, "wb") as f:
            f.write(b"final")
        return output_path

    monkeypatch.setattr("pipelines.idea2video.concatenate_videos", _fake_concat)
    monkeypatch.setattr("pipelines.idea2video.apply_color_grade", _fake_grade)
    monkeypatch.setattr("pipelines.idea2video.add_background_music", _fake_music)
    monkeypatch.setattr("pipelines.idea2video.burn_subtitles", _fake_subs)
    monkeypatch.setattr("pipelines.idea2video.add_watermark", _fake_wm)

    pipeline = Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(
        ["scene0.mp4"],
        str(tmp_path / "job"),
        plan="free",
        dialogue_tracks=[
            {
                "character": "A",
                "line": "Hi",
                "start_seconds": 0,
                "end_seconds": 1,
            }
        ],
    )
    assert calls == ["concat", "grade", "music", "subtitles", "watermark"]


@pytest.mark.asyncio
async def test_assemble_skips_subtitles_without_dialogue(tmp_path, monkeypatch):
    from pipelines.idea2video import Idea2VideoPipeline

    burn = AsyncMock(side_effect=AssertionError("burn_subtitles must not run"))

    async def _fake_concat(scene_paths, output_path):
        with open(output_path, "wb") as f:
            f.write(b"c")
        return output_path

    async def _fake_grade(video_path, output_path, director_style="cinematic_balanced", **_kw):
        with open(output_path, "wb") as f:
            f.write(b"g")
        return output_path

    async def _fake_music(video_path, output_path, music_url=None, **kwargs):
        with open(output_path, "wb") as f:
            f.write(b"m")
        return output_path

    async def _fake_wm(video_path, output_path):
        with open(output_path, "wb") as f:
            f.write(b"w")
        return output_path

    monkeypatch.setattr("pipelines.idea2video.concatenate_videos", _fake_concat)
    monkeypatch.setattr("pipelines.idea2video.apply_color_grade", _fake_grade)
    monkeypatch.setattr("pipelines.idea2video.add_background_music", _fake_music)
    monkeypatch.setattr("pipelines.idea2video.burn_subtitles", burn)
    monkeypatch.setattr("pipelines.idea2video.add_watermark", _fake_wm)

    pipeline = Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(
        ["scene0.mp4"], str(tmp_path / "job"), plan="free"
    )
    burn.assert_not_awaited()
