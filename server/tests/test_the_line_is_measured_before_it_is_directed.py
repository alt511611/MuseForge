"""A shot cannot be told it is after the last word by a pipeline that has
not said the words yet.

shots_the_line_reaches decides which angles of a covered scene are still
under the dialogue when they open. It had only a word count to go on, because
the speech was made AFTER every scene had rendered -- and a word count has to
assume the slowest delivery anybody might give the line. On the second
delivered job that assumption was four seconds long:

    scene 2   12.08s of picture, cut 5 + 7
    line      4.96s, as the voice provider measured it
    estimate  ~9s, so the second angle kept the speaking direction
    log       "the remaining 7.12s of the take was rejoined behind it"

The second angle opens 40 milliseconds after the last word and is silent from
its first frame to its last.

The speech is now made first -- it needs nothing but the script, and it is
seconds of work against minutes of video -- so the answer is measured. A
measurement needs no margin.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.shot import StoryboardShot  # noqa: E402
from interfaces.shot_plan import shots_the_line_reaches  # noqa: E402
from pipelines.idea2video import spoken_seconds  # noqa: E402


def _shot(seconds):
    return StoryboardShot(
        idx=0,
        visual_desc="Yara at the container door",
        motion_desc="she speaks",
        duration_seconds=seconds,
    )


#: The delivered scene, and enough words that the estimate overshoots it.
DELIVERED = [_shot(5), _shot(7)]
DELIVERED_WORDS = "YARA: Oh god -- CONTROL: Yara, the grid -- YARA: Just -- Yara?"


# ── the measurement ─────────────────────────────────────────────────────────


def test_the_delivered_scene_the_estimate_could_not_see():
    """Same shots, same words, and the only new thing is the truth."""
    assert shots_the_line_reaches(DELIVERED, DELIVERED_WORDS) == [True, True]
    assert shots_the_line_reaches(
        DELIVERED, DELIVERED_WORDS, line_seconds=4.96
    ) == [True, False]


def test_a_measurement_needs_no_margin():
    """The cut lands 40ms after the last word. Any hedge at all puts the
    second angle back to talking, which is what the estimate's margin did."""
    assert shots_the_line_reaches(DELIVERED, "x y", line_seconds=4.99)[1] is False
    assert shots_the_line_reaches(DELIVERED, "x y", line_seconds=5.01)[1] is True


def test_a_line_that_really_does_span_the_cut_still_speaks():
    """Scene 1 of the same job: 10s of picture cut 4 + 6, and a 6.64s line
    that genuinely runs across the join."""
    assert shots_the_line_reaches(
        [_shot(4), _shot(6)], DELIVERED_WORDS, line_seconds=6.64
    ) == [True, True]


@pytest.mark.parametrize("measured", [None, 0, 0.0, -1.0])
def test_no_measurement_leaves_the_estimate_exactly_where_it_was(measured):
    """Every path without a voice -- silent dramas, a failed provider, the
    MuAPI path before it measured anything -- keeps the old behaviour."""
    assert shots_the_line_reaches(
        DELIVERED, DELIVERED_WORDS, line_seconds=measured
    ) == [True, True]


def test_a_single_angle_scene_is_still_untouched():
    assert shots_the_line_reaches([_shot(12)], DELIVERED_WORDS, line_seconds=1.0) == [True]


# ── where the last word falls ───────────────────────────────────────────────


def test_the_gap_after_the_last_line_is_not_speech():
    """_scene_speech_lengths leaves a caption gap hanging off the end, which
    is right for reserving room and wrong by exactly the margin that decides
    this cut: 4.96 + 0.2 is 5.16, and the angle opens at 5.00."""
    assert spoken_seconds([{"line": "Oh god.", "duration_seconds": 4.96}]) == 4.96


def test_lines_are_laid_out_with_the_gap_between_them():
    two = spoken_seconds(
        [
            {"line": "One.", "duration_seconds": 1.0},
            {"line": "Two.", "duration_seconds": 2.0},
        ]
    )
    assert two == pytest.approx(3.2)


def test_a_provider_that_measured_itself_is_believed():
    """ElevenLabs returns per-line timings inside the scene's own audio, so
    its last line's end IS the last word -- no accumulation, no gaps."""
    assert spoken_seconds(
        [
            {"line": "One.", "start_seconds": 0.0, "end_seconds": 1.4},
            {"line": "Two.", "start_seconds": 1.8, "end_seconds": 4.96},
        ]
    ) == 4.96


@pytest.mark.parametrize(
    "tracks",
    [
        None,
        [],
        [{"line": "  "}],
        [{"line": "Heard nowhere.", "caption_only": True, "duration_seconds": 3.0}],
    ],
)
def test_nothing_spoken_measures_nothing(tracks):
    assert spoken_seconds(tracks) is None


# ── the wiring ──────────────────────────────────────────────────────────────


def _script(*scenes):
    from interfaces.character import DramaScript

    return DramaScript(
        title="T",
        logline="L",
        scenes=list(scenes),
        characters=[{"name": "Yara", "description": "a dock worker"}],
    )


def _scene(line):
    return {
        "action": "Yara at the container.",
        "dialogue": [{"character": "Yara", "line": line}],
    }


async def _run_pipeline(tmp_path, monkeypatch, voice, scenes):
    """Drive the pipeline far enough to see what each scene was told."""
    from unittest.mock import AsyncMock

    from pipelines import idea2video as pipeline_mod

    monkeypatch.setenv("MUSEFORGE_DIALOGUE_ENABLED", "1")
    seen = []

    async def _fake_run(*args, **kwargs):
        seen.append(kwargs.get("scene_line_seconds"))
        return {"path": "scene.mp4", "shots": []}

    pipeline = pipeline_mod.Idea2VideoPipeline("test-key")
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline._lock_location_plate = AsyncMock(return_value=None)
    pipeline.script2video.run = _fake_run
    pipeline._assemble_final_drama = AsyncMock(return_value=str(tmp_path / "out.mp4"))
    monkeypatch.setattr(pipeline_mod, "_make_voice_generator", lambda *a, **kw: voice)

    await pipeline.continue_from_script(
        _script(*scenes),
        working_dir=str(tmp_path / "job"),
        dialogue_enabled=True,
    )
    return seen


class _Voice:
    """A voice provider that reports the lengths it was built with."""

    def __init__(self, *lengths):
        self.lengths = list(lengths)
        self.calls = 0

    def lock_voices(self, voices):
        pass

    def cast_characters(self, characters):
        return {c.name.casefold(): "v" for c in characters}

    async def generate_scene_dialogue(self, lines, **kwargs):
        seconds = self.lengths[self.calls] if self.calls < len(self.lengths) else 1.0
        self.calls += 1
        if seconds is None:
            raise RuntimeError("the provider fell over")
        return [
            {
                "line": str(getattr(lines[0], "line", None) or lines[0]["line"]),
                "audio_url": "https://cdn/line.mp3",
                "duration_seconds": seconds,
            }
        ]


@pytest.mark.asyncio
async def test_the_render_is_handed_the_measured_line(tmp_path, monkeypatch):
    """The whole point of the reordering: if the speech were still made after
    the render, this would be None."""
    voice = _Voice(4.96)
    seen = await _run_pipeline(tmp_path, monkeypatch, voice, [_scene("Oh god.")])
    assert seen == [pytest.approx(4.96)]


@pytest.mark.asyncio
async def test_each_scene_is_spoken_exactly_once(tmp_path, monkeypatch):
    """Moving the generation earlier must not leave a second set behind it --
    that would be every line paid for twice."""
    voice = _Voice(2.0, 3.0)
    await _run_pipeline(
        tmp_path, monkeypatch, voice, [_scene("One."), _scene("Two.")]
    )
    assert voice.calls == 2


@pytest.mark.asyncio
async def test_a_line_that_overran_pushes_the_next_scene_s_word_later(
    tmp_path, monkeypatch
):
    """Speech that outruns its own scene plays over the next one
    (plan_scene_speech_anchors), so the next scene's last word falls later
    than its own speech is long. A shot told otherwise would be directed
    silent over dialogue."""
    from interfaces.second_budget import distribute_budget

    first_scene_seconds = distribute_budget([5, 5])[0]
    overrun = first_scene_seconds + 4.0
    voice = _Voice(overrun, 2.0)
    seen = await _run_pipeline(
        tmp_path, monkeypatch, voice, [_scene("A long one."), _scene("Short.")]
    )
    assert seen[1] > 2.0, "the overrun from scene 1 was not carried forward"


@pytest.mark.asyncio
async def test_a_voice_that_fell_over_leaves_the_estimate_in_charge(
    tmp_path, monkeypatch
):
    """Fail-open, like every stage that decorates rather than delivers: no
    measurement means the word count, not a crash and not a silent scene."""
    voice = _Voice(None)
    seen = await _run_pipeline(tmp_path, monkeypatch, voice, [_scene("Oh god.")])
    assert seen == [None]
