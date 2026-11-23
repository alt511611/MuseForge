"""The storyboard artist is the one who knows a shot is empty, and had no way to say so.

Its prompt forbids negations ("the room empty of people") and demands an
emotion on a face in every shot, so a shot of flames came back with
expression_desc "no human presence", and the acting pass then filled the peak
("the mouth tightening") unconditionally. The shot now carries ``shows_people``.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    build_frame_prompt,
    characters_in_frame,
    resolve_frame_references,
    shot_is_unpeopled,
)

YUSUF = CharacterInScene(idx=0, name="Yusuf", static_features="a grizzled sailor", wardrobe="an oilskin")
PORTRAITS = {"Yusuf": "https://x/yusuf.jpg"}
PLATE = "https://x/plate.png"


def _shot(visual, shows=None, expression="", **kw):
    return StoryboardShot(
        idx=0, visual_desc=visual, motion_desc="slow push in", expression_desc=expression,
        shows_people=shows, **kw,
    )


def test_the_prompt_lets_the_artist_declare_an_empty_shot():
    import inspect

    source = inspect.getsource(sys.modules[StoryboardArtist.__module__])
    assert '"shows_people": false' in source
    assert '"shows_people": true' in source
    assert "SHOW THE CHANGE ON THE FACE, NOT FROM ACROSS THE STREET. In a shot that shows" in source
    assert "KEEP FACES READABLE. In a shot that shows people" in source


def test_the_field_is_optional_so_older_scripts_still_load():
    assert StoryboardShot(idx=0, visual_desc="x", motion_desc="y").shows_people is None


def test_an_empty_shot_is_never_given_an_acted_peak():
    shots = [_shot("flames lean in the wind", shows=False, expression="grief")]
    StoryboardArtist._ensure_expression(shots, "grief")
    StoryboardArtist._apply_acting_beats(shots, "grief")
    assert shots[0].expression_desc == ""
    assert shots[0].expression_peak_desc == ""


def test_a_shot_with_people_is_acted_as_before():
    shots = [_shot("Yusuf grips the rail", shows=True), _shot("Yusuf grips the rail")]
    StoryboardArtist._apply_acting_beats(shots, "grief")
    for shot in shots:
        assert shot.expression_desc and shot.expression_peak_desc


def test_an_empty_shot_is_not_given_a_fallback_expression():
    shots = [_shot("flames", shows=False)]
    StoryboardArtist._ensure_expression(shots, "grief")
    assert shots[0].expression_desc == ""


def test_the_declaration_beats_the_text_in_both_directions():
    boat = _shot("Yusuf's boat lies abandoned on the shingle", shows=False)
    assert shot_is_unpeopled(boat, [YUSUF], matched_char=YUSUF)
    assert characters_in_frame(boat, [YUSUF], YUSUF) == []
    quiet = _shot("The shore at dawn", shows=True)
    assert not shot_is_unpeopled(quiet, [YUSUF])


def test_a_shot_declared_empty_is_drawn_from_the_plate_not_a_portrait():
    boat = _shot("Yusuf's boat lies abandoned on the shingle", shows=False)
    result = resolve_frame_references(
        boat, [YUSUF], PORTRAITS, scene_subject=YUSUF, location_plate_url=PLATE,
    )
    assert result[0] is None
    assert "https://x/yusuf.jpg" not in str(result)


def test_the_frame_for_a_declared_empty_shot_asks_for_no_face():
    shot = _shot("Yusuf's boat on the shingle", shows=False, expression="grief")
    prompt = build_frame_prompt("Cinematic", shot, characters=[YUSUF], matched_char=YUSUF)
    assert "Yusuf(" not in prompt and "Appearance is FIXED" not in prompt
    assert "Facial expression" not in prompt
    assert "Nobody is in this shot" in prompt
