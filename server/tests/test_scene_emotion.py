"""Emotion / dramatic-moment fidelity tests.

Covers a reported failure where generated scenes read as flat and
"unrelated to the story": the character's expression didn't match the
story beat, and the storyboard picked set-up moments over emotional ones.
The chain that has to hold end to end is:

    screenwriter emotion + dialogue
      -> storyboard artist prompt (which moment to draw, what face to show)
      -> shot.expression_desc
      -> frame prompt sent to the image model
"""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import (  # noqa: E402
    CharacterInScene,
    DialogueLine,
    ScriptScene,
)
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.idea2video import _format_scene_dialogue, _scene_emotion  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    build_character_identity_clause,
    build_frame_prompt,
)


def _shot(**overrides):
    base = dict(
        idx=0,
        visual_desc="Mother and daughter at the kitchen table",
        motion_desc="slow push-in",
        expression_desc="",
        audio_desc="ambient",
        shot_type="close-up",
        camera_movement="static",
        lens="50mm",
        duration_seconds=8.0,
    )
    base.update(overrides)
    return StoryboardShot(**base)


# --- screenwriter -> pipeline extraction -------------------------------


def test_scene_emotion_read_from_structured_scene():
    scene = ScriptScene(action="They embrace.", dialogue=[], emotion="tearful relief")
    assert _scene_emotion(scene) == "tearful relief"


def test_scene_emotion_empty_for_legacy_string_scenes():
    """Legacy scripts store scenes as bare strings -- must not crash."""
    assert _scene_emotion("Maya walks the pier.") == ""
    assert _scene_emotion({"action": "no emotion key"}) == ""


def test_scene_dialogue_formatted_for_storyboard():
    """The words that carry the emotional turn must reach the storyboard
    agent -- previously it only ever saw the action line."""
    scene = ScriptScene(
        action="They finally speak.",
        dialogue=[
            DialogueLine(character="Ayse", line="I never stopped waiting."),
            DialogueLine(character="Elif", line="I know, anne."),
        ],
        emotion="tearful reconciliation",
    )
    text = _format_scene_dialogue(scene.dialogue)
    assert "Ayse: I never stopped waiting." in text
    assert "Elif: I know, anne." in text


def test_scene_dialogue_skips_blank_lines():
    assert _format_scene_dialogue([]) == ""
    assert _format_scene_dialogue([{"character": "A", "line": "   "}]) == ""


# --- storyboard artist -------------------------------------------------


def test_system_prompt_demands_dramatic_peak_and_visible_emotion():
    prompt = StoryboardArtist.SYSTEM_PROMPT
    assert "DRAMATIC PEAK" in prompt
    assert "expression_desc" in prompt
    # Must steer away from silhouettes/backlight that make faces unreadable.
    assert "silhouette" in prompt.lower()


def test_emotion_and_dialogue_lines_reach_the_prompt():
    emotion_line = StoryboardArtist._format_emotion_line("tearful reconciliation")
    assert "tearful reconciliation" in emotion_line

    dialogue_line = StoryboardArtist._format_dialogue_line("Elif: I know, anne.")
    assert "Elif: I know, anne." in dialogue_line


def test_emotion_and_dialogue_lines_omitted_when_empty():
    assert StoryboardArtist._format_emotion_line("") == ""
    assert StoryboardArtist._format_emotion_line("   ") == ""
    assert StoryboardArtist._format_dialogue_line("") == ""


@pytest.mark.parametrize("flat", ["", "neutral", "Calm", "expressionless", "N/A"])
def test_flat_expression_falls_back_to_scene_emotion(flat):
    """A missing or neutral expression is exactly the reported bug, so it is
    not left to the LLM's discretion."""
    shots = [_shot(expression_desc=flat)]
    StoryboardArtist._ensure_expression(shots, "tearful reconciliation")
    assert shots[0].expression_desc == "tearful reconciliation"


def test_real_expression_from_the_model_is_preserved():
    shots = [_shot(expression_desc="chin trembling, eyes brimming")]
    StoryboardArtist._ensure_expression(shots, "tearful reconciliation")
    assert shots[0].expression_desc == "chin trembling, eyes brimming"


def test_ensure_expression_noop_without_scene_emotion():
    shots = [_shot(expression_desc="")]
    StoryboardArtist._ensure_expression(shots, "")
    assert shots[0].expression_desc == ""


@pytest.mark.asyncio
async def test_template_fallback_carries_scene_emotion():
    """Even the no-API-key deterministic path must not produce a blank face."""
    artist = StoryboardArtist(api_key="")
    artist.muapi_key = ""
    shots = await artist.design_storyboard(
        script="Mother and daughter finally embrace.",
        characters=[
            CharacterInScene(idx=0, name="Ayse", static_features="50s woman")
        ],
        scene_emotion="tearful reconciliation",
    )
    assert shots[0].expression_desc == "tearful reconciliation"


# --- frame prompt ------------------------------------------------------


def test_frame_prompt_states_expression_and_demands_readable_face():
    prompt = build_frame_prompt(
        "Cinematic", _shot(expression_desc="chin trembling, eyes brimming")
    )
    assert "chin trembling, eyes brimming" in prompt
    assert "clearly readable on the face" in prompt
    assert "not a silhouette" in prompt


def test_frame_prompt_without_expression_still_requires_visible_face():
    prompt = build_frame_prompt("Cinematic", _shot(expression_desc=""))
    assert "not a silhouette" in prompt
    assert "Facial expression and body language:" not in prompt


def test_frame_prompt_works_with_shots_lacking_expression_field():
    """SimpleNamespace/legacy shot objects have no expression_desc."""
    legacy = SimpleNamespace(
        visual_desc="Maya walks the pier", shot_type="medium shot", lens="50mm"
    )
    prompt = build_frame_prompt("Cinematic", legacy)
    assert "Maya walks the pier" in prompt


# --- multi-character identity pinning ----------------------------------


def test_identity_clause_pins_every_on_screen_character():
    """Only ONE character gets a reference image, so the others need a
    textual anchor or they get re-invented every scene."""
    characters = [
        CharacterInScene(idx=0, name="Ayse", static_features="50s woman, grey bun"),
        CharacterInScene(idx=1, name="Elif", static_features="20s woman, long dark hair"),
    ]
    clause = build_character_identity_clause(characters, matched_char=characters[0])

    assert "Ayse (50s woman, grey bun)" in clause
    assert "Elif (20s woman, long dark hair)" in clause
    assert "IDENTICAL to previous scenes" in clause
    # The referenced character must be identified so the model knows which
    # face the attached image belongs to.
    assert "reference image is Ayse" in clause


def test_identity_clause_skips_invisible_and_undescribed_characters():
    characters = [
        CharacterInScene(idx=0, name="Ayse", static_features="50s woman"),
        CharacterInScene(idx=1, name="Ghost", static_features="unseen", is_visible=False),
        CharacterInScene(idx=2, name="Blank", static_features="   "),
    ]
    clause = build_character_identity_clause(characters)
    assert "Ayse" in clause
    assert "Ghost" not in clause
    assert "Blank" not in clause


def test_identity_clause_empty_without_characters():
    assert build_character_identity_clause(None) == ""
    assert build_character_identity_clause([]) == ""


def test_frame_prompt_includes_identity_clause_when_characters_given():
    characters = [
        CharacterInScene(idx=0, name="Ayse", static_features="50s woman, grey bun"),
        CharacterInScene(idx=1, name="Elif", static_features="20s woman, long dark hair"),
    ]
    prompt = build_frame_prompt(
        "Cinematic",
        _shot(expression_desc="tearful"),
        characters=characters,
        matched_char=characters[1],
    )
    assert "Ayse (50s woman, grey bun)" in prompt
    assert "Elif (20s woman, long dark hair)" in prompt
    assert "reference image is Elif" in prompt


# --- end-to-end through the real pipeline ------------------------------


@pytest.mark.asyncio
async def test_emotion_and_identity_reach_the_image_model(monkeypatch, tmp_path):
    """End-to-end: a scene's emotion and BOTH characters' locked appearances
    must appear in the prompt actually sent to the image generator."""
    import agents.storyboard_artist as sb_mod
    import pipelines.script2video as s2v_mod
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod
    from pipelines.script2video import Script2VideoPipeline

    captured_prompts = []
    captured_storyboard_kwargs = {}

    async def fake_design_storyboard(self, script, characters, user_requirement="",
                                     director_style="cinematic_balanced", **kwargs):
        captured_storyboard_kwargs.update(kwargs)
        # Model returns a flat expression -- the pipeline must repair it
        # from the scene's emotion rather than shipping a neutral face.
        return [
            StoryboardShot(
                idx=0,
                visual_desc="Ayse and Elif at the kitchen table",
                motion_desc="slow push-in",
                expression_desc="neutral",
            )
        ]

    async def fake_img_ref(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        captured_prompts.append(prompt)
        return "https://fake.cdn/frame.png"

    async def fake_video(self, prompt, image_url, duration=5, aspect_ratio="16:9",
                         plan="free", is_cancelled=None):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_img_ref)
    monkeypatch.setattr(vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_video)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)

    characters = [
        CharacterInScene(idx=0, name="Ayse", static_features="50s woman, grey bun"),
        CharacterInScene(idx=1, name="Elif", static_features="20s woman, long dark hair"),
    ]
    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    await pipeline.run(
        script="Ayse and Elif finally speak.",
        characters=characters,
        working_dir=str(tmp_path / "scene"),
        character_portraits={
            "Ayse": "https://fake.cdn/ayse.png",
            "Elif": "https://fake.cdn/elif.png",
        },
        scene_emotion="tearful reconciliation",
        scene_dialogue="Elif: I know, anne.",
    )

    # The storyboard agent received the story context it needs to pick a moment.
    assert captured_storyboard_kwargs.get("scene_emotion") == "tearful reconciliation"
    assert captured_storyboard_kwargs.get("scene_dialogue") == "Elif: I know, anne."

    assert len(captured_prompts) == 1
    prompt = captured_prompts[0]
    # Flat "neutral" was repaired from the scene emotion.
    assert "tearful reconciliation" in prompt
    assert "not a silhouette" in prompt
    # BOTH characters pinned, even though only one reference image is sent.
    assert "Ayse (50s woman, grey bun)" in prompt
    assert "Elif (20s woman, long dark hair)" in prompt
