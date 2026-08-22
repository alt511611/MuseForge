"""Two ways a drama stops looking like a film.

Both seen in one delivered harbour drama:

  * the same worker wore a beanie, then an orange hard hat, then a black one
    — the costume lock forbade CHANGING the outfit, and said nothing about
    ADDING a hat that was never part of it;
  * the cast repeatedly stopped and stared down the lens, because the only
    instruction about the face was that it must not be turned away from
    camera, and every identity reference is a frontal portrait looking
    straight into it.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _char(name, wardrobe=""):
    return SimpleNamespace(
        name=name,
        static_features="thirties, weathered face",
        wardrobe=wardrobe,
        is_visible=True,
    )


def _shot():
    return SimpleNamespace(
        visual_desc="Mara hauls the door open",
        shot_type="medium shot",
        lens="50mm",
        expression_desc="jaw set, eyes fixed on the latch",
    )


# --- costume ------------------------------------------------------------


def test_unnamed_headwear_is_forbidden_even_with_a_named_outfit():
    """The failure was additive, so the lock has to be additive too."""
    from pipelines.script2video import build_character_identity_clause

    clause = build_character_identity_clause(
        [_char("Mara", "orange hi-vis jacket, black work trousers")]
    )

    assert "Costume is LOCKED" in clause
    assert "hard hat" in clause and "beanie" in clause
    assert "unless the outfit names one" in clause


def test_the_no_additions_rule_also_covers_an_undescribed_outfit():
    from pipelines.script2video import build_character_identity_clause

    clause = build_character_identity_clause([_char("Mara")])

    assert "EXACT outfit from the reference image" in clause
    assert "hard hat" in clause


def test_a_named_hat_is_kept_rather_than_banned():
    """The rule bans UNNAMED headwear; a scripted hard hat must survive it."""
    from pipelines.script2video import build_character_identity_clause

    clause = build_character_identity_clause(
        [_char("Mara", "orange hi-vis jacket and a yellow hard hat")]
    )

    assert "yellow hard hat" in clause
    assert "in every scene, never removed" in clause


def test_the_shot_designer_is_told_what_the_cast_has_on():
    """The costume lock is stated to the IMAGE model. The shot designer was
    given faces and builds alone -- and it writes visual_desc, the sentence
    the image model weights above every clause the lock lives in. Delivered:
    a yellow rain jacket in the first scene, the same jacket over a grey
    hoodie in the second, and over a harness with headphones in the third,
    against a lock that named none of it. It dressed them itself, and the
    frame prompt then asked for a headset next to a sentence forbidding one.
    """
    from agents.storyboard_artist import StoryboardArtist

    artist = StoryboardArtist(demo=True)
    prompt = artist._build_prompt(
        script="Mara hauls the door open.",
        characters=[_char("Mara", "orange hi-vis jacket, black work trousers")],
        user_requirement="",
        guidance="handheld",
        default_lens="50mm",
    )

    assert "orange hi-vis jacket, black work trousers" in prompt


def test_a_character_with_no_wardrobe_reads_exactly_as_before():
    """A legacy or library character carries no outfit; the line must not grow
    an empty "wearing" clause for them."""
    from agents.storyboard_artist import StoryboardArtist

    artist = StoryboardArtist(demo=True)
    prompt = artist._build_prompt(
        script="Mara hauls the door open.",
        characters=[_char("Mara")],
        user_requirement="",
        guidance="handheld",
        default_lens="50mm",
    )

    assert "Characters: Mara: thirties, weathered face\n" in prompt


def test_the_designer_is_told_the_costume_is_not_theirs_to_design():
    from agents.storyboard_artist import StoryboardArtist

    assert "THE COSTUME IS CAST, NOT DESIGNED" in StoryboardArtist.SYSTEM_PROMPT
    assert "headset" in StoryboardArtist.SYSTEM_PROMPT
    assert "a prop in their hands, not a new piece of costume" in (
        StoryboardArtist.SYSTEM_PROMPT
    )


def test_screenwriter_is_asked_to_settle_the_head():
    from agents.screenwriter import ScreenwriterAgent

    assert "HEAD DOWN" in ScreenwriterAgent.SYSTEM_PROMPT
    assert "bare-headed" in ScreenwriterAgent.SYSTEM_PROMPT


# --- eyeline ------------------------------------------------------------


def test_frame_prompt_keeps_the_face_visible_without_inviting_the_lens():
    from pipelines.script2video import build_frame_prompt

    prompt = build_frame_prompt(
        "Cinematic",
        _shot(),
        setting_location="rain-soaked cargo harbour",
        setting_time_of_day="night",
        characters=[_char("Mara", "orange hi-vis jacket")],
    )

    # Still readable...
    assert "lit and readable" in prompt
    assert "not a silhouette" in prompt
    # ...but no longer posing for the viewer. "Not turned away from camera"
    # used to sit in this same sentence, which is the frontal face a frontal
    # reference portrait renders with its eyes on the lens -- the pipeline
    # asking for the thing the next clause forbade.
    assert "not turned away from camera" not in prompt
    assert "never on the lens" in prompt
    assert "eyes stay inside the scene" in prompt


def test_reference_portrait_binds_the_staging_out_but_not_the_costume():
    """The reference is a frontal headshot, wearing the character's wardrobe,
    with its eyes on the lens. Excluding its staging is the point; excluding
    its clothing along with it is what let the outfit change every scene."""
    from pipelines.script2video import build_character_identity_clause

    mara = _char("Mara", "orange hi-vis jacket")
    clause = build_character_identity_clause([mara], matched_char=mara)

    assert "match that face exactly" in clause
    assert "its pose and framing belong to a portrait" in clause
    # The staging is still excluded...
    assert "stage this shot from its own description" in clause
    # ...and the outfit is explicitly not.
    assert "the exact outfit worn in it" in clause
    assert "Take ONLY the identity from it" not in clause


def test_the_costume_lock_and_the_reference_note_do_not_contradict(monkeypatch):
    """These two sentences sit three apart in the same prompt. When one says
    'wear what the reference wears' and the other says 'take only the face
    from it', the image model is free to pick, and it picked wrong."""
    from pipelines.script2video import build_character_identity_clause

    # No named wardrobe -> the costume lock points AT the reference image.
    mara = _char("Mara")
    clause = build_character_identity_clause([mara], matched_char=mara)

    assert "EXACT outfit from the reference image" in clause
    assert "the exact outfit worn in it" in clause
    assert "ONLY the identity" not in clause


def test_motion_prompt_stops_a_head_turning_to_camera_mid_shot():
    from pipelines.script2video import build_motion_prompt

    shot = _shot()
    shot.motion_desc = "she leans into the door"
    shot.camera_movement = "slow push-in"

    prompt = build_motion_prompt(shot, matched_char=_char("Mara"))

    assert "Nobody turns to look at the camera" in prompt


def test_storyboard_is_told_not_to_design_shots_that_face_the_viewer():
    from agents.storyboard_artist import StoryboardArtist

    assert "NEVER PLAY TO THE LENS" in StoryboardArtist.SYSTEM_PROMPT


def test_storyboard_setting_lock_allows_the_scripted_world_change():
    """The lock says every shot keeps the same place AND lighting, which on
    its own vetoes a climax whose whole event is the lights going out."""
    from agents.storyboard_artist import StoryboardArtist

    assert "The ONE exception" in StoryboardArtist.SYSTEM_PROMPT


def test_the_eyeline_is_stated_as_staging_on_every_frame():
    """Measured on three delivered dramas now: characters stopping mid-scene
    to look dead at the viewer.

    The rule was first made conditional on there being no reference character
    -- absent from almost every frame -- and then folded into the reference
    note so it could not be dropped. It kept failing, and the sentence says
    why: inside a note about the PORTRAIT it reads as "do not copy the
    reference's gaze", which a model can obey to the letter while still
    turning the eyes to the lens in this shot.

    It is staging, so it now lives with the composition, on every frame, and
    it names what the eyes ARE on -- which an image model follows far better
    than what they are not.
    """
    from pipelines.script2video import build_frame_prompt

    for matched in (True, False):
        mara = _char("Mara", "orange hi-vis jacket")
        prompt = build_frame_prompt(
            "Cinematic",
            _shot(),
            setting_location="rain-soaked cargo harbour",
            setting_time_of_day="night",
            characters=[mara],
            matched_char=mara if matched else None,
        )
        assert "eyes stay inside the scene" in prompt
        assert "on the other character or on the object in their hands" in prompt
        assert "never on the lens" in prompt


def test_the_eyeline_did_not_cost_the_scene_its_own_words():
    """This block is never dropped, so every character it takes comes out of
    the clauses that describe THIS beat (see test_image_prompt_budget)."""
    from pipelines.script2video import IDENTITY_CLAUSE_OVERHEAD

    assert IDENTITY_CLAUSE_OVERHEAD <= 800, IDENTITY_CLAUSE_OVERHEAD
