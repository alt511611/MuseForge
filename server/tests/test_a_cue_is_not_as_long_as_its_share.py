"""A caption's share of a scene says WHEN its line is spoken, not how long to
leave it up.

Job 49512158 -- "A dock worker on a rain-soaked cargo harbour finds a shipping
container that hums with light, and the city's power dies the moment she opens
it" -- came back as one 30.2s take carrying its own audio and three lines of
dialogue. Nothing measured the individual lines, so _lay_out_scene_captions
divided the scene between them in proportion and stretched each one across its
share. Read off the burned-in captions, a frame a second:

    0.5-7.5s   "That one wasn't lit an hour ago."                    32 chars
    8-18.5s    "Whatever you are, I hope you're worth the paperwork." 52 chars
    18.5-30s   "No, no - stay on, stay on-"                           26 chars

The shortest line held the screen the longest: 11.5 seconds, seven times the
1.5 seconds it takes to read at the 17 characters a second that
interfaces/subtitles is built on. The film's last eleven seconds -- two shots,
an opened container and the blackout the whole idea is named for -- play under
one caption the viewer finished reading in the first two of them.

The division was not the mistake. Proportional shares are what keep a caption
from arriving before its line is spoken, which is the failure
test_one_recording_is_not_one_line.py exists to hold down. The mistake was
reading a WINDOW as a DURATION. A cue now sits at the front of its share and
comes off when its own words are done -- so these tests assert both halves:
the sentence goes away, and it goes away without moving.
"""

from pipelines.idea2video import (
    CAPTION_FILL_MAX_STRETCH,
    CAPTION_GAP_SECONDS,
    _estimate_line_duration_seconds,
    _lay_out_scene_captions,
    build_srt_from_dialogue_tracks,
)

#: The delivered take, to the second.
TAKE_SECONDS = 30.2

#: Its three lines, in order, exactly as they were burned in.
LINES = [
    "That one wasn't lit an hour ago.",
    "Whatever you are, I hope you're worth the paperwork.",
    "No, no - stay on, stay on-",
]


def _self_voiced_tracks(audio: str):
    """The scene as the pipeline saw it: one recording, hung on the first line."""
    tracks = [
        {
            "character": "Mira Kess",
            "line": LINES[0],
            "scene_index": 0,
            "audio_url": audio,
            "speaks_for_itself": True,
        }
    ]
    tracks += [
        {"character": "Mira Kess", "line": line, "scene_index": 0}
        for line in LINES[1:]
    ]
    return tracks


def _cues(srt: str):
    """(start, end) of every cue in an SRT, in seconds."""

    def _seconds(stamp):
        hours, minutes, rest = stamp.split(":")
        whole, millis = rest.split(",")
        return int(hours) * 3600 + int(minutes) * 60 + int(whole) + int(millis) / 1000

    return [
        tuple(_seconds(part.strip()) for part in line.split("-->"))
        for line in srt.splitlines()
        if "-->" in line
    ]


def _stretched(durations, span):
    """The layout this file was written against: each cue spread over its share.

    Carried here rather than imported because it no longer exists in the
    pipeline, and because the invariant the second test checks is a statement
    ABOUT it -- the shares did not move, only what happens inside them.
    """
    gaps = CAPTION_GAP_SECONDS * max(0, len(durations) - 1)
    scale = span / (sum(durations) + gaps)
    placed, cursor = [], 0.0
    for duration in durations:
        end = cursor + duration * scale
        placed.append((cursor, end))
        cursor = end + CAPTION_GAP_SECONDS * scale
    return placed


def test_a_line_does_not_hold_the_screen_for_a_third_of_the_film(
    tmp_path, monkeypatch
):
    from pipelines import idea2video as idea_mod

    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"fake")
    audio = tmp_path / "take.m4a"
    audio.write_bytes(b"fake")
    monkeypatch.setattr(
        idea_mod, "_scene_boundaries", lambda _paths: [0.0, TAKE_SECONDS]
    )

    srt = build_srt_from_dialogue_tracks(
        _self_voiced_tracks(str(audio)), scene_paths=[str(clip)]
    )
    cues = _cues(srt)
    assert len(cues) == len(LINES)
    spans = [end - start for start, end in cues]

    # The delivered film: 11.5 seconds on twenty-six characters.
    assert max(spans) < TAKE_SECONDS / 4, (
        "no line of a three-line scene may hold the screen for a quarter of it"
    )
    # The closing line is the shortest thing said in the drama, and it was the
    # longest caption in it.
    assert spans[2] < spans[1], (
        '"%s" is shorter than "%s" and cannot be the longer cue' % (LINES[2], LINES[1])
    )
    # And no caption outstays its own words by more than the declared ceiling.
    for span, line in zip(spans, LINES):
        limit = _estimate_line_duration_seconds(line) * CAPTION_FILL_MAX_STRETCH
        assert span <= limit + 0.001, (
            '"%s" needs about %.1fs to say and was on screen for %.1fs'
            % (line, _estimate_line_duration_seconds(line), span)
        )


def test_the_shortened_cue_still_starts_on_the_frame_it_started_on():
    """Shortening a caption must not move the one thing the share decided.

    A cue's START is the claim that its line is being spoken about now. Pull
    that earlier and the caption runs ahead of the voice again -- the whole
    reason the proportional fill is there.
    """
    durations = [_estimate_line_duration_seconds(line) for line in LINES]
    placed = _lay_out_scene_captions(durations, TAKE_SECONDS, fill=True)

    starts = [round(start, 6) for start, _ in placed]
    shares = [round(start, 6) for start, _ in _stretched(durations, TAKE_SECONDS)]
    assert starts == shares, "the shares moved; only their tails were meant to"

    # Every cue is strictly shorter than the share it sits in, and none of
    # them runs past it into the next line's window.
    for (start, end), (share_start, share_end) in zip(
        placed, _stretched(durations, TAKE_SECONDS)
    ):
        assert start <= end <= share_end
        assert end - start < share_end - share_start


def test_a_scene_that_measured_its_lines_is_left_alone():
    """The ceiling is on the STRETCH, and an unstretched scene has none.

    Without ``fill`` a set of lines is only ever scaled DOWN, to fit a shot
    too short to hold it -- so a cue is already no longer than its own words,
    and a ceiling that touched it here would be shortening a measurement.
    """
    durations = [3.0, 1.5, 4.0]

    roomy = _lay_out_scene_captions(durations, 30.0)
    assert [round(end - start, 6) for start, end in roomy] == durations

    cramped = _lay_out_scene_captions(durations, 5.0)
    assert sum(end - start for start, end in cramped) < sum(durations), (
        "a scene too short for its lines still squeezes them"
    )
