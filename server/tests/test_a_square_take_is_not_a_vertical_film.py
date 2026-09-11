"""The ordered shape has to survive to delivery, and be noticed when it does not.

Job a66acd59 was ordered 9:16 and its takes came back 960x960. fal's raw
outputs, before assembly, are properly staged over-the-shoulder two-shots: the
man fills the right third of frame, the lamp and window sit where a director
would put them. The delivered film is one woman with a stray hand at the edge
of the picture -- because conforming a square to 9:16 keeps 56% of its width
and centre-crops the rest, and the second character lived in the 44%.

That read, watching the finished video, as a storyboard that never covered
him. It was a crop. Nothing in the logs said so, because by the time anything
is written down the frame is already the ordered shape.

The video endpoint takes no aspect ratio (fal's Kling v3 schema has no such
field): it reads the shape off the start image it is given. So there are two
places the shape can be lost and one line of evidence that separates them --
what the opening frame actually measured.
"""

from pipelines.script2video import (
    GEOMETRY_LOSS_WARNING,
    _ratio_of,
    build_geometry_filters,
)


def test_a_square_clip_ordered_vertical_says_what_it_costs(caplog):
    with caplog.at_level("WARNING"):
        filters = build_geometry_filters(960, 960, "9:16")

    assert filters == [
        "scale=540:960:force_original_aspect_ratio=increase",
        "crop=540:960",
        "setsar=1",
    ], "the delivered film is still 9:16; the loss is the thing to report"
    assert any("56%" in record.getMessage() for record in caplog.records), (
        "a crop this deep is a composition being discarded, not a rounding "
        "correction, and it went unremarked on a delivered job"
    )


def test_a_clip_in_the_ordered_shape_is_silent(caplog):
    """Rounding to even pixels must not cry wolf on every scene of every job."""
    with caplog.at_level("WARNING"):
        build_geometry_filters(1082, 1920, "9:16")

    assert not caplog.records


def test_the_threshold_is_above_rounding_and_below_a_reframe():
    assert 0.8 < GEOMETRY_LOSS_WARNING < 1.0
    # 9:16 asked of a square keeps this much, and it is the case that matters.
    assert (_ratio_of("9:16") / 1.0) < GEOMETRY_LOSS_WARNING


def test_a_ratio_that_cannot_be_read_never_looks_like_a_match():
    """Zero, so no measurement can accidentally satisfy the comparison."""
    assert _ratio_of("") == 0.0
    assert _ratio_of("9:0") == 0.0
    assert _ratio_of("vertical") == 0.0
    assert _ratio_of("9:16") == 0.5625


def test_a_square_still_is_corrected_before_it_becomes_a_take(tmp_path):
    """One picture cropped, so eight seconds of picture need not be.

    The video endpoint reads its canvas off the start image and composes
    inside it. Correcting the still buys a take DIRECTED for the delivered
    shape; leaving it buys a take composed for a square and then cropped,
    which is what removed the second actor from job a66acd59.
    """
    from PIL import Image

    from pipelines.script2video import _conform_image_to_ratio

    source = tmp_path / "frame.png"
    Image.new("RGB", (1024, 1024), "white").save(source)
    output = tmp_path / "frame-9x16.jpg"

    _conform_image_to_ratio(str(source), str(output), "9:16")

    with Image.open(output) as corrected:
        width, height = corrected.size
    assert abs(width / height - 9 / 16) < 0.01
    assert height == 1024, "the binding side keeps its pixels; only the sides go"


def test_an_unreadable_ratio_leaves_the_still_alone(tmp_path):
    """A frame is not worth destroying over a typo in a ratio."""
    from PIL import Image

    from pipelines.script2video import _conform_image_to_ratio

    source = tmp_path / "frame.png"
    Image.new("RGB", (1024, 1024), "white").save(source)
    output = tmp_path / "out.jpg"

    _conform_image_to_ratio(str(source), str(output), "vertical")

    with Image.open(output) as untouched:
        assert untouched.size == (1024, 1024)
