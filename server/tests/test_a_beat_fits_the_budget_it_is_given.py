"""Eighteen characters cost a whole scene.

    'msg': 'Value error, Prompt must not exceed 512 characters.'
    'loc': ['body', 'multi_prompt', 0, 'prompt']

The beat was 530. Unlike the frame prompt's ladder -- where an overrun costs
a clause and the picture is merely poorer for it -- an overrun here is not a
degraded anything: the endpoint answers 422 and the take does not exist.

It was the first beat, and the first beat is the one carrying the cast
clause, which the CALLER used to prepend after the beat was built. So the
only budget anyone could have measured was measured against a string that was
about to get fifty characters longer.
"""

from interfaces.scene_take import (
    MIN_BEAT_DESCRIPTION,
    Beat,
    Element,
    SceneTake,
)

#: The beat the endpoint refused, verbatim.
_DESCRIPTION = (
    "Wide shot of the basement card room: Vera Kessler at frame-left under "
    "the hanging bulb, fanning cards and pushing chips forward, Silas Voss at "
    "frame-right behind stacked chips, fedora brim low, steepled fingers. "
    "Vera slides the chip stack forward and taps two fingers on the table's "
    "edge; Silas remains still, watching her hand."
)
_LINES = (
    "Vera Kessler: Call or fold, Mr. Voss.",
    "Silas Voss: Patience is a tell too, Vera.",
)


def _take(description=_DESCRIPTION, lines=_LINES, limit=512, second_beat=False):
    beats = [Beat(4, description, shot_type="wide", dialogue=lines)]
    if second_beat:
        beats.append(Beat(4, "Tight on Vera.", shot_type="close-up"))
    return SceneTake(
        seconds=4 * len(beats),
        beats=tuple(beats),
        elements=(Element(name="Vera Kessler"), Element(name="Silas Voss")),
        max_prompt_chars=limit,
    )


def test_the_beat_that_was_refused_now_fits():
    prompt = _take().multi_prompt()[0]["prompt"]

    assert len(prompt) <= 512
    assert "@Element1 is Vera Kessler" in prompt, "the cast clause never gives"
    for line in _LINES:
        _, _, said = line.partition(": ")
        assert said.rstrip(".") in prompt, (
            "a line cut out of the prompt is a line the take does not say, "
            "while the subtitle burned into the same frame still shows it"
        )


def test_the_cast_clause_is_counted_because_it_is_applied_here():
    """The caller cannot prepend it: by then the fitting has already happened."""
    with_cast = _take().multi_prompt()[0]["prompt"]
    solo = _take(second_beat=True).multi_prompt()[1]["prompt"]

    assert with_cast.startswith("@Element1")
    assert "@Element" not in solo, "said once, at the top of the take"


def test_the_speech_outlives_the_description():
    """The description has slack; the audio does not."""
    prompt = _take(description="X" * 900).multi_prompt()[0]["prompt"]

    assert len(prompt) <= 512
    assert "Call or fold" in prompt
    assert "Patience is a tell too" in prompt
    assert "X" * MIN_BEAT_DESCRIPTION in prompt, (
        "the shot still has to be described; a beat with no picture in it is "
        "a cut to nowhere"
    )


def test_speech_longer_than_the_budget_loses_whole_lines():
    """Half a sentence spoken aloud is worse than a sentence not spoken."""
    lines = tuple(f"Vera Kessler: {'word ' * 30}" for _ in range(4))

    prompt = _take(description="X" * 400, lines=lines).multi_prompt()[0]["prompt"]

    assert len(prompt) <= 512
    assert prompt.rstrip().endswith('"'), "no line is cut mid-sentence"


def test_an_unmeasured_backend_is_not_a_backend_with_a_zero_budget():
    """0 means nobody has measured this endpoint, which is where all of them
    started -- not "the prompt may be empty"."""
    prompt = _take(limit=0).multi_prompt()[0]["prompt"]

    assert _DESCRIPTION in prompt
    assert len(prompt) > 512


def test_the_declared_limit_travels_from_the_backend():
    from interfaces.scene_take import plan_scene_take
    from interfaces.video_backend import BACKENDS

    backend = next(b for b in BACKENDS.values() if b.multishot)

    class _Shot:
        visual_desc = _DESCRIPTION
        motion_desc = ""
        shot_type = "wide"
        deliver_seconds = 8

    take = plan_scene_take(8, [_Shot()], backend, dialogue=list(_LINES))

    assert take is not None
    assert take.max_prompt_chars == backend.max_prompt_chars == 512
    assert all(len(beat["prompt"]) <= 512 for beat in take.multi_prompt())
