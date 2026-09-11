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


def test_the_budget_is_counted_the_way_the_wire_counts_it():
    """510 characters were refused by a 512-character limit.

        'msg': 'multiPrompt[0].prompt: size must be between 0 and 512'

    The prompt carried four double quotes around its spoken lines. JSON
    escapes each of them, so what reached the validator was 514. A budget
    measured in `len` cannot see that, and the take it lets through does not
    exist.
    """
    from interfaces.scene_take import wire_length

    assert wire_length('say "hello"') == len('say "hello"') + 2
    assert wire_length("plain") == 5
    assert wire_length("") == 0


def test_the_refused_beat_measured_on_the_wire_now_fits():
    from interfaces.scene_take import PROMPT_BUDGET_RESERVE, wire_length

    description = (
        "Medium shot at the green felt table: Vera sits frame-left in her "
        "charcoal vest, Silas frame-right under his fedora, cigarette smoke "
        "curling; the untouched chip stack sits between them beneath the "
        "hanging bulb's harsh light, venetian-blind shadows striping both "
        "faces. Vera's fingers twitch toward her pinky."
    )
    lines = (
        "Vera: You're playing careless hands tonight, Silas.",
        "Silas: Maybe I already know what's coming.",
    )

    prompt = _take(description=description, lines=lines).multi_prompt()[0]["prompt"]

    assert wire_length(prompt) <= 512 - PROMPT_BUDGET_RESERVE
    assert "You're playing careless hands tonight" in prompt
    assert "Maybe I already know what's coming" in prompt


def test_a_beat_measured_under_the_budget_was_refused_by_it_anyway():
    """Three characters of margin is not margin; it is a coin toss.

        'msg': 'multiPrompt[0].prompt: size must be between 0 and 512'

    Job 49512158's opening beat. It measured 501 by `len` and 503 by
    wire_length, against an effective budget of 504 -- so the fitting never
    fired, the prompt went out exactly as the storyboard wrote it, and the
    endpoint refused it anyway. Two double quotes cannot carry 501 to 512,
    which is the explanation wire_length was built on, so the rule is
    something else and this pipeline cannot see what.

    What it can do is stop trying to land on a number it cannot measure. The
    same beat is now fitted rather than waved through, and the two things a
    beat may not lose survive the fitting: the cast clause and the line.
    """
    from interfaces.scene_take import PROMPT_BUDGET_RESERVE, wire_length

    description = (
        "Wide shot of the secondhand bookshop at dusk: Vivian Reyes stands "
        "behind the wooden counter as Daniel faces her, tote bag strap in "
        "hand, dusk light spilling through the open glass door onto the "
        "counter where the cream envelope has just slid free. The envelope "
        "tumbles from the paperback's pages and comes to rest on the counter "
        "as Daniel shifts."
    )
    lines = ("Daniel: Sorry, I dog-eared a page near the end.",)

    take = SceneTake(
        seconds=3,
        beats=(Beat(3, description, shot_type="wide", dialogue=lines),),
        elements=(Element(name="Vivian Reyes"), Element(name="Daniel")),
        max_prompt_chars=512,
    )
    prompt = take.multi_prompt()[0]["prompt"]

    #: What went out and came back 422, measured the way this module measures.
    refused_at = 503

    assert wire_length(prompt) < refused_at, (
        "this exact beat measured 503 against a budget of 504, was waved "
        "through untouched, and was refused; the budget it passed is the "
        "thing under test, so the number it has to beat is absolute"
    )
    assert wire_length(prompt) <= 512 - PROMPT_BUDGET_RESERVE
    assert prompt.startswith("@Element1 is Vivian Reyes"), "the cast clause never gives"
    assert "Sorry, I dog-eared a page near the end" in prompt, (
        "the line is the audio; a beat that does not carry it is a beat the "
        "take does not say"
    )
    assert len(description) > len(prompt) - 200, "and the shot is still described"


def test_the_reserve_is_wide_enough_to_outlive_being_wrong_again():
    """The margin is the point, so it is the thing worth asserting.

    Every candidate explanation of the three refusals lands at or under
    thirty characters above `len`. A reserve equal to the largest of them
    would be another guess at a rule; a reserve that clears it by a factor
    survives the next one being different too.
    """
    from interfaces.scene_take import MIN_BEAT_DESCRIPTION, PROMPT_BUDGET_RESERVE

    assert PROMPT_BUDGET_RESERVE >= 60, (
        "a reserve under thirty has already been refused twice"
    )
    assert 512 - PROMPT_BUDGET_RESERVE > MIN_BEAT_DESCRIPTION * 3, (
        "and a margin that eats the description is not a margin either"
    )


def test_a_cut_description_still_ends_on_a_sentence():
    """A shorter description of the shot, not a sentence that gives up.

    The widened reserve means the fitting now fires on most beats rather than
    on the rare overrunning one, so what the cut READS like stopped being a
    detail. Measured on the first beat it ran against: "The envelope tumbles
    from the paperback's." -- a clause that stops before it says anything.
    """
    from interfaces.scene_take import _trim

    assert _trim("The envelope tumbles from the paperback's pages", 40) == (
        "The envelope tumbles."
    )
    # Two dangling words in a row both go; the first real word ends it.
    assert _trim("Vera crosses to the window and the", 30) == (
        "Vera crosses to the window."
    )
    # A word that can end a sentence is kept, even a short one.
    assert _trim("Silas watches her hand carefully", 26) == "Silas watches her hand."
