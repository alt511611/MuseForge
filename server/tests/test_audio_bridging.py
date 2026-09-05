"""Speech that outlives its shot: the audio bridge.

A micro-drama cuts faster than people talk. The pipeline used to resolve that
by truncating the line at the scene border (``subclipped(0, available)``),
which is audible as a word cut in half and gets worse the faster the picture
is cut -- so the cutting rhythm this product wants was, in effect, capped by
the mixer.

Speech now runs over the join, and the two places that decide WHEN a line
happens -- the mixer and the SRT builder -- are driven from one plan
(``plan_scene_speech_anchors``) so they cannot disagree.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines.idea2video import (  # noqa: E402
    SPEECH_GAP_SECONDS,
    build_srt_from_dialogue_tracks,
    plan_scene_speech_anchors,
)


def _track(scene, line="Bir şey söyle", **extra):
    base = {"scene_index": scene, "character": "Ayse", "line": line}
    base.update(extra)
    return base


# --- the plan ----------------------------------------------------------


def test_speech_starts_at_its_own_scene_when_it_fits():
    """The common case must be untouched: nothing drifts without cause."""
    tracks = [
        _track(0, start_seconds=0.0, end_seconds=2.0),
        _track(1, start_seconds=0.0, end_seconds=2.0),
    ]
    anchors = plan_scene_speech_anchors(tracks, [0.0, 6.0], master_duration=12.0)
    assert anchors == {0: 0.0, 1: 6.0}


def test_speech_longer_than_its_shot_pushes_the_next_scene_later():
    """A 5-second line under a 2-second shot has to finish somewhere."""
    tracks = [
        _track(0, start_seconds=0.0, end_seconds=5.0),
        _track(1, start_seconds=0.0, end_seconds=1.5),
    ]
    anchors = plan_scene_speech_anchors(tracks, [0.0, 2.0], master_duration=12.0)
    assert anchors[0] == 0.0
    # Scene 1's picture starts at 2.0s, but its line waits for scene 0's to end.
    assert anchors[1] == pytest.approx(5.0 + SPEECH_GAP_SECONDS)


def test_speech_never_overlaps_speech():
    """Two characters talking over each other is a choice, not a side effect
    of a shot running short."""
    tracks = [
        _track(0, start_seconds=0.0, end_seconds=4.0),
        _track(1, start_seconds=0.0, end_seconds=4.0),
        _track(2, start_seconds=0.0, end_seconds=4.0),
    ]
    anchors = plan_scene_speech_anchors(
        tracks, [0.0, 1.5, 3.0], master_duration=30.0
    )
    ends = [anchors[i] + 4.0 for i in range(3)]
    assert anchors[1] >= ends[0]
    assert anchors[2] >= ends[1]


def test_nothing_is_anchored_past_the_end_of_the_film():
    """A line placed after the last frame is a line nobody can hear."""
    tracks = [
        _track(0, start_seconds=0.0, end_seconds=20.0),
        _track(1, start_seconds=0.0, end_seconds=3.0),
    ]
    anchors = plan_scene_speech_anchors(tracks, [0.0, 2.0], master_duration=8.0)
    assert anchors[1] < 8.0


def test_scenes_without_dialogue_are_not_in_the_plan():
    anchors = plan_scene_speech_anchors(
        [_track(1, start_seconds=0.0, end_seconds=2.0)], [0.0, 4.0], 10.0
    )
    assert set(anchors) == {1}


def test_unmeasured_lines_are_summed_from_their_durations():
    """The MuAPI voice path returns one file per line and no timestamps."""
    tracks = [
        _track(0, duration_seconds=2.0),
        _track(0, duration_seconds=2.0),
        _track(1, duration_seconds=1.0),
    ]
    anchors = plan_scene_speech_anchors(tracks, [0.0, 3.0], master_duration=20.0)
    # Scene 0 needs ~4.4s (two lines plus the gap between them), so scene 1's
    # line cannot start at its picture (3.0s).
    assert anchors[1] > 3.0


def test_empty_input_plans_nothing():
    assert plan_scene_speech_anchors([], [0.0, 5.0], 10.0) == {}
    assert plan_scene_speech_anchors(None, [], 0.0) == {}


# --- captions follow the same plan -------------------------------------


def _timestamp_seconds(stamp: str) -> float:
    hours, minutes, rest = stamp.split(":")
    seconds, millis = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def _cue_starts(srt: str):
    return [
        _timestamp_seconds(line.split(" --> ")[0])
        for line in srt.splitlines()
        if " --> " in line
    ]


def test_captions_move_with_the_speech_they_belong_to(monkeypatch):
    """If the sound waits, the subtitle waits. Otherwise the words on screen
    are a different take from the words in the air."""
    import pipelines.idea2video as pipeline

    # A 2-second opening shot carrying a 5-second line, then a longer scene.
    monkeypatch.setattr(
        pipeline, "_scene_boundaries", lambda paths: [0.0, 2.0, 12.0]
    )
    srt = build_srt_from_dialogue_tracks(
        [
            _track(0, line="Uzun bir replik", start_seconds=0.0, end_seconds=5.0),
            _track(1, line="Cevap", start_seconds=0.0, end_seconds=1.0),
        ],
        scene_paths=["a.mp4", "b.mp4"],
    )
    starts = _cue_starts(srt)
    assert starts[0] == pytest.approx(0.0)
    # Not 2.0 (its picture), but after the first line has finished.
    assert starts[1] == pytest.approx(5.0 + SPEECH_GAP_SECONDS, abs=0.01)


def test_captions_are_unchanged_when_every_line_fits_its_scene(monkeypatch):
    import pipelines.idea2video as pipeline

    monkeypatch.setattr(
        pipeline, "_scene_boundaries", lambda paths: [0.0, 6.0, 12.0]
    )
    srt = build_srt_from_dialogue_tracks(
        [
            _track(0, line="Kisa", start_seconds=0.5, end_seconds=2.0),
            _track(1, line="Yanit", start_seconds=0.5, end_seconds=2.0),
        ],
        scene_paths=["a.mp4", "b.mp4"],
    )
    starts = _cue_starts(srt)
    assert starts[0] == pytest.approx(0.5)
    assert starts[1] == pytest.approx(6.5)


# --- the mixer itself --------------------------------------------------


def _has_ffmpeg():
    import shutil

    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.asyncio
@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
async def test_a_line_longer_than_its_shot_is_mixed_whole(tmp_path):
    """The regression this file exists for, exercised against real files.

    Scene 0 is two seconds; its line is three and a half. Before the audio
    bridge the mixed clip was cut to the scene border, so the last 1.5s of the
    sentence simply did not exist in the master.
    """
    import numpy as np
    from moviepy import AudioArrayClip, ColorClip

    from pipelines.idea2video import add_background_music

    def _scene(name, duration):
        path = str(tmp_path / name)
        clip = ColorClip(size=(160, 90), color=(20, 20, 20), duration=duration)
        clip.write_videofile(path, fps=12, codec="libx264", audio=False, logger=None)
        clip.close()
        return path

    scenes = [_scene("s0.mp4", 2.0), _scene("s1.mp4", 6.0)]
    master = _scene("master.mp4", 8.0)

    # A 3.5-second tone: longer than the two-second shot it belongs to.
    rate = 22050
    samples = np.sin(
        2 * np.pi * 440 * np.arange(int(rate * 3.5)) / rate
    ).reshape(-1, 1)
    line_path = str(tmp_path / "line.mp3")
    tone = AudioArrayClip(np.hstack([samples, samples]), fps=rate)
    tone.write_audiofile(line_path, logger=None)
    tone.close()

    out = str(tmp_path / "mixed.mp4")
    await add_background_music(
        master,
        out,
        music_url=None,
        dialogue_tracks=[
            {
                "scene_index": 0,
                "character": "Ayse",
                "line": "Uzun bir replik",
                "audio_url": line_path,
                "start_seconds": 0.0,
                "end_seconds": 3.5,
                "duration_seconds": 3.5,
            }
        ],
        scene_paths=scenes,
    )

    from moviepy import VideoFileClip

    with VideoFileClip(out) as mixed:
        assert mixed.audio is not None
        # The master keeps its own length whatever the speech does...
        assert mixed.duration == pytest.approx(8.0, abs=0.3)
        # ...and there is still sound after the scene border at 2.0s, which is
        # exactly where the old code cut the sentence off.
        after_the_cut = mixed.audio.subclipped(2.4, 3.3).to_soundarray(fps=8000)
    assert float(abs(after_the_cut).max()) > 0.01


def test_a_silent_scenes_captions_do_not_delay_a_later_scenes_voice():
    """A scene whose voice failed carries subtitles and no sound. Waiting for
    it would hold real audio back for lines nobody can hear."""
    tracks = [
        _track(0, line="Sessiz replik", caption_only=True, duration_seconds=6.0),
        _track(1, start_seconds=0.0, end_seconds=2.0),
    ]
    anchors = plan_scene_speech_anchors(tracks, [0.0, 2.0], master_duration=12.0)
    assert 0 not in anchors
    assert anchors[1] == 2.0
