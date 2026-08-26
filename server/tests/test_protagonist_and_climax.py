"""The two ways a rendered drama stopped being the drama that was asked for.

Both were observed on one brief -- "A dock worker on a rain-soaked cargo
harbour finds a shipping container that hums with light, and the city's power
dies the moment she opens it":

  * "she" was rendered as two men, because the protagonist's description
    reached the image model with no gender in it at all;
  * the city's power never died, because the frame prompt locks the drama's
    lighting to scene 1 and that lock outranked the event the film is about.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# --- whose story it is ---------------------------------------------------


def _script(protagonist_description: str, brief: str):
    from interfaces.character import CharacterProfile, DramaScript

    return DramaScript(
        title="Harbour",
        logline="A container hums",
        user_brief=brief,
        characters=[
            CharacterProfile(
                name="Mara",
                description=protagonist_description,
                role="protagonist",
            ),
            CharacterProfile(
                name="Otto", description="60s, heavy build", role="supporting"
            ),
        ],
    )


def test_brief_gender_fills_a_description_that_states_none():
    from agents.screenwriter import ScreenwriterAgent

    script = _script(
        "thirties, weathered face, close-cropped hair",
        "A dock worker finds a container, and the power dies when she opens it.",
    )
    ScreenwriterAgent._apply_brief_gender(script)

    assert script.characters[0].description.startswith("woman, ")
    assert "weathered face" in script.characters[0].description
    # Supporting cast is never touched -- the brief only spoke for its lead.
    assert script.characters[1].description == "60s, heavy build"


def test_a_gendered_description_is_left_alone():
    """The model saw the whole brief; the marker list sees a word."""
    from agents.screenwriter import ScreenwriterAgent

    script = _script("man in his fifties, grey stubble", "...when she opens it.")
    ScreenwriterAgent._apply_brief_gender(script)

    assert script.characters[0].description == "man in his fifties, grey stubble"


def test_an_ungendered_brief_changes_nothing():
    from agents.screenwriter import ScreenwriterAgent

    script = _script("thirties, weathered face", "A container hums with light.")
    ScreenwriterAgent._apply_brief_gender(script)

    assert script.characters[0].description == "thirties, weathered face"


def test_the_applied_gender_reaches_voice_casting():
    """The written description and the cast voice must agree -- one word list
    serves both, so a character written as a woman cannot be voiced by George."""
    from agents.screenwriter import ScreenwriterAgent
    from tools.muapi_voice_generator import MuAPIVoiceGenerator

    script = _script("thirties, weathered face", "...the power dies when she opens it.")
    ScreenwriterAgent._apply_brief_gender(script)

    generator = MuAPIVoiceGenerator("test-key")
    generator.cast_characters(script.characters)

    assert (
        generator.voice_id_for_character("Mara")
        in MuAPIVoiceGenerator.FEMALE_VOICE_IDS
    )


# --- the event the film is about -----------------------------------------


def _scene(action: str, world_change: str = ""):
    from interfaces.character import ScriptScene

    return ScriptScene(action=action, world_change=world_change)


def test_world_change_persists_into_every_later_scene():
    """Once the power dies it stays dead -- otherwise the cut goes from a
    blackout straight back to a lit harbour."""
    from pipelines.idea2video import _world_state

    scenes = [
        _scene("She walks the pier."),
        _scene("She opens it.", "every light in the city goes out"),
        _scene("She stands in the dark."),
    ]

    assert _world_state(scenes, 0) == ("", "")
    assert _world_state(scenes, 1) == ("every light in the city goes out", "")
    assert _world_state(scenes, 2) == ("", "every light in the city goes out")


def test_scene_direction_carries_the_world_change_to_the_storyboard():
    from pipelines.idea2video import _format_scene_direction

    direction = _format_scene_direction(
        _scene("She opens it.", "every light in the city goes out")
    )

    assert "every light in the city goes out" in direction


def test_frame_prompt_breaks_the_lighting_lock_for_the_event():
    from pipelines.script2video import build_frame_prompt

    shot = SimpleNamespace(
        visual_desc="Mara pulls the container door wide",
        shot_type="wide shot",
        lens="35mm",
    )
    kwargs = dict(
        setting_location="rain-soaked cargo harbour",
        setting_time_of_day="night",
        setting_era="present day",
    )

    ordinary = build_frame_prompt("Cinematic", shot, **kwargs)
    event = build_frame_prompt(
        "Cinematic",
        shot,
        world_change="every light in the city and on the docks goes out",
        **kwargs,
    )

    # The lock still holds for an ordinary scene.
    assert "the room itself must not change" in ordinary
    # ...and gets out of the way for the one scene the drama exists for.
    assert "must not change" not in event
    assert "every light in the city and on the docks goes out" in event
    assert "architecture are unchanged" in event


def test_frame_prompt_keeps_a_changed_world_changed():
    """A scene AFTER the blackout inherits it, without re-staging the event."""
    from pipelines.script2video import build_frame_prompt

    shot = SimpleNamespace(
        visual_desc="Mara stands still", shot_type="medium shot", lens="50mm"
    )
    after = build_frame_prompt(
        "Cinematic",
        shot,
        setting_location="rain-soaked cargo harbour",
        setting_time_of_day="night",
        world_state="every light in the city goes out",
    )

    assert "every light in the city goes out" in after
    assert "must not change" not in after


def test_lighting_plan_is_suppressed_once_the_lights_are_out():
    """The plan is derived from the time of day ("night harbour -> sodium
    streetlamps") -- the exact thing the blackout removes."""
    from interfaces.lighting import resolve_lighting
    from pipelines.script2video import build_frame_prompt

    shot = SimpleNamespace(
        visual_desc="Mara stands still", shot_type="medium shot", lens="50mm"
    )
    plan_clause = resolve_lighting("night").as_clause()
    assert plan_clause  # guard: the assertion below would be vacuous otherwise

    lit = build_frame_prompt(
        "Cinematic", shot, setting_location="harbour", setting_time_of_day="night"
    )
    dark = build_frame_prompt(
        "Cinematic",
        shot,
        setting_location="harbour",
        setting_time_of_day="night",
        world_change="every light goes out",
    )

    assert plan_clause in lit
    assert plan_clause not in dark


def test_the_video_model_is_told_the_world_has_already_changed():
    """The still can be correctly dark and the five seconds animated out of it
    still re-light the harbour: "lit night dock" is the strongest prior a
    video model has, and nothing in the motion prompt contradicted it."""
    from pipelines.script2video import build_motion_prompt

    shot = SimpleNamespace(
        motion_desc="she steps back from the container",
        camera_movement="slow push-in",
        expression_desc="eyes wide",
    )

    prompt = build_motion_prompt(shot, world_state="every light on the docks is out")

    assert "every light on the docks is out" in prompt
    assert "must not revert, recover or re-light" in prompt


def test_an_unchanged_world_leaves_the_motion_prompt_exactly_as_it_was():
    from pipelines.script2video import build_motion_prompt

    shot = SimpleNamespace(
        motion_desc="she steps back",
        camera_movement="slow push-in",
        expression_desc="eyes wide",
    )

    assert build_motion_prompt(shot) == build_motion_prompt(shot, world_state="  ")
    assert "already changed" not in build_motion_prompt(shot)


# --- the event survives the prompt budget --------------------------------


def _segments(**kwargs):
    """The (priority, text) list build_frame_prompt hands the assembler.

    Captured rather than inferred from the finished string: what changed here
    is a RANK, and a rank is only visible before the squeeze decides on it.
    """
    from pipelines import script2video

    captured = {}
    real = script2video.fit_image_prompt

    def spy(segments, *args, **kw):
        captured["segments"] = list(segments)
        return real(segments, *args, **kw)

    shot = SimpleNamespace(
        visual_desc="Elena hauls the container door wide",
        shot_type="wide shot",
        lens="35mm",
    )
    script2video.fit_image_prompt = spy
    try:
        script2video.build_frame_prompt(
            "Sci-Fi",
            shot,
            setting_location=(
                "rain-soaked cargo harbour among stacked shipping containers "
                "under sodium floodlights"
            ),
            setting_time_of_day="night",
            setting_era="present day",
            **kwargs,
        )
    finally:
        script2video.fit_image_prompt = real
    return captured["segments"]


def _rank_of(segments, needle):
    return next(prio for prio, text in segments if needle in (text or ""))


def test_the_scene_that_carries_the_event_cannot_be_squeezed_out_of_it():
    """930f11de-4b0 went over budget on all six of its frames -- "dropping 262
    chars of lower-priority direction" x6 -- and cleared it with 262 to spare.

    The setting clause is the only thing in the prompt that says the lights go
    out, and it was ranked droppable: one rung under the identity clause it
    competes with, so a second described character would have bought its faces
    with the film's own climax.
    """
    from pipelines.script2video import REQUIRED

    change = "every light in the city and on the docks goes out"
    segments = _segments(world_change=change)

    assert _rank_of(segments, change) == REQUIRED


def test_a_scene_after_the_blackout_is_protected_too():
    """Inherited state is the same event, one scene later."""
    from pipelines.script2video import REQUIRED

    state = "every light on the docks is out"
    segments = _segments(world_state=state)

    assert _rank_of(segments, state) == REQUIRED


def test_an_ordinary_scene_still_pays_for_its_faces_with_continuity():
    """Unchanged where nothing is at stake: with no event to protect, the
    continuity clause is direction, and direction is what a squeeze is for."""
    from pipelines.script2video import REQUIRED

    segments = _segments()

    rank = _rank_of(segments, "the room itself must not change")
    assert rank != REQUIRED
    assert rank > 0


def test_the_protected_clause_really_does_survive_a_squeeze():
    """The rank, spent: under a limit nothing optional can fit, the event is
    still there and the optional direction is not."""
    from pipelines.script2video import REQUIRED, fit_image_prompt

    kept = fit_image_prompt(
        [(REQUIRED, "the lights go out. "), (1, "continuity. ")], limit=25
    )

    assert "the lights go out" in kept
    assert "continuity" not in kept
