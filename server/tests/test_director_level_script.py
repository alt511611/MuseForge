"""Director-level screenwriting: structure, turn, subtext, staging, motif.

The screenwriter is asked to direct rather than summarize a plot. Every field
it produces has to survive all the way to the storyboard agent -- a field
nothing reads is worse than no field at all (see the color_grade regression,
where DirectorStyle named a grade for six presets and nothing ever used it).
The last test in this file exists specifically to catch that class of bug.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from agents.storyboard_artist import StoryboardArtist  # noqa: E402
from interfaces.character import (  # noqa: E402
    DRAMATIC_FUNCTIONS,
    CharacterProfile,
    DialogueLine,
    DramaScript,
    ScriptScene,
)
from pipelines.idea2video import (  # noqa: E402
    _format_character_direction,
    _format_scene_direction,
    _scene_field,
)
from pipelines.script2video import build_character_identity_clause  # noqa: E402


def _rich_scene(**overrides):
    base = dict(
        action="Elif puts the cup in her bag. Ayse watches.",
        dialogue=[DialogueLine(character="Ayse", line="That cup was always yours.")],
        emotion="tearful reconciliation",
        dramatic_function="climax",
        turn="Elif takes the cup back out and sets it near her mother's hand",
        subtext="They are talking about the cup but mean staying",
        staging="Elif standing, bag half open; Ayse seated, palms up on the table",
        tension=9,
    )
    base.update(overrides)
    return ScriptScene(**base)


# --- the screenwriter is asked to direct -------------------------------


def test_system_prompt_demands_dramatic_structure():
    prompt = ScreenwriterAgent.SYSTEM_PROMPT
    assert "dramatic_function" in prompt
    assert "climax" in prompt
    # Must forbid a flat run of identical beats.
    assert "do not write five scenes of rising_action" in prompt


def test_system_prompt_demands_a_turn_subtext_and_staging():
    prompt = ScreenwriterAgent.SYSTEM_PROMPT
    assert "EVERY SCENE MUST TURN" in prompt
    assert "WRITE SUBTEXT" in prompt
    assert "STAGE IT PHYSICALLY" in prompt
    # Performance direction, not just plot.
    assert '"want"' in prompt and '"need"' in prompt and '"arc"' in prompt


def test_system_prompt_separates_wardrobe_from_face():
    """The reference image binds a face, not an outfit, so they are distinct
    fields and the prompt must say so."""
    prompt = ScreenwriterAgent.SYSTEM_PROMPT
    assert "wardrobe" in prompt
    assert "face, build and age ONLY" in prompt


def test_system_prompt_asks_for_a_through_line():
    prompt = ScreenwriterAgent.SYSTEM_PROMPT
    assert "theme" in prompt
    assert "visual_motif" in prompt


def test_preset_character_instruction_survives_rewrites():
    """Regression: rewrapping the prompt once split this phrase across lines."""
    assert "do NOT redefine" in ScreenwriterAgent.SYSTEM_PROMPT


def test_max_tokens_raised_for_the_richer_schema():
    """A truncated response is unparseable JSON and silently drops the whole
    script to the template fallback."""
    assert ScreenwriterAgent.MAX_SCRIPT_TOKENS >= 8192


def test_both_provider_paths_share_the_token_budget():
    """Regression: the budget was raised only on the direct-Anthropic
    fallback, while the MuAPI route -- which is tried FIRST -- kept the old
    2048 default and truncated its JSON mid-object. The symptom is a generic
    template script, with nothing in the output explaining why."""
    import inspect

    muapi_call = inspect.getsource(ScreenwriterAgent.write_script)
    anthropic_call = inspect.getsource(ScreenwriterAgent._write_with_claude)
    assert "max_tokens=self.MAX_SCRIPT_TOKENS" in muapi_call
    assert '"max_tokens": self.MAX_SCRIPT_TOKENS' in anthropic_call


def test_storyboard_also_passes_its_budget_to_muapi():
    import inspect

    source = inspect.getsource(StoryboardArtist.design_storyboard)
    assert "max_tokens=self.MAX_SHOT_TOKENS" in source


# --- template fallback still has a dramatic shape ----------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("num_scenes", [2, 3, 4, 5])
async def test_template_fallback_always_peaks_and_resolves(num_scenes):
    """However many scenes are requested, the offline script must still be a
    drama: it has to climax somewhere and end on a resolution."""
    agent = ScreenwriterAgent(demo=True)
    script = await agent.write_script("A reunion", num_scenes=num_scenes)

    functions = [s.dramatic_function for s in script.scenes]
    assert functions[-1] == "resolution", functions
    assert "climax" in functions, functions
    assert all(f in DRAMATIC_FUNCTIONS for f in functions), functions


@pytest.mark.asyncio
@pytest.mark.parametrize("num_scenes", [2, 3, 4, 5])
async def test_template_fallback_tension_peaks_at_the_climax(num_scenes):
    """Tension must rise into the climax and release after it, rather than
    being a flat or arbitrary sequence of numbers."""
    agent = ScreenwriterAgent(demo=True)
    script = await agent.write_script("A reunion", num_scenes=num_scenes)

    tensions = [s.tension for s in script.scenes]
    climax_at = [s.dramatic_function for s in script.scenes].index("climax")

    assert tensions[climax_at] == max(tensions), tensions
    # Everything before the climax escalates towards it.
    assert tensions[:climax_at] == sorted(tensions[:climax_at]), tensions
    # The resolution releases.
    assert tensions[-1] < tensions[climax_at], tensions


@pytest.mark.asyncio
@pytest.mark.parametrize("num_scenes", [2, 3, 4, 5])
async def test_template_fallback_beat_matches_its_action(num_scenes):
    """Regression: an earlier version patched a scene's function and turn but
    kept the previous beat's action line, so a 'resolution' scene still read
    'a pivotal moment - makes a decisive choice'."""
    agent = ScreenwriterAgent(demo=True)
    script = await agent.write_script("A reunion", num_scenes=num_scenes)

    by_function = {s.dramatic_function: s for s in script.scenes}
    if "climax" in by_function:
        assert "decisive choice" in by_function["climax"].action
    assert "Final frame" in by_function["resolution"].action
    if "setup" in by_function:
        assert "enters" in by_function["setup"].action


@pytest.mark.asyncio
async def test_template_fallback_scenes_carry_turn_and_staging():
    agent = ScreenwriterAgent(demo=True)
    script = await agent.write_script("A reunion", num_scenes=3)

    for scene in script.scenes:
        assert scene.turn.strip(), "every scene needs a turn to be filmable"
        assert scene.staging.strip()
        assert scene.emotion.strip()
        assert 1 <= scene.tension <= 10


@pytest.mark.asyncio
async def test_template_fallback_has_theme_and_motif():
    agent = ScreenwriterAgent(demo=True)
    script = await agent.write_script("A reunion", num_scenes=3)
    assert script.theme.strip()
    assert script.visual_motif.strip()


# --- extraction --------------------------------------------------------


def test_scene_direction_rendered_for_the_storyboard():
    block = _format_scene_direction(_rich_scene())
    assert "Dramatic function: climax" in block
    assert "sets it near her mother's hand" in block
    assert "mean staying" in block
    assert "palms up on the table" in block
    assert "Dramatic tension: 9/10" in block


def test_scene_direction_empty_for_legacy_scenes():
    """Legacy scripts store scenes as bare strings and carry none of this."""
    assert _format_scene_direction("Maya walks the pier.") == ""
    assert _format_scene_direction({"action": "no direction fields"}) == ""


def test_zero_tension_is_omitted_rather_than_printed():
    block = _format_scene_direction(_rich_scene(tension=0))
    assert "tension" not in block.lower()


def test_scene_field_reads_objects_dicts_and_strings():
    scene = _rich_scene()
    assert _scene_field(scene, "turn").startswith("Elif takes the cup")
    assert _scene_field(scene.model_dump(), "turn").startswith("Elif takes the cup")
    assert _scene_field("legacy string scene", "turn") == ""
    assert _scene_field(scene, "no_such_field") == ""


def test_character_direction_rendered():
    script = DramaScript(
        title="t",
        logline="l",
        characters=[
            CharacterProfile(
                name="Ayse", description="52", want="to keep her daughter",
                need="to admit she left", arc="from silence to confession",
            ),
            CharacterProfile(name="Extra", description="a neighbour"),
        ],
    )
    block = _format_character_direction(script)
    assert "Ayse — wants: to keep her daughter" in block
    assert "needs: to admit she left" in block
    assert "arc: from silence to confession" in block
    # A character with no direction contributes no empty line.
    assert "Extra" not in block


# --- storyboard agent consumption --------------------------------------


def test_storyboard_prompt_blocks_render_and_omit_cleanly():
    direction = _format_scene_direction(_rich_scene())
    block = StoryboardArtist._format_direction_block(direction)
    assert "DIRECTOR'S NOTES" in block
    assert "THE TURN" in block
    assert StoryboardArtist._format_direction_block("") == ""
    assert StoryboardArtist._format_direction_block("   ") == ""

    through = StoryboardArtist._format_through_line("Forgiving is not forgetting", "a cracked cup")
    assert "Forgiving is not forgetting" in through
    assert "a cracked cup" in through
    assert StoryboardArtist._format_through_line("", "") == ""

    perf = StoryboardArtist._format_character_direction_block("Ayse — wants: x")
    assert "Ayse — wants: x" in perf
    assert StoryboardArtist._format_character_direction_block("") == ""


def test_storyboard_system_prompt_uses_the_direction():
    prompt = StoryboardArtist.SYSTEM_PROMPT
    # The turn decides which moment is filmed.
    assert "THE TURN" in prompt
    # Shot scale must follow the beat, not be uniform.
    assert "MATCH SHOT SCALE TO THE BEAT" in prompt
    assert "tension of 8+" in prompt
    # Expression plays the subtext, not the line.
    assert "PLAY THE SUBTEXT" in prompt


@pytest.mark.asyncio
async def test_direction_reaches_the_storyboard_agent(monkeypatch, tmp_path):
    """End-to-end: the director's notes must arrive in the agent's prompt."""
    import agents.storyboard_artist as sb_mod
    import pipelines.script2video as s2v_mod
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod
    from interfaces.character import CharacterInScene
    from interfaces.shot import StoryboardShot
    from pipelines.script2video import Script2VideoPipeline

    seen = {}

    async def fake_design(self, script, characters, user_requirement="",
                          director_style="cinematic_balanced", **kwargs):
        seen.update(kwargs)
        return [StoryboardShot(idx=0, visual_desc="two women", motion_desc="push-in")]

    async def fake_img(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        return "https://fake.cdn/f.png"

    async def fake_vid(self, prompt, image_url, duration=5, aspect_ratio="16:9",
                       plan="free", is_cancelled=None):
        return "https://fake.cdn/v.mp4"

    async def fake_dl(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(path, "wb").write(b"x")
        return path

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_img)
    monkeypatch.setattr(vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_vid)
    monkeypatch.setattr(s2v_mod, "download_video", fake_dl)

    pipeline = Script2VideoPipeline(api_key="k", demo=False)
    await pipeline.run(
        script="They finally speak.",
        characters=[CharacterInScene(idx=0, name="Ayse", static_features="52")],
        working_dir=str(tmp_path / "s"),
        character_portraits={"Ayse": "https://fake.cdn/p.png"},
        scene_direction="THE TURN — film this moment: she takes the cup back out",
        character_direction="Ayse — wants: to keep her daughter",
        theme="Forgiving is not forgetting",
        visual_motif="a cracked porcelain cup",
    )

    assert "she takes the cup back out" in seen["scene_direction"]
    assert "to keep her daughter" in seen["character_direction"]
    assert seen["theme"] == "Forgiving is not forgetting"
    assert seen["visual_motif"] == "a cracked porcelain cup"


# --- wardrobe ----------------------------------------------------------


def test_wardrobe_pinned_alongside_the_face():
    from interfaces.character import CharacterInScene

    characters = [
        CharacterInScene(idx=0, name="Ayse", static_features="52, grey bun",
                         wardrobe="faded blue house apron"),
        CharacterInScene(idx=1, name="Elif", static_features="24, long dark hair"),
    ]
    clause = build_character_identity_clause(characters)
    assert "Ayse (52, grey bun, wearing faded blue house apron)" in clause
    # No wardrobe -> no dangling "wearing".
    assert "Elif (24, long dark hair)" in clause


def test_characters_from_script_carries_wardrobe():
    from pipelines.idea2video import Idea2VideoPipeline

    script = DramaScript(
        title="t", logline="l",
        characters=[CharacterProfile(name="Ayse", description="52", wardrobe="blue apron")],
    )
    pipeline = Idea2VideoPipeline(api_key="", demo=True)
    [char] = pipeline._characters_from_script(script)
    assert char.wardrobe == "blue apron"


# --- the anti-dead-field guard -----------------------------------------


def test_every_director_field_is_actually_consumed():
    """Guard against the color_grade class of bug: a field the screenwriter is
    told to produce, that nothing downstream ever reads.

    Each new field must appear somewhere in the code that builds prompts.
    """
    import inspect

    import pipelines.idea2video as idea2video_mod
    import pipelines.script2video as script2video_mod

    consuming_code = "".join(
        inspect.getsource(mod)
        for mod in (idea2video_mod, script2video_mod, StoryboardArtist)
    )

    for field in (
        "dramatic_function", "turn", "subtext", "staging", "tension",
        "theme", "visual_motif", "wardrobe", "want", "need", "arc",
    ):
        assert field in consuming_code, (
            f"screenwriter emits {field!r} but no pipeline code reads it -- "
            "either consume it or stop asking the model to produce it"
        )


# --- a failed screenwriter must not fail silently -----------------------


def test_template_script_is_marked_as_degraded():
    """The fallback discards the user's idea almost entirely -- generic
    setting, a character named "Alex". Shipping that unlabelled makes the
    product look like it cannot follow a prompt."""
    import asyncio

    script = asyncio.run(
        ScreenwriterAgent(demo=True).write_script("a forest quest", num_scenes=3)
    )
    assert script.generated_by == "template"
    # An LLM-written script is the default and stays unlabelled.
    assert DramaScript(title="t", logline="l").generated_by == "llm"


def test_degradation_is_surfaced_on_the_job():
    """It must reach both the progress stream (so the user sees it while
    waiting) and the result (so the UI can explain the finished video)."""
    import inspect

    import pipelines.idea2video as mod

    source = inspect.getsource(mod.Idea2VideoPipeline.continue_from_script)
    assert 'generated_by", "llm") == "template"' in source
    assert "script_degraded" in source
    assert "will not follow your idea closely" in source


@pytest.mark.asyncio
async def test_degraded_flag_reaches_the_result(monkeypatch, tmp_path):
    import pipelines.idea2video as mod

    pipeline = mod.Idea2VideoPipeline(api_key="", demo=True)
    monkeypatch.setattr(
        pipeline, "_lock_character_portraits", _async_return({})
    )
    monkeypatch.setattr(
        pipeline.script2video, "run", _async_return({"path": None, "shots": []})
    )

    template = await ScreenwriterAgent(demo=True).write_script("x", num_scenes=2)
    result = await pipeline.continue_from_script(
        template, working_dir=str(tmp_path / "job")
    )
    assert result["script_degraded"] is True


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner
