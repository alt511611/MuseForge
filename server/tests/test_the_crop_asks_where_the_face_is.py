"""A vertical crop is a composition decision, and it was being made blind.

Job a66acd59's takes came back square on a 9:16 order, so every scene was
conformed by discarding 44% of its width -- and what lived in that 44% was the
second character. The film's own frame prompts had PUT him there: every
two-hander carries the locked 180-degree axis (first visible character
frame-left, second frame-right, in singles too). The crop was the only stage
that never asked.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


TWO_HANDER = [
    {"name": "Vera", "is_visible": True},
    {"name": "Emre", "is_visible": True},
]


def _scene(shots, dialogue, index=0):
    return {
        "index": index,
        "clip_index": index,
        "shots": shots,
        "script": {"dialogue": dialogue},
    }


# --- reading the axis the film already locked ----------------------------


def test_the_axis_is_the_one_the_frame_prompts_state():
    """Same rule, same guard as build_screen_direction_clause: if these two
    ever disagree, the crop is cutting to a staging nobody asked for."""
    from interfaces.reframe import FRAME_LEFT, FRAME_RIGHT, sides_from_characters

    sides = sides_from_characters(TWO_HANDER)

    assert sides == {"vera": FRAME_LEFT, "emre": FRAME_RIGHT}


def test_a_single_hander_and_an_ensemble_have_no_axis():
    """A single has no axis to hold and an ensemble needs real blocking --
    exactly the cases the frame prompt refuses to state a rule for."""
    from interfaces.reframe import sides_from_characters

    assert sides_from_characters(TWO_HANDER[:1]) == {}
    assert sides_from_characters(TWO_HANDER + [{"name": "Deniz"}]) == {}
    # An off-screen character (a voice on the radio) is not in the frame and
    # does not take a side.
    assert sides_from_characters(
        TWO_HANDER + [{"name": "Radio", "is_visible": False}]
    ) != {}


def test_the_speaker_decides_which_way_the_crop_leans():
    from interfaces.reframe import anchor_for_speakers, sides_from_characters

    sides = sides_from_characters(TWO_HANDER)

    left = anchor_for_speakers(["Vera"], sides, "medium shot")
    right = anchor_for_speakers(["Emre"], sides, "medium shot")

    assert left.x < 0.5 < right.x
    assert left.confidence > 0 and right.confidence > 0


def test_a_tighter_framing_leans_less():
    """A close-up fills the frame with a face and can only lean; a wide has
    room to place a body a third of the way in."""
    from interfaces.reframe import anchor_for_speakers, sides_from_characters

    sides = sides_from_characters(TWO_HANDER)

    close = anchor_for_speakers(["Emre"], sides, "close-up")
    wide = anchor_for_speakers(["Emre"], sides, "wide shot")

    assert 0.5 < close.x < wide.x


def test_a_two_hander_framing_is_held_whole():
    """A crop cannot favour one player without losing the other, and in a
    micro-drama the listener IS the shot."""
    from interfaces.reframe import anchor_for_speakers, sides_from_characters

    sides = sides_from_characters(TWO_HANDER)

    assert anchor_for_speakers(["Emre"], sides, "over-the-shoulder").confidence == 0
    # Both of them speaking is a two-hander whatever the shot_type says.
    assert anchor_for_speakers(["Emre", "Vera"], sides, "medium shot").confidence == 0


def test_nobody_speaking_and_nobody_known_stays_centred():
    from interfaces.reframe import CENTRE, anchor_for_speakers, sides_from_characters

    sides = sides_from_characters(TWO_HANDER)

    assert anchor_for_speakers([], sides, "close-up") == CENTRE
    assert anchor_for_speakers(["Someone Else"], sides, "close-up") == CENTRE
    # No axis at all: every film with one character, or five.
    assert anchor_for_speakers(["Emre"], {}, "close-up") == CENTRE


# --- a scene, beat by beat -----------------------------------------------


def test_a_scene_is_weighted_by_the_seconds_each_beat_holds():
    """The beats of a take are cuts inside ONE generation whose exact timings
    are the model's, so the crop moves at SCENE boundaries only -- which means
    a scene's anchor is its beats, weighted by screen time."""
    from interfaces.reframe import scene_anchor, sides_from_characters

    sides = sides_from_characters(TWO_HANDER)
    scene = _scene(
        shots=[
            {"index": 0, "seconds": 8.0, "shot_type": "medium shot", "line_count": 1},
            {"index": 1, "seconds": 2.0, "shot_type": "close-up", "line_count": 1},
        ],
        dialogue=[
            {"character": "Emre", "line": "you knew"},
            {"character": "Vera", "line": "i did"},
        ],
    )

    anchor = scene_anchor(scene, sides)

    # Eight seconds of Emre against two of Vera: the scene is Emre's.
    assert anchor.x > 0.5


def test_a_scene_that_cuts_between_two_singles_evenly_stays_centred():
    """No single place to point a fixed crop, and saying so is the honest
    answer rather than picking one of them."""
    from interfaces.reframe import scene_anchor, sides_from_characters

    sides = sides_from_characters(TWO_HANDER)
    scene = _scene(
        shots=[
            {"seconds": 5.0, "shot_type": "medium shot", "line_count": 1},
            {"seconds": 5.0, "shot_type": "medium shot", "line_count": 1},
        ],
        dialogue=[
            {"character": "Vera", "line": "one"},
            {"character": "Emre", "line": "two"},
        ],
    )

    assert abs(scene_anchor(scene, sides).x - 0.5) < 0.001


def test_a_silent_beat_inherits_the_scene_it_is_in():
    """A reaction beat says nothing and is still a shot of somebody. Left at
    the centre it would drag the scene's average back there and undo the
    reading the spoken beats paid for."""
    from interfaces.reframe import CONFIDENCE_CAST, anchors_for_scene, sides_from_characters

    sides = sides_from_characters(TWO_HANDER)
    scene = _scene(
        shots=[
            {"seconds": 4.0, "shot_type": "medium shot", "line_count": 1},
            {"seconds": 4.0, "shot_type": "close-up", "line_count": 0},
        ],
        dialogue=[{"character": "Emre", "line": "you knew"}],
    )

    spans = anchors_for_scene(scene, sides)

    assert spans[1][1].x > 0.5
    # ...but held below a beat with a name in it: it is an inference about
    # this beat rather than a fact about it.
    assert spans[1][1].confidence <= CONFIDENCE_CAST < spans[0][1].confidence


def test_scenes_come_back_in_cut_order_not_script_order():
    """A re-cut reorders the film and rewrites clip indices as it goes."""
    from interfaces.reframe import anchors_in_cut_order

    scenes = [
        _scene(
            [{"seconds": 6.0, "shot_type": "medium shot", "line_count": 1}],
            [{"character": name, "line": "x"}],
            index=i,
        )
        for i, name in enumerate(("Emre", "Vera"))
    ]

    anchors = anchors_in_cut_order(scenes, TWO_HANDER)

    assert len(anchors) == 2
    assert anchors[0].x > 0.5 > anchors[1].x


def test_a_film_with_no_axis_produces_no_anchors_at_all():
    from interfaces.reframe import anchors_in_cut_order

    scenes = [_scene([{"seconds": 6.0, "line_count": 1}], [{"character": "Solo", "line": "x"}])]

    assert anchors_in_cut_order(scenes, [{"name": "Solo"}]) == []


# --- what ffmpeg is actually told -----------------------------------------


def test_the_default_is_the_centre_crop_this_pipeline_always_emitted():
    """Character for character. Everything here is an improvement on the
    centre crop or it is the centre crop."""
    from interfaces.reframe import CENTRE, crop_filter

    assert crop_filter(1920, 1080, 608, 1080, anchor=CENTRE) == "crop=608:1080"
    # Nothing to crop at all.
    assert crop_filter(1080, 1920, 1080, 1920) == "crop=1080:1920"


def test_the_crop_moves_towards_the_speaker():
    from interfaces.reframe import Anchor, crop_filter

    left = crop_filter(1920, 1080, 608, 1080, anchor=Anchor(x=0.33, confidence=0.75))
    right = crop_filter(1920, 1080, 608, 1080, anchor=Anchor(x=0.67, confidence=0.75))

    assert "(in_w-out_w)*" in left and "(in_w-out_w)*" in right
    left_fraction = float(left.split("(in_w-out_w)*")[1].split(":")[0])
    right_fraction = float(right.split("(in_w-out_w)*")[1].split(":")[0])
    assert left_fraction < 0.5 < right_fraction


def test_low_confidence_barely_moves_the_crop():
    """A wrong crop that is fully applied loses the subject; one that is half
    applied does not."""
    from interfaces.reframe import Anchor, crop_filter

    sure = crop_filter(1920, 1080, 608, 1080, anchor=Anchor(x=0.75, confidence=1.0))
    unsure = crop_filter(1920, 1080, 608, 1080, anchor=Anchor(x=0.75, confidence=0.2))

    sure_fraction = float(sure.split("(in_w-out_w)*")[1].split(":")[0])
    unsure_fraction = float(unsure.split("(in_w-out_w)*")[1].split(":")[0])
    assert 0.5 < unsure_fraction < sure_fraction


def test_the_subject_lands_inside_the_window_it_was_cropped_for():
    """The arithmetic, checked in pixels: a subject two thirds across a 1920
    frame has to still be in a 608-wide crop of it, and nearer its middle than
    a centre crop would leave them."""
    from interfaces.reframe import Anchor, crop_fraction

    frame, window = 1920.0, 608.0
    fraction = crop_fraction(0.67, 1.0, frame, window)
    left_edge = fraction * (frame - window)
    subject = 0.67 * frame

    assert left_edge <= subject <= left_edge + window
    assert abs((subject - left_edge) - window / 2) < 1.0


def test_a_scene_by_scene_plan_is_one_crop_whose_offset_jumps_at_the_cuts():
    """One filter, one encode. The offset changes where the picture already
    changes, which is where a change of framing belongs."""
    from interfaces.reframe import Anchor, crop_filter, spans_from_durations

    spans = spans_from_durations(
        [5.0, 6.0],
        {0: Anchor(x=0.7, confidence=0.75), 1: Anchor(x=0.3, confidence=0.75)},
    )
    crop = crop_filter(960, 960, 540, 960, spans=spans)

    assert crop.startswith("crop=540:960:if(lt(t,5.000)")
    assert crop.count("if(") == 1  # two spans, one switch


def test_an_unknown_clip_in_the_plan_keeps_the_centre():
    from interfaces.reframe import Anchor, CENTRE, spans_from_durations

    spans = spans_from_durations([4.0, 4.0], {1: Anchor(x=0.7, confidence=0.75)})

    assert spans[0][2] == CENTRE
    assert spans[1][2].x > 0.5


def test_a_crop_that_takes_the_top_and_bottom_leaves_headroom():
    """Faces do not sit at the vertical centre of a frame: a centre crop of a
    square take into 16:9 slices the top of a head off and leaves the chest."""
    from interfaces.reframe import Anchor, crop_filter, spans_from_durations

    spans = spans_from_durations([6.0], {0: Anchor(x=0.5, confidence=0.0)}, vertical=True)
    crop = crop_filter(960, 960, 960, 540, spans=spans)

    assert "(in_h-out_h)*" in crop
    fraction = float(crop.split("(in_h-out_h)*")[1])
    assert fraction < 0.5, "the window sits above centre, where the faces are"


# --- the record the export reads later ------------------------------------


def test_the_plan_survives_a_round_trip_through_the_job_result():
    from pipelines.idea2video import reframe_spans_from_record

    spans = reframe_spans_from_record(
        [
            {"start": 0.0, "end": 5.0, "x": 0.7, "y": 0.5, "confidence": 0.75, "reason": "emre"},
            {"start": 5.0, "end": 9.0, "x": 0.3, "y": 0.5, "confidence": 0.75, "reason": "vera"},
        ]
    )

    assert [round(s[0], 1) for s in spans] == [0.0, 5.0]
    assert spans[0][2].x == 0.7
    assert spans[1][2].reason == "vera"


def test_a_job_made_before_any_of_this_exports_exactly_as_it_did():
    from pipelines.idea2video import reframe_spans_from_record

    assert reframe_spans_from_record(None) == []
    assert reframe_spans_from_record([]) == []


def test_the_plan_is_machinery_and_never_reaches_the_browser():
    from jobs import public_result

    public = public_result({"video_url": "u", "_reframe": [{"start": 0}]})

    assert "_reframe" not in public
    assert public["video_url"] == "u"
