"""Two stages that kept running for a film whose picture already spoke it.

`picture_carries_dialogue` is asked once and every soundtrack stage turns on
it. It was asked too late, and asked for too little.

TOO LATE. It sat below the casting. So job 6f857aa0-903 -- three scenes,
English, MUSEFORGE_VIDEO_PROVIDER=falai_multishot -- gender-matched its
ensemble to ElevenLabs ids, logged `Cast: mara voss=FGY2WhTYpPnrIDTdsKH5`,
spent a verify_cast round trip at the provider confirming that id, and wrote
it onto the result for the character library to inherit. One line later the
same job warned that the take would choose its own voices. Nothing in that
film ever spoke in FGY2WhTYpPnrIDTdsKH5, and the library would have recorded
it as the voice this drama gave her.

TOO LITTLE. With no TTS there is no recording to measure, so the second budget
-- the split idea2video itself calls "the one decision that cannot be revisited
later" -- was handed `speech_seconds=[0.0, 0.0, 0.0]` and read it as three
scenes with nothing to say. That job sized 8/10/12s on tension alone and then
asked interfaces/scene_take to fit real lines into the beats the guess had
bought. The lines were always there in the script; only the recording was
missing. scene_take already estimates from the text to decide which beat a
line falls in, so the budget now asks it the same question -- one formula,
used by the stage that sizes the scene and the stage that fills it.
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.scene_take import (  # noqa: E402
    WORDS_PER_SECOND,
    estimated_speech_seconds,
)
from interfaces.second_budget import distribute_budget  # noqa: E402

MARA = [
    "MARA: Dispatch, you seeing this?",
    "DISPATCH: Voss, step back from that container. That's not on any manifest.",
]


# --- the estimate itself ---------------------------------------------------


def test_a_scene_with_no_lines_speaks_for_no_seconds():
    assert estimated_speech_seconds([]) == 0.0


def test_the_speaker_s_name_is_not_something_anybody_says_out_loud():
    """"MARA:" is a script convention, and counting it pads every line."""
    assert estimated_speech_seconds(["MARA: run"]) == estimated_speech_seconds(["run"])


def test_a_two_word_line_is_still_a_breath():
    """At 2.5 words/sec "hm." is 0.4 seconds, which no actor has ever done."""
    assert estimated_speech_seconds(["MARA: hm."]) == 1.0


def test_a_longer_line_is_priced_at_the_rate_the_beats_are_built_on():
    line = "MARA: " + " ".join(["word"] * 10)

    assert estimated_speech_seconds([line]) == 10 / WORDS_PER_SECOND


def test_the_scene_is_the_sum_of_what_it_says():
    assert estimated_speech_seconds(MARA) == sum(
        estimated_speech_seconds([line]) for line in MARA
    )


def test_the_budget_and_the_beats_read_from_one_formula():
    """_spread_dialogue lays lines out end to end with the same arithmetic.

    Stated as a test because the two are in different modules and the whole
    point of exporting it was that they cannot answer differently.
    """
    from interfaces import scene_take

    source = inspect.getsource(scene_take._spread_dialogue)

    assert "_line_seconds(line)" in source
    assert "WORDS_PER_SECOND" not in source


# --- what the budget does with it ------------------------------------------


def test_a_scene_with_lines_is_no_longer_sized_as_if_it_had_none():
    """The delivered failure: three speaking scenes, split on tension alone."""
    tension = [3, 5, 8]
    blind = distribute_budget(tension, speech_seconds=[0.0, 0.0, 0.0])
    informed = distribute_budget(
        tension, speech_seconds=[estimated_speech_seconds(MARA), 0.0, 0.0]
    )

    assert blind != informed
    assert informed[0] > blind[0]


def test_the_total_is_still_the_total():
    """The estimate redistributes the budget; it may not grow it. The total is
    fixed before any credit is charged and nothing downstream may move it."""
    tension = [3, 5, 8]
    blind = distribute_budget(tension, speech_seconds=[0.0, 0.0, 0.0])
    informed = distribute_budget(
        tension, speech_seconds=[estimated_speech_seconds(MARA)] * 3
    )

    assert sum(informed) == sum(blind)


# --- the call sites --------------------------------------------------------


def _pipeline_source():
    import pipelines.idea2video as mod

    return inspect.getsource(mod.Idea2VideoPipeline.continue_from_script)


def test_the_question_is_asked_before_the_cast_is_built_not_after():
    """Order is the whole fix: below the cast it cannot stop the casting."""
    source = _pipeline_source()

    assert source.index("picture_speaks = ") < source.index("_make_voice_generator")


def test_a_speaking_picture_builds_no_voice_generator_to_cast_with():
    assert "if dialogue_requested and not picture_speaks" in _pipeline_source()


def test_a_speaking_picture_sizes_its_scenes_from_the_lines_it_will_say():
    source = _pipeline_source()

    assert "estimated_speech_seconds(_scene_dialogue(scene))" in source
    assert "if picture_speaks" in source
