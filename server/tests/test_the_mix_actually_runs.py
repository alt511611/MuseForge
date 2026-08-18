"""The ffmpeg mix was failing on almost every job, and taking the sound with it.

Production logs, one delivered drama:

    WARNING pipelines.idea2video: ffmpeg mix failed (exit=234), falling back to moviepy
    [fc#0 @ ...] Filter 'asplit' has output 0 (sc) unconnected
    Error binding filtergraph inputs/outputs: Invalid argument

``asplit`` exists to make ducking possible: sidechaincompress CONSUMES its
control input, so the speech steering the compressor cannot also be the speech
that reaches the mix. But the split was emitted whenever there was SPEECH,
while the only thing that consumes [sc] is the MUSIC chain. Music is a paid
Creator/Pro extra and off by default, so every ordinary job with dialogue
built a filtergraph with a dangling output and ffmpeg refused the whole thing.

What that cost was not the mix -- there is a moviepy fallback -- but what the
fallback does with the layers. The same job shipped 60% digital silence with
three foley beds generated, paid for, and then not heard, and spent forty
minutes in post-processing decoding the master again at every stage.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from pipelines.idea2video import build_audio_mix_graph  # noqa: E402


def _graph(**kw):
    kw.setdefault("dialogue", [(1, 0.0)])
    kw.setdefault("foley", [])
    kw.setdefault("music_index", None)
    kw.setdefault("duration", 30.0)
    return build_audio_mix_graph(**kw)


# ── the regression ──────────────────────────────────────────────────────────


def test_speech_without_music_leaves_no_dangling_split():
    """The exact shape that failed in production: dialogue on, music off."""
    graph = _graph(dialogue=[(1, 0.0), (2, 16.0)], foley=[(4, 0.0), (5, 16.0)])

    assert "asplit" not in graph
    assert "[sc]" not in graph
    # The speech still reaches the mix; only the unused copy is gone.
    assert "[speech]" in graph


def test_music_still_gets_its_ducking_sidechain():
    """The split is not wrong, it was unconditional. Where something consumes
    [sc], it has to still be there or the score stops getting out of the way
    of the dialogue."""
    graph = _graph(music_index=3)

    assert "asplit=2[speech][sc]" in graph
    assert "sidechaincompress" in graph
    assert "[musicraw][sc]sidechaincompress" in graph


def test_every_declared_label_is_consumed():
    """The general form of the bug: ffmpeg refuses a graph with an output
    nothing reads, so a label produced and never used fails the whole mix."""
    import re

    for kw in (
        {},
        {"music_index": 3},
        {"foley": [(4, 0.0)]},
        {"music_index": 3, "foley": [(4, 0.0)]},
        {"dialogue": [], "foley": [(4, 0.0)]},
        {"dialogue": [], "music_index": 3},
        {"dialogue": [(1, 0.0), (2, 5.0)], "foley": [(4, 0.0)], "music_index": 3},
    ):
        graph = _graph(**kw)
        if graph is None:
            continue
        produced = set(re.findall(r"\[([a-z][a-z0-9]*)\](?=;|$)", graph))
        consumed = set(re.findall(r"\[([a-z][a-z0-9]*)\](?![;]|$)", graph))
        dangling = produced - consumed - {"aout"}
        assert not dangling, f"{kw} produces unread label(s) {dangling}: {graph}"


def test_nothing_to_mix_is_still_nothing_to_mix():
    assert _graph(dialogue=[], foley=[], music_index=None) is None


# ── the graph has to survive real ffmpeg, not just a string check ───────────


def test_the_graph_binds_in_ffmpeg(tmp_path):
    """A filtergraph is only correct if ffmpeg accepts it. The production
    failure was a BINDING error -- every string assertion above would have
    passed on the broken graph too."""
    import shutil
    import subprocess

    ffmpeg = os.environ.get("MUSEFORGE_FFMPEG_BINARY") or shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            import pytest

            pytest.skip("no ffmpeg available")

    graph = _graph(dialogue=[(0, 0.0)], foley=[(1, 0.0)], duration=1.0)
    out = tmp_path / "mixed.wav"
    result = subprocess.run(
        [
            ffmpeg,
            "-f", "lavfi", "-i", "sine=f=300:d=1",
            "-f", "lavfi", "-i", "sine=f=200:d=1",
            "-filter_complex", graph,
            "-map", "[aout]",
            "-y", str(out),
            "-loglevel", "error",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert out.exists() and out.stat().st_size > 0
