"""Kinetic captions: the word lights up as it is spoken.

Vertical drama is watched muted, so the captions are not an accessibility
layer -- they are the dialogue. This covers the ASS document that carries the
effect, and the one rule the whole thing rests on: every highlight is TIMED
from the voice provider's own measurement, never estimated. A karaoke caption
whose emphasis lands on the wrong word reads as a broken player.
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces import ass_captions  # noqa: E402
from pipelines.idea2video import build_kinetic_ass  # noqa: E402


def _words(*pairs):
    return [
        {"text": text, "start": start, "end": end} for text, start, end in pairs
    ]


def _track(**extra):
    base = {
        "scene_index": 0,
        "character": "Ayse",
        "line": "Cocuk senin degil",
        "start_seconds": 0.0,
        "end_seconds": 1.8,
        "duration_seconds": 1.8,
        "words": _words(
            ("Cocuk", 0.0, 0.5), ("senin", 0.5, 1.1), ("degil", 1.1, 1.8)
        ),
    }
    base.update(extra)
    return base


# --- the document ------------------------------------------------------


def test_playres_is_the_real_frame_so_sizes_are_pixels():
    """The SRT path has to work around libass's 384x288 default canvas; this
    one simply declares the truth."""
    header = ass_captions.build_header(1080, 1920)
    assert "PlayResX: 1080" in header
    assert "PlayResY: 1920" in header


def test_type_is_sized_from_the_shorter_side_in_both_orientations():
    vertical = ass_captions.build_header(1080, 1920)
    horizontal = ass_captions.build_header(1920, 1080)

    def _size(header):
        style = [l for l in header.splitlines() if l.startswith("Style: ")][0]
        return int(style.split(",")[1 + 1])  # Name, Fontname, Fontsize

    # Same physical reading size whichever way the phone is held -- the SRT
    # path learned this the hard way (one line became six on vertical).
    assert _size(vertical) == _size(horizontal)


def test_the_unspoken_part_of_a_cue_is_dimmed_not_recoloured():
    """\\k fills from SecondaryColour to PrimaryColour. A different hue per
    word would turn a caption into a rainbow."""
    header = ass_captions.build_header(1080, 1920)
    style = [l for l in header.splitlines() if l.startswith("Style: ")][0]
    fields = style.split(",")
    primary, secondary = fields[3], fields[4]
    assert primary == ass_captions.WHITE
    assert secondary == ass_captions.DIM


def test_every_word_carries_its_own_karaoke_duration():
    cues = ass_captions.chunk_into_cues(
        _words(("Bir", 0.0, 0.4), ("iki", 0.4, 0.9), ("uc", 0.9, 1.5))
    )
    document = ass_captions.build_ass(cues, 1080, 1920)
    # 40, 50 and 60 centiseconds respectively.
    assert "\\k40}Bir" in document
    assert "\\k50}iki" in document
    assert "\\k60}uc" in document


def test_a_pause_between_words_is_not_swallowed():
    """Without carrying the gap, the highlight runs ahead of the voice for the
    rest of the cue."""
    cues = ass_captions.chunk_into_cues(
        _words(("Ben", 0.0, 0.3), ("...", 1.0, 1.4))
    )
    document = ass_captions.build_ass(cues, 1080, 1920)
    assert "\\k70}" in document  # the 0.7s silence, held before the next word


def test_cues_are_short_bursts_and_break_at_sentences():
    cues = ass_captions.chunk_into_cues(
        _words(
            ("Bitti.", 0.0, 0.5),
            ("Yeni", 0.6, 1.0),
            ("bir", 1.0, 1.3),
            ("gun", 1.3, 1.8),
            ("basliyor", 1.8, 2.4),
        )
    )
    assert [len(c.words) for c in cues] == [1, 3, 1]


def test_the_scenes_turn_decides_what_is_emphasised():
    stems = ass_captions.emphasis_stems("she finally says the child is not his")
    cues = ass_captions.chunk_into_cues(
        _words(("The", 0.0, 0.2), ("child", 0.2, 0.8), ("knows", 0.8, 1.4))
    )
    document = ass_captions.build_ass(cues, 1080, 1920, emphasis=stems)
    assert ass_captions.ACCENT in document
    # ...and the styling is closed again, or the rest of the line inherits it.
    assert f"\\c{ass_captions.WHITE}\\fscx100\\fscy100" in document


def test_turkish_suffixes_do_not_defeat_the_emphasis():
    """"Boşanıyoruz" and "boşanma" are the same news; an exact match would
    emphasise almost nothing in the language this product is mostly used in."""
    stems = ass_captions.emphasis_stems("kadin bosanma karari aldigini soyler")
    cues = ass_captions.chunk_into_cues(_words(("Bosaniyoruz", 0.0, 1.0)))
    assert ass_captions.ACCENT in ass_captions.build_ass(cues, 1080, 1920, stems)


def test_short_words_are_never_emphasised():
    stems = ass_captions.emphasis_stems("bir ve de")
    cues = ass_captions.chunk_into_cues(_words(("bir", 0.0, 0.3)))
    assert ass_captions.ACCENT not in ass_captions.build_ass(cues, 1080, 1920, stems)


def test_braces_in_dialogue_cannot_inject_override_tags():
    cues = ass_captions.chunk_into_cues(
        _words(("{\\fscx900}boom", 0.0, 0.5))
    )
    document = ass_captions.build_ass(cues, 1080, 1920)
    # The tag survives as visible text; what must not survive is the BRACES,
    # which are the only thing that makes libass read it as an override.
    assert "{\\fscx900}" not in document
    assert "(\\\\fscx900)boom" in document


def test_timestamps_never_print_a_sixtieth_second():
    assert ass_captions._timestamp(59.999) == "0:01:00.00"
    assert ass_captions._timestamp(0.0) == "0:00:00.00"


def test_no_cues_means_no_document():
    assert ass_captions.build_ass([], 1080, 1920) == ""


# --- wiring ------------------------------------------------------------


def test_a_provider_without_word_timings_produces_nothing(monkeypatch):
    """Every voice path except the direct ElevenLabs one measures no words,
    and a guessed highlight is worse than none."""
    import pipelines.idea2video as pipeline

    monkeypatch.setattr(pipeline, "_scene_boundaries", lambda paths: [0.0, 6.0])
    plain = _track()
    plain.pop("words")
    assert build_kinetic_ass([plain], scene_paths=["a.mp4"]) == ""


def test_cues_are_offset_onto_the_master_timeline(monkeypatch):
    import pipelines.idea2video as pipeline

    monkeypatch.setattr(pipeline, "_scene_boundaries", lambda paths: [0.0, 6.0, 12.0])
    document = build_kinetic_ass(
        [_track(scene_index=1)], scene_paths=["a.mp4", "b.mp4"], width=1080, height=1920
    )
    # Scene 1 starts at 6s, so its first word cannot be at zero.
    assert "0:00:06.00" in document


def test_the_emphasis_travels_on_the_track(monkeypatch):
    import pipelines.idea2video as pipeline

    monkeypatch.setattr(pipeline, "_scene_boundaries", lambda paths: [0.0, 6.0])
    document = build_kinetic_ass(
        [_track(emphasis="cocuk senin degil diye soyler")], scene_paths=["a.mp4"]
    )
    assert ass_captions.ACCENT in document


# --- libass has to accept it -------------------------------------------


def _has_ffmpeg():
    import shutil

    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not available")
def test_the_document_renders_without_libass_complaining(tmp_path):
    """A document that parses in this test but not in libass is worthless, so
    the real renderer gets a look at it."""
    from pipelines.idea2video import resolve_ffmpeg_binary

    document = ass_captions.build_ass(
        ass_captions.chunk_into_cues(
            _words(("Cocuk", 0.0, 0.5), ("senin", 0.5, 1.1), ("degil", 1.1, 1.8))
        ),
        320,
        180,
        emphasis=ass_captions.emphasis_stems("cocuk senin degil"),
    )
    ass_path = tmp_path / "cues.ass"
    ass_path.write_text(document, encoding="utf-8")
    out = tmp_path / "burned.mp4"

    result = subprocess.run(
        [
            resolve_ffmpeg_binary(), "-y", "-f", "lavfi",
            "-i", "color=c=black:s=320x180:r=24:d=2",
            "-vf", f"ass={ass_path}",
            "-pix_fmt", "yuv420p", str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-800:]
    assert out.exists() and out.stat().st_size > 0
    # libass reports a malformed script on stderr while still exiting 0.
    assert "Error" not in result.stderr or "ass" not in result.stderr.lower()
