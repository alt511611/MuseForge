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
    """Order: concat -> grade -> music -> subtitles -> watermark (when tracks)."""
    from pipelines.idea2video import Idea2VideoPipeline

    calls = []

    async def _fake_concat(scene_paths, output_path):
        calls.append("concat")
        with open(output_path, "wb") as f:
            f.write(b"concat")
        return output_path

    async def _fake_grade(video_path, output_path, style="cinematic"):
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

    async def _fake_grade(video_path, output_path, style="cinematic"):
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
