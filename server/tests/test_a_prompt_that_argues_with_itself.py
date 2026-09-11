"""One frame prompt, three instructions, and no picture that satisfies them.

Taken verbatim off a delivered close-up. The setting is a "windowless
basement card room, felt table under a bare hanging bulb". The event is "the
basement door bursts open and the single hanging bulb swings wildly ... as
dark-coated men flood into the room". And then, in the same prompt:

    Render the location in that state -- this is the story's event and it
    must be plainly visible in the frame, not implied.
    ...
    Any light named in that setting line describes this place BEFORE the
    change; do not light the frame with it.
    ...
    The cast is closed: Vivian Kesler, Silas Vane appear in this story. Every
    featured, recognisable face in the frame is one of them.
    ...
    Shot type: close-up.

A close-up cannot plainly show a room filling with men, the closed cast
forbids the men outright, and the light the frame is told not to use is the
swinging bulb the shot is ABOUT. Every one of those sentences is right on its
own and each was added to fix a real delivered failure. Together they leave
the model to choose which to break.
"""

from pipelines.script2video import build_frame_prompt, names_the_same_light


class _Shot:
    def __init__(self, shot_type="close-up"):
        self.visual_desc = "Vivian half-risen, one hand flat on the cards"
        self.motion_desc = "she rises"
        self.shot_type = shot_type
        self.lens = "40mm"
        self.expression_desc = "shocked betrayal"


def _cast():
    from interfaces.character import CharacterInScene

    return [
        CharacterInScene(
            idx=0,
            name="Vivian Kesler",
            static_features="woman in her thirties, sharp cheekbones",
            dynamic_features="composed",
            wardrobe="black silk blouse",
        ),
        CharacterInScene(
            idx=1,
            name="Silas Vane",
            static_features="man in his fifties, gaunt face",
            dynamic_features="watchful",
            wardrobe="grey overcoat",
        ),
    ]


def _prompt(shot_type, change, characters=None):
    return build_frame_prompt(
        "Noir",
        _Shot(shot_type),
        setting_location="windowless basement card room, felt table under a "
        "bare hanging bulb",
        setting_time_of_day="night",
        setting_era="1950s",
        world_change=change,
        characters=characters,
    )


_DOOR = (
    "the basement door bursts open and the single hanging bulb swings wildly, "
    "throwing sweeping shadows as dark-coated men flood into the room"
)


def test_a_close_up_is_not_asked_to_show_a_room():
    prompt = _prompt("close-up", _DOOR)

    assert "must be plainly visible in the frame" not in prompt, (
        "a close-up has no room in it to make a room plainly visible"
    )
    assert "as it reaches THIS framing" in prompt
    assert "do not add people the shot does not name" in prompt, (
        "the cast clause already forbids them; the event clause was inviting "
        "them in the same prompt"
    )


def test_a_wide_still_has_to_show_the_event():
    """The demand was added for a delivered climax that was never filmed."""
    prompt = _prompt("wide shot", _DOOR)

    assert "must be plainly visible in the frame, not implied" in prompt


def test_the_light_the_event_is_about_is_not_vetoed():
    prompt = _prompt("close-up", _DOOR)

    assert "do not light the frame with it" not in prompt, (
        "the swinging bulb is the shot; it cannot also be the fixture to "
        "ignore"
    )


def test_a_light_the_event_does_not_touch_is_still_vetoed():
    """The failure the veto exists for: lamps that stayed on through a blackout."""
    prompt = _prompt("wide shot", "the overturned table and scattered chips")

    assert "do not light the frame with it" in prompt


def test_both_halves_have_to_name_the_light():
    assert names_the_same_light("under a bare hanging bulb", "the bulb swings")
    assert not names_the_same_light("under a bare hanging bulb", "the table is overturned")
    assert not names_the_same_light("a bare room", "the bulb swings")
    assert not names_the_same_light("", "the bulb swings")


def test_a_take_that_speaks_is_not_promised_a_sync_pass():
    """"Their lips will be animated to the dialogue" is a promise, and on a
    native-audio take nothing keeps it.

    The sync pass skips a scene that said its own lines, so the sentence is
    simply untrue there -- and the alternative the code falls to without it is
    worse: the no-sync branch asks for the mouth to be "naturally obscured,
    shown in profile, or not be the focal point", which is the one direction
    you would never give a model about to animate that mouth.
    """
    spoken = build_frame_prompt(
        "Noir",
        _Shot("close-up"),
        has_dialogue=True,
        picture_speaks=True,
    )

    assert "spoken aloud" in spoken
    assert "will be animated to the dialogue" not in spoken
    assert "naturally obscured" not in spoken


def test_a_synced_scene_keeps_the_sentence_that_is_true_of_it():
    synced = build_frame_prompt(
        "Noir",
        _Shot("close-up"),
        has_dialogue=True,
        lipsync_enabled=True,
    )

    assert "will be animated to the dialogue" in synced


def test_the_shot_is_the_first_thing_the_model_reads():
    """fit_image_prompt's own docstring names the shape: style, then the shot.

    The ladder did not have it. Taken off a delivered close-up, the first
    thing the model read about what it was drawing was "windowless basement
    card room" and the first thing about WHO was a costume lock; "Close-up on
    Vivian Kesler half-risen from her chair" arrived sixth, about 60% into a
    ~2,400-character prompt, behind four blocks that are word-for-word
    identical in every frame of the film.
    """
    prompt = _prompt("close-up", _DOOR, characters=_cast())

    shot = prompt.index("Vivian half-risen")
    for later, what in (
        ("Setting:", "the room"),
        ("Appearance is FIXED", "the identity lock"),
        ("180-degree rule", "the axis"),
        ("The cast is closed", "the closed cast"),
    ):
        assert shot < prompt.index(later), (
            f"{what} is identical in every frame of the film; this shot is not"
        )
    assert prompt.index("Noir style") < shot, "the style still opens the prompt"
    assert prompt.index("Shot type:") < prompt.index("Appearance is FIXED"), (
        "framing belongs with the shot it frames, not after the locks"
    )


def test_reordering_did_not_change_what_dies_first():
    """Reading order and drop order are separate, and only one of them moved."""
    from pipelines.script2video import fit_image_prompt

    dropped = fit_image_prompt(
        [(0, "A" * 40), (7, "Z" * 40), (2, "M" * 40)], limit=90
    )

    assert "Z" not in dropped, "the worst priority goes first, wherever it reads"
    assert dropped.startswith("A" * 40)
    assert "M" * 40 in dropped
