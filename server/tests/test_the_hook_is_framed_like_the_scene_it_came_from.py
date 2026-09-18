"""The cold open, the quote, and two things that were decided by default.

The teaser at the head of a micro-drama is a COPY of the last seconds of the
climax -- the same footage, shown early. Where to point its crop is therefore
already known. It was not used: anchors are keyed by clip path, the teaser is
a new file, so the one part of a vertical export that most needs aiming was
the one part centre-cropped, while the identical footage later in the film was
aimed properly.

The quote's version of "decided by default" is worse, because it is decided
for everyone: /api/estimate reaches _scene_concurrency, which imported the
whole render stack to read one environment variable. An install missing an
optional render dependency answered the pricing page with a 500.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import pipelines.idea2video as pipeline  # noqa: E402
from interfaces.reframe import Anchor  # noqa: E402
from pipelines.idea2video import Idea2VideoPipeline  # noqa: E402


def _scene(clip_index, function, tension):
    return {
        "clip_index": clip_index,
        "script": {"dramatic_function": function, "tension": tension},
    }


@pytest.fixture
def hooked(monkeypatch, tmp_path):
    """A pipeline whose cold open builds without touching ffmpeg."""

    async def _fake_trim(source, output, seconds, from_head=True):
        open(output, "wb").write(b"clip")
        return output

    async def _no_card(*args, **kwargs):
        return None

    monkeypatch.setattr(pipeline, "trim_to_duration", _fake_trim)
    monkeypatch.setattr(Idea2VideoPipeline, "_build_title_card", _no_card)
    monkeypatch.setattr(pipeline.micro_drama, "is_cold_open_enabled", lambda: True)
    return Idea2VideoPipeline(api_key="k", demo=False)


@pytest.mark.asyncio
async def test_the_teaser_is_pointed_where_its_own_scene_is(hooked, tmp_path):
    climax_anchor = Anchor(x=0.72, y=0.4, confidence=0.9, reason="speaker")
    anchors = {"s1.mp4": climax_anchor}
    scenes = [_scene(0, "setup", 3), _scene(1, "climax", 10)]

    paths, _dialogue, _sfx = await hooked._with_cold_open(
        ["s0.mp4", "s1.mp4"],
        scenes,
        [],
        [],
        str(tmp_path),
        narrative_mode="micro_drama",
        anchors=anchors,
    )

    teaser = paths[0]
    assert teaser not in ("s0.mp4", "s1.mp4"), "the teaser is its own file"
    assert anchors[teaser] == climax_anchor


@pytest.mark.asyncio
async def test_a_hook_taken_from_a_scene_nobody_could_read_stays_centred(
    hooked, tmp_path
):
    """No anchor to inherit is not a reason to invent one."""
    anchors = {}
    scenes = [_scene(0, "climax", 10)]

    paths, _dialogue, _sfx = await hooked._with_cold_open(
        ["s0.mp4"],
        scenes,
        [],
        [],
        str(tmp_path),
        narrative_mode="micro_drama",
        anchors=anchors,
    )

    assert anchors == {}
    assert len(paths) == 2  # teaser + the scene


@pytest.mark.asyncio
async def test_a_caller_that_passes_no_anchors_still_gets_its_hook(hooked, tmp_path):
    paths, _dialogue, _sfx = await hooked._with_cold_open(
        ["s0.mp4"],
        [_scene(0, "climax", 10)],
        [],
        [],
        str(tmp_path),
        narrative_mode="micro_drama",
    )

    assert len(paths) == 2


def test_every_assembly_path_hands_the_hook_its_anchors():
    """The hook is rebuilt on a retake and a re-cut too, so a fix that only
    reached the first render would be a fix that disappears the moment the
    customer edits anything."""
    import inspect

    source = inspect.getsource(pipeline.Idea2VideoPipeline)
    # "scene_anchors=" is the assembly's own parameter and contains the same
    # substring, so it is subtracted rather than matched by accident.
    to_the_hook = source.count("anchors=scene_anchor_map") - source.count(
        "scene_anchors=scene_anchor_map"
    )

    assert source.count("scene_anchors=scene_anchor_map") == 3, "the assembly"
    assert to_the_hook == 3, "the cold open"


# ── the quote ────────────────────────────────────────────────────────────────

def test_the_quote_survives_a_render_stack_that_will_not_import(monkeypatch):
    """An estimate is arithmetic. It must not 500 because a video backend's
    optional dependency is missing on this box."""
    import builtins

    real_import = builtins.__import__

    def _refuse(name, *args, **kwargs):
        if name == "pipelines.script2video":
            raise ImportError("No module named 'fal_client'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _refuse)
    monkeypatch.delenv("MUSEFORGE_DYNAMIC_REFERENCE", raising=False)

    assert pipeline._scene_concurrency(5) >= 1


def test_the_chaining_flag_is_still_honoured_without_the_render_stack(monkeypatch):
    """Read straight from the environment, which is where it lives anyway --
    otherwise the fallback would quote a parallel render for a mode that is
    strictly sequential."""
    import builtins

    real_import = builtins.__import__

    def _refuse(name, *args, **kwargs):
        if name == "pipelines.script2video":
            raise ImportError("No module named 'fal_client'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _refuse)
    monkeypatch.setenv("MUSEFORGE_DYNAMIC_REFERENCE", "1")

    assert pipeline._scene_concurrency(5) == 1


# ── the cast that is only ever heard ─────────────────────────────────────────

def test_the_cast_is_read_once_not_once_per_character(monkeypatch):
    """It is a pure function of the script and the cast; calling it per
    character re-read every action line of every scene for each of them, and
    said its one decision once per character in the log."""
    calls = []
    real = pipeline._heard_but_never_seen

    def _counted(script, cast):
        calls.append(1)
        return real(script, cast)

    monkeypatch.setattr(pipeline, "_heard_but_never_seen", _counted)

    from interfaces.character import CharacterProfile, DramaScript

    script = DramaScript(
        title="The Tell",
        logline="a card room",
        mood="tense",
        scenes=["Mara deals. Yara watches. Denny's voice crackles over the radio."],
        characters=[
            CharacterProfile(name="Mara", description="dealer", role="protagonist"),
            CharacterProfile(name="Yara", description="player", role="antagonist"),
            CharacterProfile(name="Denny", description="a voice", role="supporting"),
        ],
        setting_location="basement card room",
        setting_time_of_day="night",
        setting_era="present day",
    )

    Idea2VideoPipeline(api_key="k", demo=True)._characters_from_script(script)

    assert len(calls) == 1
