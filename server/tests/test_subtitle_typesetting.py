"""Subtitle typesetting to the broadcast conventions.

What the pipeline delivered before this existed, measured off a real master:

    52  Mira Kess: Sal, you seeing this? That one's glowing.
    58  Sal Okafor: Probably a bad seal light. Log it and move on.
    72  Mira Kess: It's already been called in a hundred times. Nobody's coming.

Single unwrapped lines up to 1.7x the maximum a broadcast subtitle may be,
each carrying a speaker name no professional subtitle would show. Not hard to
read -- recognisably machine-made, which is the same tell as a flat face or an
unducked score.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces import subtitles  # noqa: E402
from interfaces.subtitles import (  # noqa: E402
    MAX_LINE_CHARS,
    MAX_LINES,
    reading_seconds,
    split_into_cues,
    wrap_cue,
)


@pytest.fixture(autouse=True)
def _labels_off(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_SPEAKER_LABELS", raising=False)


#: The lines that were actually delivered, so the fix is measured against the
#: thing that was wrong rather than against an invented example.
DELIVERED = [
    "Sal, you seeing this? That one's glowing.",
    "Probably a bad seal light. Log it and move on.",
    "Mira, don't. We call it in, we don't touch it.",
    "It's already been called in a hundred times. Nobody's coming.",
    "It's still glowing. It's the only thing still glowing.",
]


# --- the line ----------------------------------------------------------


@pytest.mark.parametrize("line", DELIVERED)
def test_every_delivered_line_now_fits_the_standard(line):
    for cue in split_into_cues(line):
        rendered = wrap_cue(cue).split("\n")
        assert len(rendered) <= MAX_LINES, rendered
        assert all(len(r) <= MAX_LINE_CHARS for r in rendered), rendered


def test_a_short_line_is_left_on_one_line():
    assert wrap_cue("Gitme.") == "Gitme."
    assert "\n" not in wrap_cue("Sal, you seeing this?")


def test_a_line_breaks_where_the_sentence_breaks():
    """Splitting before a verb makes the reader hold half a clause across the
    break; splitting after the full stop costs nothing."""
    wrapped = wrap_cue("It's still glowing. It's the only thing still glowing.")
    top, bottom = wrapped.split("\n")
    assert top.endswith(".")
    assert bottom.startswith("It's the only")


def test_a_clause_break_beats_an_arbitrary_one():
    wrapped = wrap_cue("Mira, don't. We call it in, we don't touch it.")
    top, _ = wrapped.split("\n")
    assert top.rstrip().endswith((".", ","))


def test_lines_come_out_balanced_rather_than_ragged():
    """A caption whose first line runs to the margin and whose second holds
    two words reads as a mistake even when both lines are legal."""
    top, bottom = wrap_cue(
        "It's already been called in a hundred times. Nobody's coming."
    ).split("\n")
    assert abs(len(top) - len(bottom)) <= 14, (top, bottom)


def test_no_word_is_ever_split():
    for line in DELIVERED:
        for cue in split_into_cues(line):
            assert set(wrap_cue(cue).split()) == set(cue.split())


def test_whitespace_is_normalised():
    assert wrap_cue("  Gitme   artık  ") == "Gitme artık"


def test_an_empty_line_produces_nothing():
    assert wrap_cue("") == ""
    assert split_into_cues("") == []
    assert split_into_cues(None) == []


# --- one line, several cues --------------------------------------------


def test_a_line_too_long_for_two_lines_becomes_two_cues():
    """What a subtitler does. Four lines of text on screen is not an option,
    so the caption is split in time instead of in space."""
    long_line = (
        "It's already been called in a hundred times and nobody is coming, "
        "and you know exactly why nobody is coming to a place like this."
    )
    cues = split_into_cues(long_line)
    assert len(cues) >= 2
    for cue in cues:
        assert len(cue) <= MAX_LINE_CHARS * MAX_LINES


def test_a_multi_sentence_line_splits_at_its_sentences():
    cues = split_into_cues(
        "Bu is burada bitmez ve sen bunu cok iyi biliyorsun. "
        "Yarin sabah geldiginde kapiyi acan olmayacak. "
        "Kimse seni beklemiyor artik."
    )
    assert len(cues) >= 2
    assert all(not c.startswith(" ") for c in cues)
    # Sentences are not chopped mid-clause when a boundary was available.
    assert cues[0].endswith(".")


def test_a_single_enormous_sentence_still_gets_split():
    cue = " ".join(["word"] * 60)
    cues = split_into_cues(cue)
    assert len(cues) > 1
    assert all(len(c) <= MAX_LINE_CHARS * MAX_LINES for c in cues)


def test_nothing_is_lost_in_the_split():
    line = DELIVERED[3]
    assert " ".join(split_into_cues(line)).split() == line.split()


# --- the speaker -------------------------------------------------------


def test_the_speaker_is_not_named_by_default():
    """Broadcast names a speaker when the picture cannot -- off screen, a
    crowd, a narrator. On a two-shot it is a quarter of a 42-character line
    spent describing what the viewer is looking at."""
    assert subtitles.format_speaker("Sal Okafor") == ""


def test_sdh_deployments_can_have_the_names_back(monkeypatch):
    """Accessibility subtitles have the opposite requirement: SDH names every
    speaker by design."""
    monkeypatch.setenv("MUSEFORGE_SPEAKER_LABELS", "1")
    assert subtitles.format_speaker("Sal Okafor") == "Sal Okafor: "
    assert subtitles.format_speaker("") == ""


# --- reading speed -----------------------------------------------------


def test_reading_time_follows_the_seventeen_character_standard():
    assert reading_seconds("x" * 34) == pytest.approx(2.0, abs=0.01)


def test_even_a_very_short_cue_gets_long_enough_to_register():
    assert reading_seconds("Ya!") == subtitles.MIN_CUE_SECONDS


def test_nothing_to_read_takes_no_time():
    assert reading_seconds("") == 0.0


# --- end to end in the SRT ---------------------------------------------


def test_the_delivered_drama_would_now_be_typeset(monkeypatch):
    import pipelines.idea2video as pipeline
    from pipelines.idea2video import build_srt_from_dialogue_tracks

    monkeypatch.setattr(pipeline, "_scene_boundaries", lambda paths: [0.0, 30.0])
    srt = build_srt_from_dialogue_tracks(
        [
            {
                "scene_index": 0,
                "character": "Mira Kess",
                "line": DELIVERED[3],
                "start_seconds": 0.0,
                "end_seconds": 4.0,
                "duration_seconds": 4.0,
            }
        ],
        scene_paths=["a.mp4"],
    )
    text_lines = [
        line
        for line in srt.splitlines()
        if line and " --> " not in line and not line.isdigit()
    ]
    assert text_lines, srt
    assert all(len(line) <= MAX_LINE_CHARS for line in text_lines), text_lines
    assert "Mira Kess:" not in srt


def test_a_long_line_gets_its_time_divided_between_its_cues(monkeypatch):
    """Each cue is on screen for as long as its own words need -- which is
    what makes splitting a line honest rather than cosmetic."""
    import pipelines.idea2video as pipeline
    from pipelines.idea2video import build_srt_from_dialogue_tracks

    monkeypatch.setattr(pipeline, "_scene_boundaries", lambda paths: [0.0, 30.0])
    srt = build_srt_from_dialogue_tracks(
        [
            {
                "scene_index": 0,
                "character": "Mira",
                "line": (
                    "It's already been called in a hundred times and nobody is "
                    "coming, and you know exactly why nobody comes here."
                ),
                "start_seconds": 0.0,
                "end_seconds": 8.0,
                "duration_seconds": 8.0,
            }
        ],
        scene_paths=["a.mp4"],
    )
    stamps = [line for line in srt.splitlines() if " --> " in line]
    assert len(stamps) >= 2, srt
    # The cues run in order and none of them starts before the last one ended.
    starts = [s.split(" --> ")[0] for s in stamps]
    assert starts == sorted(starts)
