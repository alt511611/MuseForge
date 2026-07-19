"""Verify add_background_music() always closes the VideoFileClip, even when
loading the music track fails -- found via a free (no-cost) audit that
spotted an unclosed ffmpeg subprocess leak in that failure path, right
after fixing an actual OOM crash (a resource leak like this would
compound under sustained real usage).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


@pytest.mark.asyncio
async def test_video_closed_even_when_music_load_fails(tmp_path, monkeypatch):
    from pipelines import idea2video as mod

    close_calls = {"video": 0}

    class FakeVideo:
        duration = 5.0

        def with_audio(self, audio):
            return self

        def close(self):
            close_calls["video"] += 1

        def write_videofile(self, *a, **kw):
            pass

    def fake_video_file_clip(path):
        return FakeVideo()

    def fake_audio_file_clip(url):
        raise RuntimeError("simulated: invalid/unreachable music URL")

    import moviepy

    monkeypatch.setattr(moviepy, "VideoFileClip", fake_video_file_clip)
    monkeypatch.setattr(moviepy, "AudioFileClip", fake_audio_file_clip)

    src = tmp_path / "in.mp4"
    src.write_bytes(b"fake video bytes")
    out = tmp_path / "out.mp4"

    await mod.add_background_music(str(src), str(out), music_url="https://fake/music.mp3")

    assert close_calls["video"] == 1, (
        "VideoFileClip was opened but never closed when AudioFileClip failed -- "
        "this leaks an ffmpeg subprocess per failed music attempt"
    )
    # Fail-open: output file must still exist (copied through unchanged).
    assert out.is_file()
