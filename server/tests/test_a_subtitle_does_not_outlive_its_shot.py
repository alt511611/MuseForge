"""Her line stayed on his face after the picture cut to him.

Delivered drama 10e143bb, final scene -- a 12-second take with a cut 7 seconds
into it, read off the burned-in captions frame by frame:

    18.083s   the take opens on her at his door
    22.542s   "I wrote you a letter once." comes up, over her
    25.500s   the picture cuts to him, listening
    27.333s   her caption finally comes off HIS face

A reader attributes a caption to whoever is under it, so the film reads as him
saying he wrote her a letter, which is the opposite of the scene. Nothing was
wrong with the estimate that produced the cue: the scene is voiced by its own
take, so there is one recording and no per-line measurement in it, and 4.8
seconds is a fair guess at that sentence.

What was wrong is the window it was fitted to. Fitting a scene's cues inside
the SCENE was the same thing as fitting them inside its shot for as long as a
scene was a shot. Since interfaces/scene_take a scene is several framings of
one generation, and the take itself decides which of them says which line
(scene_take._spread_dialogue) -- so the answer was already worked out before
the picture existed, and nothing downstream was spending it.
"""

import pytest

from interfaces.subtitles import fit_cues_to_shots
from pipelines.idea2video import _take_line_windows, build_srt_from_dialogue_tracks

#: The delivered scene: a 12-second take, 7 seconds on her and 5 on him, one
#: line said in each.
SHOTS = [
    {"index": 0, "one_take": True, "seconds": 7, "line_count": 1},
    {"index": 1, "one_take": True, "seconds": 5, "line_count": 1},
]

#: What the clip actually measured. Not 12: the generation came back one frame
#: longer than the seconds it was ordered in.
SPAN = 12.042


def _tracks(audio, windows=True):
    """The scene's two lines, voiced by the take that shows them."""
    placed = _take_line_windows(SHOTS)
    rows = [
        {
            "character": "Elena Vasquez",
            "line": "Elena?",
            "scene_index": 0,
            "audio_url": audio,
            "speaks_for_itself": True,
        },
        {
            "character": "Elena Vasquez",
            "line": "I wrote you a letter once.",
            "scene_index": 0,
        },
    ]
    if windows:
        for row, window in zip(rows, placed):
            row["shot_window"] = window
    return rows


def _spans(srt: str):
    def _seconds(stamp):
        hours, minutes, rest = stamp.split(":")
        whole, millis = rest.split(",")
        return int(hours) * 3600 + int(minutes) * 60 + int(whole) + int(millis) / 1000

    return [
        tuple(_seconds(part.strip()) for part in line.split("-->"))
        for line in srt.splitlines()
        if "-->" in line
    ]


@pytest.fixture
def scene(tmp_path, monkeypatch):
    from pipelines import idea2video as idea_mod

    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"fake")
    audio = tmp_path / "take.m4a"
    audio.write_bytes(b"fake")
    monkeypatch.setattr(idea_mod, "_scene_boundaries", lambda _paths: [0.0, SPAN])
    return str(clip), str(audio)


def test_a_line_is_captioned_inside_the_framing_that_says_it(scene):
    clip, audio = scene

    spans = _spans(build_srt_from_dialogue_tracks(_tracks(audio), scene_paths=[clip]))
    cut = 7 / 12 * SPAN

    assert len(spans) == 2
    # Each cue inside its own framing. The tolerance is the SRT's own
    # resolution: a timestamp is written to the millisecond, so a cue that
    # ends on the cut and the one that begins on it round to neighbouring
    # milliseconds rather than to the same number.
    for (start, end), (opens, closes) in zip(spans, [(0.0, cut), (cut, SPAN)]):
        assert start >= opens - 0.002, "no cue begins before its framing does"
        assert end <= closes + 0.002, "and none outlives it"


def test_without_the_framings_the_cue_runs_onto_the_listener(scene):
    """The same scene, unchanged except that nobody said where it cuts.

    Kept as a test rather than a memory: it is the delivered behaviour, and
    it is what every scene rendered by a backend that cannot cut inside one
    generation still gets, correctly -- there is no cut inside it to cross.
    """
    clip, audio = scene

    spans = _spans(
        build_srt_from_dialogue_tracks(_tracks(audio, windows=False), scene_paths=[clip])
    )
    cut = 7 / 12 * SPAN

    assert any(start < cut < end for start, end in spans)


def test_a_caption_still_lasts_as_long_as_its_shot_is_talking(scene):
    """Shrinking a cue to its framing must not leave the shot uncaptioned.

    A scene voiced by its own take is speaking for its whole length, which is
    why the scene-wide layout stretches estimates to fill it. Placed by shot,
    the same argument holds against the shot: a 1.2-second reading estimate
    under seven seconds of speech comes off screen five seconds before the
    line is finished.
    """
    clip, audio = scene

    spans = _spans(build_srt_from_dialogue_tracks(_tracks(audio), scene_paths=[clip]))

    assert spans[0][1] - spans[0][0] > 5.0
    assert spans[1][1] - spans[1][0] > 4.0


def test_the_framings_are_shares_of_the_scene_not_seconds_of_it():
    """A take is ordered in whole seconds and comes back longer than that.

    8, 10 and 12 seconds of plan arrived as 8.042, 10.042 and 12.042 of
    picture -- one frame each at 24fps, 723 frames against 720. A framing
    written down as "from 7s to 12s" is a frame out by the end of its own
    scene and three by the end of the film; written down as a share of the
    scene it survives, and the caller multiplies it by what the clip measured.
    """
    windows = _take_line_windows(SHOTS)

    assert windows == [(0.0, 7 / 12), (7 / 12, 1.0)]
    assert all(0.0 <= edge <= 1.0 for window in windows for edge in window)


def test_a_scene_with_nothing_to_say_about_its_framings_says_nothing():
    """Three shapes that must produce no windows at all.

    A partial answer is worse than none: some cues placed by shot and the
    rest by scene are two layouts overlapping each other on one screen.
    """
    assert _take_line_windows([]) == []
    assert _take_line_windows([{"one_take": True, "seconds": 12, "line_count": 2}]) == []
    assert _take_line_windows(
        [{"index": 0, "seconds": 7}, {"index": 1, "seconds": 5}]
    ) == [], "the per-shot path's framings are separate clips, never one take"


def test_two_lines_in_one_framing_share_it_in_order():
    placed = fit_cues_to_shots([1.0, 3.0], [(0.0, 8.0), (0.0, 8.0)], gap=0.2, fill=True)

    assert placed[0][0] == 0.0
    assert placed[0][1] <= placed[1][0], "in order, and not on screen together"
    assert placed[1][1] == pytest.approx(8.0), "and between them they cover the shot"
