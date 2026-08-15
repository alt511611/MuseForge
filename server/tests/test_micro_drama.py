"""The micro-drama shape: open on the shock, end on the question.

A film and a vertical episode are not the same object at two lengths. The
pipeline's default curve — rising to a climax, settling into a resolution — is
the wrong shape for a feed, where the first two seconds decide whether the
rest is watched and the last frame is the only reason anyone comes back.

Three places have to agree about that, and this file holds them to it: the
screenwriter's prompt, the deterministic template behind it, and the cut
itself (the cold open, which is assembled from footage the climax already paid
for).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces import micro_drama  # noqa: E402
from pipelines.idea2video import Idea2VideoPipeline  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_NARRATIVE_MODE", raising=False)
    monkeypatch.delenv("MUSEFORGE_COLD_OPEN", raising=False)


# --- the mode ----------------------------------------------------------


def test_cinematic_is_the_default():
    """Existing deployments keep the product they already have."""
    assert micro_drama.resolve_mode() == micro_drama.CINEMATIC
    assert micro_drama.resolve_mode("") == micro_drama.CINEMATIC
    assert micro_drama.is_micro_drama() is False


def test_the_caller_outranks_the_environment(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_NARRATIVE_MODE", "micro_drama")
    assert micro_drama.resolve_mode() == micro_drama.MICRO_DRAMA
    assert micro_drama.resolve_mode("cinematic") == micro_drama.CINEMATIC


def test_an_unknown_mode_is_not_honoured():
    assert micro_drama.resolve_mode("interpretive_dance") == micro_drama.CINEMATIC


def test_the_card_speaks_the_dramas_language():
    assert micro_drama.card_text("tr") == "DAHA ÖNCE"
    assert micro_drama.card_text("en") == "EARLIER"
    # A card in the wrong language still says "time moved"; no card at all
    # makes the teaser read as a continuity error.
    assert micro_drama.card_text("xx") == "EARLIER"


def test_the_card_does_not_invent_a_number():
    """"12 HOURS EARLIER" is the convention and a claim this pipeline cannot
    make -- nothing tells it how much time the story spans."""
    for text in micro_drama._CARD_TEXT.values():
        assert not any(ch.isdigit() for ch in text)


# --- the prompt --------------------------------------------------------


def test_the_clause_is_absent_in_cinematic_mode():
    prompt = ScreenwriterAgent(api_key="")._system_prompt(narrative_mode="cinematic")
    assert "MICRO-DRAMA FORM" not in prompt


def test_the_clause_comes_last_so_it_can_override():
    """It contradicts the base prompt's rising curve and its demand for a
    resolution; a model weighs a late override against what came before."""
    prompt = ScreenwriterAgent(api_key="")._system_prompt(
        language="tr", require_dialogue=True, narrative_mode="micro_drama"
    )
    assert prompt.rstrip().endswith(micro_drama.SCREENWRITER_CLAUSE.rstrip())
    assert "SPOKEN DRAMA" in prompt  # the dialogue clause is still there
    assert "LANGUAGE." in prompt


def test_the_clause_says_the_three_things_that_define_the_form():
    clause = micro_drama.SCREENWRITER_CLAUSE
    assert "OPEN ON THE WORST MOMENT" in clause
    assert "NO RESOLUTION" in clause
    assert "cliffhanger" in clause


# --- the template behind it --------------------------------------------


@pytest.mark.asyncio
async def test_the_template_writes_the_micro_drama_curve():
    """A key-less run must not quietly produce a three-act film when the
    caller asked for the other shape."""
    # demo=True is the deterministic template path: no keys, no network.
    agent = ScreenwriterAgent(api_key="", demo=True)
    script = await agent.write_script(
        "iki kardes bir mirasi paylasamaz", num_scenes=4, narrative_mode="micro_drama"
    )
    functions = [s.dramatic_function for s in script.scenes]
    tensions = [s.tension for s in script.scenes]

    assert "resolution" not in functions, functions
    assert functions[-1] == "climax"
    # Opens hard, falls, then climbs -- the opposite of the cinematic ramp.
    assert tensions[0] >= 8
    assert tensions[1] < tensions[0]
    assert tensions[-1] == max(tensions)


@pytest.mark.asyncio
async def test_the_cinematic_template_is_untouched():
    agent = ScreenwriterAgent(api_key="", demo=True)
    script = await agent.write_script("a quiet reconciliation", num_scenes=4)
    functions = [s.dramatic_function for s in script.scenes]
    assert functions[0] == "setup"
    assert functions[-1] == "resolution"


# --- the cold open -----------------------------------------------------


def _scene(index, function, tension=5, clip_index=None):
    return {
        "index": index,
        "clip_index": index if clip_index is None else clip_index,
        "script": {
            "action": "something happens",
            "dramatic_function": function,
            "tension": tension,
        },
        "shots": [],
    }


def test_prepending_the_hook_moves_every_timed_thing_with_it():
    """The teaser goes in FRONT of scene 0, and every piece of timed audio is
    addressed by its position in that list. Without the shift the drama's
    first line plays over the teaser and every line after it lands a scene
    early."""
    shifted = Idea2VideoPipeline.shift_track_scenes(
        [{"scene_index": 0, "line": "ilk"}, {"scene_index": 2, "line": "son"}], 2
    )
    assert [t["scene_index"] for t in shifted] == [2, 4]
    # ...and the rest of the track is untouched.
    assert shifted[0]["line"] == "ilk"


def test_no_shift_is_a_no_op():
    tracks = [{"scene_index": 1}]
    assert Idea2VideoPipeline.shift_track_scenes(tracks, 0) == tracks
    assert Idea2VideoPipeline.shift_track_scenes(None, 3) == []


@pytest.mark.asyncio
async def test_the_teaser_comes_from_the_climax(tmp_path, monkeypatch):
    """The hook is the climax shown early -- that is what a flash-forward is,
    and it is why this costs nothing."""
    import pipelines.idea2video as pipeline

    captured = {}

    async def _fake_trim(source, output, seconds, from_head=True):
        captured["source"] = source
        captured["seconds"] = seconds
        open(output, "wb").write(b"clip")
        return output

    monkeypatch.setattr(pipeline, "trim_to_duration", _fake_trim)
    monkeypatch.setattr(
        Idea2VideoPipeline, "_build_title_card", lambda *a, **k: _none()
    )

    async def _none():
        return None

    scenes = [
        _scene(0, "setup", 3),
        _scene(1, "climax", 10),
        _scene(2, "rising_action", 6),
    ]
    paths = ["s0.mp4", "s1.mp4", "s2.mp4"]
    clips = await Idea2VideoPipeline(api_key="k", demo=False)._build_cold_open(
        scenes, paths, str(tmp_path)
    )

    assert captured["source"] == "s1.mp4"
    assert captured["seconds"] == micro_drama.COLD_OPEN_SECONDS
    assert len(clips) == 1


@pytest.mark.asyncio
async def test_a_scene_that_could_not_be_trimmed_is_not_used(tmp_path, monkeypatch):
    """An untrimmed "teaser" is the whole scene played twice, which is not a
    hook -- it is a repeat."""
    import pipelines.idea2video as pipeline

    async def _no_trim(source, output, seconds, from_head=True):
        return source

    monkeypatch.setattr(pipeline, "trim_to_duration", _no_trim)
    clips = await Idea2VideoPipeline(api_key="k", demo=False)._build_cold_open(
        [_scene(0, "climax", 10)], ["s0.mp4"], str(tmp_path)
    )
    assert clips == []


@pytest.mark.asyncio
async def test_a_script_with_no_climax_still_finds_its_peak(tmp_path, monkeypatch):
    """Legacy scripts declare no dramatic_function; the most tense scene that
    produced a clip is the honest stand-in."""
    import pipelines.idea2video as pipeline

    captured = {}

    async def _fake_trim(source, output, seconds, from_head=True):
        captured["source"] = source
        open(output, "wb").write(b"clip")
        return output

    async def _no_card(*a, **k):
        return None

    monkeypatch.setattr(pipeline, "trim_to_duration", _fake_trim)
    monkeypatch.setattr(Idea2VideoPipeline, "_build_title_card", _no_card)

    scenes = [_scene(0, "", 4), _scene(1, "", 9), _scene(2, "", 6)]
    await Idea2VideoPipeline(api_key="k", demo=False)._build_cold_open(
        scenes, ["s0.mp4", "s1.mp4", "s2.mp4"], str(tmp_path)
    )
    assert captured["source"] == "s1.mp4"


@pytest.mark.asyncio
async def test_a_drama_with_no_clips_gets_no_hook(tmp_path):
    assert (
        await Idea2VideoPipeline(api_key="k", demo=False)._build_cold_open(
            [], [], str(tmp_path)
        )
        == []
    )


# --- the hook survives editing ------------------------------------------
#
# A derived clip that only the FIRST assembly knows about is a feature that
# disappears the moment the customer edits anything -- and silently, because
# nothing in the product ever claimed it was there.


@pytest.fixture
def _micro(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_NARRATIVE_MODE", "micro_drama")


@pytest.mark.asyncio
async def test_the_hook_is_rebuilt_for_every_assembly_path(tmp_path, monkeypatch, _micro):
    import pipelines.idea2video as pipeline

    async def _fake_trim(source, output, seconds, from_head=True):
        open(output, "wb").write(b"clip")
        return output

    async def _no_card(*a, **k):
        return None

    monkeypatch.setattr(pipeline, "trim_to_duration", _fake_trim)
    monkeypatch.setattr(Idea2VideoPipeline, "_build_title_card", _no_card)

    paths, dialogue, sfx = await Idea2VideoPipeline(
        api_key="k", demo=False
    )._with_cold_open(
        ["s0.mp4", "s1.mp4"],
        [_scene(0, "setup", 4), _scene(1, "climax", 10)],
        [{"scene_index": 1, "line": "son"}],
        [{"scene_index": 0, "audio_url": "bed0.mp3"}],
        str(tmp_path),
        narrative_mode="micro_drama",
    )

    assert len(paths) == 3  # teaser + the two scenes
    # ...and everything timed moved with it, or the first line would play
    # over the teaser.
    assert dialogue[0]["scene_index"] == 2
    assert sfx[0]["scene_index"] == 1


@pytest.mark.asyncio
async def test_a_cinematic_drama_is_left_exactly_as_it_was(tmp_path):
    paths, dialogue, sfx = await Idea2VideoPipeline(
        api_key="k", demo=False
    )._with_cold_open(
        ["s0.mp4"],
        [_scene(0, "climax", 10)],
        [{"scene_index": 0}],
        [{"scene_index": 0}],
        str(tmp_path),
        narrative_mode="cinematic",
    )
    assert paths == ["s0.mp4"]
    assert dialogue[0]["scene_index"] == 0
    assert sfx[0]["scene_index"] == 0


@pytest.mark.asyncio
async def test_the_hook_follows_the_story_not_the_file(tmp_path, monkeypatch, _micro):
    """A re-cut may have reordered the scenes, so the teaser must come from
    the climax as it stands NOW -- not from wherever it came from last time."""
    import pipelines.idea2video as pipeline

    captured = {}

    async def _fake_trim(source, output, seconds, from_head=True):
        captured["source"] = source
        open(output, "wb").write(b"clip")
        return output

    async def _no_card(*a, **k):
        return None

    monkeypatch.setattr(pipeline, "trim_to_duration", _fake_trim)
    monkeypatch.setattr(Idea2VideoPipeline, "_build_title_card", _no_card)

    # The climax now sits FIRST in the cut, at clip position 0.
    await Idea2VideoPipeline(api_key="k", demo=False)._with_cold_open(
        ["reordered_climax.mp4", "reordered_setup.mp4"],
        [_scene(0, "climax", 10), _scene(1, "setup", 4)],
        [],
        [],
        str(tmp_path),
        narrative_mode="micro_drama",
    )
    assert captured["source"] == "reordered_climax.mp4"


def test_foley_is_kept_for_re_edits():
    """The beds are paid for once. A re-cut that dropped them would deliver a
    quieter film than the one the customer already has, with no way back."""
    import inspect

    # continue_from_script is where the render state is written; run() is a
    # thin wrapper over it.
    source = inspect.getsource(Idea2VideoPipeline.continue_from_script)
    assert '"sfx_tracks": sfx_tracks' in source, "not recorded for later edits"

    recut = inspect.getsource(Idea2VideoPipeline.apply_timeline_edit)
    assert 'state.get("sfx_tracks")' in recut, "re-cut drops the foley"
    retake = inspect.getsource(Idea2VideoPipeline._rerender_scenes)
    assert 'state.get("sfx_tracks")' in retake, "retake drops the foley"
