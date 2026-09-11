"""A scene's whole soundtrack is not the length of its first sentence.

Job a66acd59 was voiced by the take itself: one audio file per scene, hung on
the scene's FIRST line the way a scene voiced in one recording always has
been. The subtitle builder measured that file and gave the whole scene's
length to one sentence.

What it delivered, read off the burned-in captions frame by frame:

    0-5s   "Your bet, mister."                                 (6s, 3 words)
    6s     "Call."                                             (1s)
    7s     "Nice tell you've got there."                       (1s)
    8-15s  "You're quick for a man who's never played before." (8s)
    16-17s "I've had a good teacher."                          (2s)
    18-27s "I taught you that tell. Fifteen years back."       (10s)

Every scene the same shape: the opening line parked for the length of the
scene, the rest flashing past at the end of it. A viewer reading the film --
which is how vertical drama is watched -- gets the first sentence for six
seconds and the reply for one.
"""

from pipelines.idea2video import build_srt_from_dialogue_tracks


def _scene_take_tracks(audio: str):
    """One scene, three lines, the take's own audio on the first of them."""
    return [
        {
            "character": "Vivian Marsh",
            "line": "Your bet, mister.",
            "scene_index": 0,
            "audio_url": audio,
            "speaks_for_itself": True,
        },
        {"character": "The Man", "line": "Call.", "scene_index": 0},
        {
            "character": "Vivian Marsh",
            "line": "Nice tell you've got there.",
            "scene_index": 0,
        },
    ]


def _cue_spans(srt: str):
    spans = []
    for line in srt.splitlines():
        if "-->" not in line:
            continue
        start, end = (part.strip() for part in line.split("-->"))

        def _seconds(stamp):
            hours, minutes, rest = stamp.split(":")
            whole, millis = rest.split(",")
            return int(hours) * 3600 + int(minutes) * 60 + int(whole) + int(millis) / 1000

        spans.append(_seconds(end) - _seconds(start))
    return spans


def test_three_words_do_not_hold_the_screen_for_the_whole_scene(tmp_path, monkeypatch):
    from pipelines import idea2video as idea_mod

    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"fake")
    audio = tmp_path / "take.m4a"
    audio.write_bytes(b"fake")

    # The scene runs ten seconds and its audio is the whole of it.
    monkeypatch.setattr(idea_mod, "_scene_boundaries", lambda _paths: [0.0, 10.0])
    # The take's file is the whole scene; the other two lines have none.
    monkeypatch.setattr(
        idea_mod,
        "_probe_audio_duration_seconds",
        lambda path: 10.0 if path else None,
    )

    srt = build_srt_from_dialogue_tracks(
        _scene_take_tracks(str(audio)), scene_paths=[str(clip)]
    )
    spans = _cue_spans(srt)

    assert len(spans) == 3
    assert spans[0] < spans[2], (
        '"Your bet, mister." is three words and "Nice tell you\'ve got there." '
        "is five; the shorter line cannot be the longer cue"
    )
    assert max(spans) < 6.0, (
        "no single line in a three-line scene may hold the screen for most of it"
    )
    assert min(spans) > 1.0, "and none may flash past in under a second"
    # And the set covers the scene: the take is speaking for its whole
    # length, so captions that finish halfway through it have run ahead of
    # the voice saying them.
    assert sum(spans) > 8.0
