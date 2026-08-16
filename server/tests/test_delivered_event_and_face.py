"""The two things a voiced delivery got wrong that a silent one had not.

Both measured on the same 18-second drama, the first one with audio:

  * it ended on a face with glowing white eyes and a screaming mouth — the
    fear beat asked for "eyes flaring white above the iris" and "mouth
    pulled wide and open", and the image model drew exactly that;
  * the city's power was SAID to be gone ("Control's gone") while every lamp
    in the frame stayed on. Dialogue gave the script a way to discharge the
    brief without filming it — the one failure a silent script cannot make.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

BRIEF = (
    "A dock worker on a rain-soaked cargo harbour finds a shipping container "
    "that hums with light, and the city's power dies the moment she opens it."
)


def _script(scenes, brief=BRIEF):
    from interfaces.character import DramaScript

    return DramaScript(title="T", logline="L", user_brief=brief, scenes=scenes)


# --- the face ------------------------------------------------------------


def test_no_beat_can_be_drawn_as_a_change_to_the_eye_itself():
    """An anatomical phrase is a material instruction to an image model."""
    import re

    from interfaces import acting

    source = open(acting.__file__).read()
    peaks = [
        " ".join(re.findall(r'"([^"]*)"', block))
        for block in re.findall(r"peak=\(\s*((?:\"[^\"]*\"\s*)+)\)", source)
    ]
    assert peaks, "no peaks found — the scan is looking in the wrong place"

    for peak in peaks:
        low = peak.lower()
        assert "white" not in low, peak
        assert "glow" not in low, peak
        assert "blood" not in low, peak


def test_fear_is_written_as_muscle_not_as_a_scream():
    from interfaces.acting import resolve

    peak = resolve("dread").peak.lower()

    assert "white" not in peak
    assert "mouth pulled wide" not in peak
    # Still a real, watchable change.
    assert "eyelids" in peak or "brows" in peak


def test_the_edit_prompt_forbids_the_render_that_actually_happened():
    from interfaces.acting import end_frame_edit_prompt, resolve

    prompt = end_frame_edit_prompt(resolve("fear").peak)

    assert "MUSCULAR ONLY" in prompt
    assert "no glowing" in prompt
    assert "no horror or monster effect" in prompt


# --- the event -----------------------------------------------------------


def test_the_briefs_event_is_restored_when_no_scene_declares_one():
    from agents.screenwriter import ScreenwriterAgent

    script = _script(
        [
            {"action": "She walks the pier.", "dramatic_function": "setup"},
            {"action": "She opens it.", "dramatic_function": "climax"},
        ]
    )
    ScreenwriterAgent._apply_brief_event(script)

    assert "power dies" in script.scenes[1].world_change
    # ...and only on the climax; an earlier scene must not pre-empt it.
    assert script.scenes[0].world_change == ""


def test_a_script_that_named_its_own_change_is_left_alone():
    """The model read the whole brief; this reads a word list."""
    from agents.screenwriter import ScreenwriterAgent

    script = _script(
        [
            {"action": "She opens it.", "dramatic_function": "climax",
             "world_change": "every lamp on the quay goes out at once"},
        ]
    )
    ScreenwriterAgent._apply_brief_event(script)

    assert script.scenes[0].world_change == "every lamp on the quay goes out at once"


def test_a_brief_with_no_world_event_gets_nothing_invented():
    from agents.screenwriter import ScreenwriterAgent

    script = _script(
        [{"action": "They argue.", "dramatic_function": "climax"}],
        brief="Two brothers argue about an inheritance in a kitchen.",
    )
    ScreenwriterAgent._apply_brief_event(script)

    assert script.scenes[0].world_change == ""


def test_two_candidate_events_defer_rather_than_guess():
    from agents.screenwriter import ScreenwriterAgent

    script = _script(
        [{"action": "It happens.", "dramatic_function": "climax"}],
        brief="The dam collapses. Later the power dies across the valley.",
    )
    ScreenwriterAgent._apply_brief_event(script)

    assert script.scenes[0].world_change == ""


def test_a_turkish_brief_is_read_too():
    from agents.screenwriter import ScreenwriterAgent

    script = _script(
        [{"action": "Kapağı açar.", "dramatic_function": "climax"}],
        brief="Konteyneri açtığı anda şehrin elektriği kesilir.",
    )
    ScreenwriterAgent._apply_brief_event(script)

    assert "elektriği kesilir" in script.scenes[0].world_change


def test_the_last_scene_carries_it_when_nothing_is_labelled_climax():
    from agents.screenwriter import ScreenwriterAgent

    script = _script([{"action": "She walks."}, {"action": "She opens it."}])
    ScreenwriterAgent._apply_brief_event(script)

    assert script.scenes[1].world_change
    assert script.scenes[0].world_change == ""


def test_legacy_string_scenes_do_not_break_the_guard():
    from agents.screenwriter import ScreenwriterAgent

    script = _script(["A legacy silent scene."])
    ScreenwriterAgent._apply_brief_event(script)  # must not raise

    assert script.scenes == ["A legacy silent scene."]


def test_a_voiced_script_is_told_a_line_is_not_the_event():
    from agents.screenwriter import ScreenwriterAgent

    clause = ScreenwriterAgent.DIALOGUE_CLAUSE

    assert "A LINE IS NOT THE EVENT" in clause
    assert "never the only place it exists" in clause


def test_the_restored_event_reaches_the_frame_prompt():
    """End to end: the field the guard fills is the field that breaks the
    drama's locked lighting."""
    from types import SimpleNamespace

    from agents.screenwriter import ScreenwriterAgent
    from pipelines.idea2video import _world_state
    from pipelines.script2video import build_frame_prompt

    script = _script(
        [
            {"action": "She walks the pier.", "dramatic_function": "setup"},
            {"action": "She opens it.", "dramatic_function": "climax"},
        ]
    )
    ScreenwriterAgent._apply_brief_event(script)
    change, _ = _world_state(script.scenes, 1)

    prompt = build_frame_prompt(
        "Cinematic",
        SimpleNamespace(
            visual_desc="She hauls the door wide",
            shot_type="wide shot",
            lens="35mm",
        ),
        setting_location="rain-soaked cargo harbour",
        setting_time_of_day="night",
        world_change=change,
    )

    assert "power dies" in prompt
    assert "must not change" not in prompt
