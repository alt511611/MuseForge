"""A mouth on screen says its own lines and nobody else's.

The voice generator speaks a whole scene in ONE request and returns ONE
combined file, carried on that scene's first track. The lip-sync pass hands
that file to the provider, and the provider drives the on-screen face from
every word in it -- so a scene where somebody answers over the radio was
delivered with the face saying the radio's half too.

Delivered job 82e03154-12c, brief "A dock worker on a rain-soaked cargo
harbour finds a shipping container that hums with light":

    REYNA     Dispatch, I've got a container lit up on Bay Seven.
              No manifest tag.
    DISPATCH  Copy that. Hold position, we'll pull the records.

Reyna is the only person in the film. Between t=4.9 and t=7.7 her lips form
the dispatcher's words, on screen, over her own subtitle naming him.

The pipeline already KNEW: _heard_but_never_seen marked the dispatcher
invisible, and the portrait step honoured it -- that job generated exactly one
character portrait. The sync step was simply never told.

The fix is a guide track, not a shorter one. The provider bakes the audio it
is handed into the clip it returns, but every tier of concatenate_videos drops
that audio on purpose and the mixer lays the ORIGINAL down at the same anchor
(see _lipsync_scenes) -- so silencing the dispatcher for the sync costs
nothing audible, and keeping the file's LENGTH identical is what leaves the
drift maths, the cutaway split and the length guard reading the clock they
already read.
"""
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines.idea2video import (  # noqa: E402
    _mute_spans,
    _off_screen_speech_spans,
    resolve_ffmpeg_binary,
)


#: The delivered scene, as the voice generator returns it: one combined file
#: on the first track, per-line timings measured against that file.
def _delivered_scene(audio_url="https://cdn/scene_0.mp3"):
    return [
        {
            "scene_index": 0,
            "character": "Reyna Voss",
            "line": "Dispatch, I've got a container lit up on Bay Seven.",
            "start_seconds": 0.0,
            "end_seconds": 4.0,
            "audio_url": audio_url,
        },
        {
            "scene_index": 0,
            "character": "Dispatch",
            "line": "Copy that. Hold position, we'll pull the records.",
            "start_seconds": 4.9,
            "end_seconds": 7.7,
        },
    ]


# ── reading the scene ───────────────────────────────────────────────────────


def test_the_delivered_scene_silences_the_radio_and_nothing_else():
    spans, syncable = _off_screen_speech_spans(_delivered_scene(), {"dispatch"})
    assert syncable is True
    assert spans == [(4.9, 7.7)]  # Reyna's 0.0-4.0 is untouched


def test_a_scene_nobody_answers_in_is_left_exactly_as_it_was():
    """One speaker is the overwhelming majority of scenes, and the path that
    has to stay byte-for-byte unchanged: no spans means no guide file, which
    means the same request this made before any of this existed."""
    spans, syncable = _off_screen_speech_spans(_delivered_scene()[:1], {"dispatch"})
    assert spans == []
    assert syncable is True


def test_a_film_with_nobody_off_screen_never_looks_for_a_span():
    spans, syncable = _off_screen_speech_spans(_delivered_scene(), set())
    assert spans == []
    assert syncable is True


def test_an_untimed_radio_line_fails_open_rather_than_cutting_blind():
    """The MuAPI voice backend estimates line lengths instead of measuring
    them. Silencing on an estimate would take a syllable off the mouth that IS
    on screen -- the exact fault this removes -- so a scene whose off-screen
    line has no measured span syncs the way it did before."""
    tracks = _delivered_scene()
    del tracks[1]["start_seconds"]
    del tracks[1]["end_seconds"]
    spans, syncable = _off_screen_speech_spans(tracks, {"dispatch"})
    assert spans == []
    assert syncable is True


def test_a_scene_that_is_only_a_radio_has_no_mouth_to_drive():
    """Not a silencing job -- a declining one. Every line belongs to somebody
    the film never shows, so the guide would be silent end to end and the call
    would buy a closed mouth at full price."""
    tracks = [_delivered_scene()[1]]
    spans, syncable = _off_screen_speech_spans(tracks, {"dispatch"})
    assert syncable is False
    assert spans == [(4.9, 7.7)]


def test_two_radio_lines_in_a_row_become_one_span():
    """Adjacent and overlapping spans are merged so the filter chain stays one
    volume stage per real stretch of speech, not one per line."""
    tracks = _delivered_scene()
    tracks.append({
        "character": "Dispatch",
        "line": "Records are clean.",
        "start_seconds": 7.6,
        "end_seconds": 9.2,
    })
    spans, _ = _off_screen_speech_spans(tracks, {"dispatch"})
    assert spans == [(4.9, 9.2)]


def test_the_match_is_case_and_space_insensitive():
    tracks = _delivered_scene()
    tracks[1]["character"] = "  DISPATCH "
    spans, _ = _off_screen_speech_spans(tracks, {"dispatch"})
    assert spans == [(4.9, 7.7)]


# ── writing the guide ───────────────────────────────────────────────────────


def _tone(path, seconds=8.1):
    subprocess.run(
        [
            resolve_ffmpeg_binary(), "-y", "-v", "error",
            "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}",
            "-c:a", "libmp3lame", "-q:a", "2", str(path),
        ],
        check=True,
    )
    return str(path)


def _mean_dbfs(path, start, length):
    out = subprocess.run(
        [
            resolve_ffmpeg_binary(), "-hide_banner",
            "-ss", str(start), "-t", str(length), "-i", str(path),
            "-af", "volumedetect", "-f", "null", "-",
        ],
        capture_output=True, text=True,
    ).stderr
    for line in out.splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].strip().split()[0])
    raise AssertionError(f"no mean_volume in ffmpeg output for {path}")


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
async def test_the_guide_keeps_its_length_and_loses_only_the_radio(tmp_path):
    """The two properties the rest of the pass depends on, measured rather
    than asserted: same duration, and energy removed from the dispatcher's
    window only."""
    source = _tone(tmp_path / "scene_0.mp3")
    guide = await _mute_spans(source, str(tmp_path / "guide.mp3"), [(4.9, 7.7)])
    assert guide is not None

    assert abs(_seconds(guide) - _seconds(source)) < 0.05

    assert _mean_dbfs(guide, 0.0, 4.0) == pytest.approx(
        _mean_dbfs(source, 0.0, 4.0), abs=0.5
    )
    assert _mean_dbfs(guide, 4.9, 2.8) < -80.0


@pytest.mark.asyncio
async def test_a_guide_that_cannot_be_written_leaves_the_original(tmp_path):
    missing = await _mute_spans(
        str(tmp_path / "nothing.mp3"), str(tmp_path / "guide.mp3"), [(1.0, 2.0)]
    )
    assert missing is None
    assert await _mute_spans("x.mp3", str(tmp_path / "g.mp3"), []) is None


# ── the sync request ────────────────────────────────────────────────────────


class _FakeLipsync:
    def __init__(self):
        self.requests = []

    def available(self):
        return True

    async def sync(self, video, audio, is_cancelled=None):
        self.requests.append((video, audio))
        return "https://cdn/synced.mp4"


@pytest.fixture
def lipsync_on(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")


async def _run(monkeypatch, tmp_path, tracks, off_screen):
    import pipelines.idea2video as mod
    from pipelines.idea2video import Idea2VideoPipeline

    fake = _FakeLipsync()
    monkeypatch.setattr(mod, "make_lipsync", lambda demo=False: fake)

    async def fake_download(url, path):
        with open(path, "wb") as f:
            f.write(b"synced")
        return path

    async def fake_mute(source, dest, spans):
        with open(dest, "wb") as f:
            f.write(b"guide")
        return dest

    monkeypatch.setattr(mod, "download_video", fake_download)
    monkeypatch.setattr(mod, "_mute_spans", fake_mute)
    monkeypatch.setattr(mod, "_keeps_its_length", lambda a, b: True)

    clip = tmp_path / "scene0.mp4"
    clip.write_bytes(b"original")
    scene_paths = [str(clip)]

    async def progress(*a, **kw):
        return None

    synced = await Idea2VideoPipeline("test-key")._lipsync_scenes(
        scene_paths=scene_paths,
        dialogue_tracks=tracks,
        working_dir=str(tmp_path),
        progress=progress,
        off_screen=off_screen,
    )
    return fake, tracks, synced


@pytest.mark.asyncio
async def test_the_provider_is_handed_the_guide_not_the_scene(
    lipsync_on, monkeypatch, tmp_path
):
    tracks = _delivered_scene()
    fake, tracks, synced = await _run(monkeypatch, tmp_path, tracks, {"dispatch"})

    assert synced == [0]
    _, audio = fake.requests[0]
    assert audio.endswith("scene_0_sync_guide.mp3"), audio


@pytest.mark.asyncio
async def test_the_mixer_still_gets_the_whole_scene_so_the_radio_is_heard(
    lipsync_on, monkeypatch, tmp_path
):
    """The dispatcher is silenced for the MOUTH, never for the audience: the
    track the mixer reads is left carrying the original combined file."""
    tracks = _delivered_scene()
    _, tracks, synced = await _run(monkeypatch, tmp_path, tracks, {"dispatch"})

    assert synced == [0]
    assert tracks[0]["audio_url"] == "https://cdn/scene_0.mp3"


@pytest.mark.asyncio
async def test_a_scene_with_nobody_off_screen_sends_the_file_it_always_sent(
    lipsync_on, monkeypatch, tmp_path
):
    tracks = _delivered_scene()[:1]
    fake, _, synced = await _run(monkeypatch, tmp_path, tracks, {"dispatch"})

    assert synced == [0]
    assert fake.requests[0][1] == "https://cdn/scene_0.mp3"


@pytest.mark.asyncio
async def test_a_scene_that_is_all_radio_is_declined_not_paid_for(
    lipsync_on, monkeypatch, tmp_path
):
    tracks = [dict(_delivered_scene()[1], audio_url="https://cdn/scene_0.mp3")]
    fake, _, synced = await _run(monkeypatch, tmp_path, tracks, {"dispatch"})

    assert synced == []
    assert fake.requests == []
