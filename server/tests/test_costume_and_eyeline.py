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
    assert "unless the character's own outfit names one" in clause


def test_the_no_additions_rule_also_covers_an_undescribed_outfit():
    from pipelines.script2video import build_character_identity_clause

    clause = build_character_identity_clause([_char("Mara")])

    assert "Clothing is also FIXED" in clause
    assert "hard hat" in clause


def test_a_named_hat_is_kept_rather_than_banned():
    """The rule bans UNNAMED headwear; a scripted hard hat must survive it."""
    from pipelines.script2video import build_character_identity_clause

    clause = build_character_identity_clause(
        [_char("Mara", "orange hi-vis jacket and a yellow hard hat")]
    )

    assert "yellow hard hat" in clause
    assert "worn in every scene, never taken off or replaced" in clause


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
    assert "not turned away from camera" in prompt
    # ...but no longer posing for the viewer.
    assert "does NOT look into the lens" in prompt
    assert "gaze stays inside the scene" in prompt


def test_reference_portrait_binds_identity_only_not_its_gaze():
    """The reference is a frontal headshot with its eyes on the lens; without
    this the identity anchor drags the shot's staging along with the face."""
    from pipelines.script2video import build_character_identity_clause

    mara = _char("Mara", "orange hi-vis jacket")
    clause = build_character_identity_clause([mara], matched_char=mara)

    assert "match that face exactly" in clause
    assert "Take ONLY the identity from it" in clause
    assert "gaze into the lens" in clause


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
