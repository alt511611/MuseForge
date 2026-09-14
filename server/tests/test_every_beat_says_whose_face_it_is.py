"""The man at the table was forty-five for twenty-seven seconds, then seventy.

Job 921ee1df-40d, delivered: three takes on fal-ai/kling-video/v3/standard,
two elements attached to every one of them, no 422, nothing in the log to say
anything had gone wrong. Its third scene was planned as two beats -- 9s and
3s -- so the second beat opened 27.083s into a 30.2s film, and the cut
measured in the delivered master lands at 27.125s. That is where the man
across the card table stops being the man across the card table and becomes
somebody forty years older. Scene two breaks the same way on its own second
beat, at 11.04s, where the dealer becomes a different woman; by the end of
the film she has been four.

The request was not missing the faces. `elements` carried both portraits on
all three takes. What the request never did was NAME them anywhere except in
the cast clause, and the cast clause is written on the first beat only -- so
from the second beat onward the endpoint held two reference pictures it had
been given no reason to use, and drew the scene's people out of the prose
instead. Prose produces somebody who matches the description and is not the
same person twice; interfaces/character has said so since the per-shot path
hit it, and the per-shot path answered it by restating identity in every
frame prompt. The take path restated it once.

So every beat cites. The dictionary -- which token is whom, what they are
wearing -- is still read once at the top, because that is what a dictionary
is for; the citation is what has to be on each beat, and it is roughly five
characters long.
"""

import re

from interfaces.scene_take import Beat, Element, SceneTake

_VERA = Element(name="Vera Kessler", images=("vera.png",))
_SILAS = Element(name="Silas Voss", images=("silas.png",))


def _take(beats, elements=(_VERA, _SILAS), limit=512):
    return SceneTake(
        seconds=sum(b.seconds for b in beats),
        beats=tuple(beats),
        elements=tuple(elements),
        max_prompt_chars=limit,
    )


def test_the_second_beat_is_not_handed_a_stranger():
    """The beat that delivered a seventy-year-old now says whose face it is."""
    take = _take(
        [
            Beat(9, "Vera Kessler deals across the baize.", shot_type="wide"),
            Beat(3, "Silas Voss lifts his eyes to her.", shot_type="close-up"),
        ]
    )

    prompts = [entry["prompt"] for entry in take.multi_prompt()]

    assert "@Element2" in prompts[1], (
        "the uncited beat is the one that changed the man at the table"
    )
    assert "Silas Voss lifts" not in prompts[1], "the name gave way to the token"


def test_every_beat_carries_a_binding():
    """Not just the second one -- a take is only as locked as its loosest cut."""
    take = _take(
        [
            Beat(3, "Vera Kessler fans the deck.", shot_type="wide"),
            Beat(4, "Vera watches Silas over the cards.", shot_type="medium"),
            Beat(3, "Silas Voss taps the felt twice.", shot_type="close-up"),
        ]
    )

    for index, entry in enumerate(take.multi_prompt()):
        assert "@Element" in entry["prompt"], f"beat {index} cites nobody"


def test_the_first_name_is_the_one_a_beat_actually_writes():
    """A storyboard writes "Vera" far more often than "Vera Kessler"."""
    take = _take([Beat(4, "Vera slides the chips forward.", shot_type="medium")])

    prompt = take.multi_prompt()[0]["prompt"]

    assert "@Element1 slides the chips forward" in prompt
    # The full name still survives where the cast clause states it.
    assert "@Element1 is Vera Kessler" in prompt


def test_the_longest_spelling_wins():
    """Otherwise "Vera Kessler" comes out as "@Element1 Kessler"."""
    take = _take([Beat(4, "Vera Kessler counts the pot.", shot_type="medium")])

    description = take.cited(take.beats[0]).description

    assert description == "@Element1 counts the pot."


def test_a_possessive_survives_the_citation():
    take = _take([Beat(4, "Vera's gloved hand covers the ace.", shot_type="insert")])

    assert take.cited(take.beats[0]).description == (
        "@Element1's gloved hand covers the ace."
    )


def test_a_name_that_is_also_a_word_is_left_alone():
    """A character called Will costs the prompt every "will" in it.

    Case-sensitivity is the whole defence: the screenwriter capitalises a
    name and does not capitalise a verb, so "Will deals" cites and "she will
    deal" does not. Without it this beat reads "she @Element1 deal", which is
    not a tighter prompt, it is one that has stopped being a sentence.
    """
    take = _take(
        [Beat(4, "Will steadies the deck; she will deal in a moment.")],
        elements=(Element(name="Will Hartley"),),
    )

    description = take.cited(take.beats[0]).description

    assert description.startswith("@Element1 steadies the deck")
    assert "she will deal in a moment" in description


#: Job 09414b97-a54's storyboard, verbatim -- one capital T, one lower case,
#: in a cast whose names are descriptions rather than names.
_GENERIC = "The Dealer deals cards across the felt toward the Man in the windowless room."


def test_a_cast_of_descriptions_is_still_a_cast():
    """"The Dealer" and "The Man" are what a screenwriter names a two-hander.

    And a screenwriter does not capitalise them consistently: the beat above
    wrote "The Dealer" and "the Man" in one sentence. Matched case-sensitively
    the man stayed prose, and prose is what redraws him.
    """
    take = _take(
        [Beat(4, _GENERIC)],
        elements=(Element(name="The Dealer"), Element(name="The Man")),
    )

    assert take.cited(take.beats[0]).description == (
        "@Element1 deals cards across the felt toward @Element2 in the "
        "windowless room."
    )


def test_an_article_in_a_name_never_becomes_the_name():
    """A cast named "dealer" and "the man" hands "the" to the second element.

    Measured before this was fixed, on the same beat: "deals cards across
    @Element2 felt toward @Element2 Man in @Element2 windowless room." Three
    citations, none of them a person, in a prompt that no longer parses.
    """
    take = _take(
        [Beat(4, _GENERIC)],
        elements=(Element(name="dealer"), Element(name="the man")),
    )

    description = take.cited(take.beats[0]).description

    assert "@Element2 felt" not in description
    assert description.count("@Element2") == 1, "the man is cited once: as the man"
    assert "@Element1 deals" in description, (
        "a lower-case cast name still cites where the prose capitalises it"
    )


def test_a_surname_two_characters_share_cites_neither():
    """Citing the wrong element holds one face where the script wrote two."""
    take = _take(
        [Beat(4, "Kessler looks at Kessler across the table.")],
        elements=(Element(name="Vera Kessler"), Element(name="Nadia Kessler")),
    )

    description = take.cited(take.beats[0]).description

    assert description == "@Element1. Kessler looks at Kessler across the table.", (
        "an ambiguous part is dropped, not guessed -- and the beat falls back "
        "to the anchor rather than citing a coin toss"
    )


def test_an_insert_belongs_to_the_person_the_scene_is_about():
    """Three seconds of a stranger's hand is what an uncited insert delivers."""
    take = _take([Beat(3, "A gloved hand slides one card face down.")])

    description = take.cited(take.beats[0]).description

    assert description.startswith("@Element1. "), "the anchor is the first element"


def test_the_name_behind_the_colon_is_speech_and_stays():
    """The endpoint SAYS what it is given.

    "Vera Kessler: Patience is a tell too, Vera." carries the same name twice
    and they are two different things. In front of the colon it says which
    element is talking. Behind it, a citation is a take that pronounces "at
    element one" out loud while the subtitle burned into the same frame reads
    "Vera".
    """
    take = _take(
        [
            Beat(
                4,
                "The two of them hold still over the cards.",
                shot_type="medium",
                dialogue=("Vera Kessler: Patience is a tell too, Vera.",),
            )
        ]
    )

    prompt = take.multi_prompt()[0]["prompt"]

    assert '@Element1 says: "Patience is a tell too, Vera."' in prompt


def test_a_take_with_no_elements_is_left_exactly_as_it_was():
    """Nothing to cite, nothing to change -- and no bare token prefix either."""
    take = _take([Beat(4, "Vera Kessler deals.", shot_type="wide")], elements=())

    assert take.multi_prompt()[0]["prompt"] == "wide. Vera Kessler deals."


def test_the_citation_is_inside_the_budget_it_was_measured_against():
    """A citation is longer than the name it replaces.

    Which is the mistake this module has already made once: the cast clause
    was prepended after the fitting, against a length that was about to
    change, and the endpoint answered 422 over eighteen characters.
    """
    long_description = (
        "Vera Kessler at frame-left under the hanging bulb, fanning cards and "
        "pushing chips forward, Silas Voss at frame-right behind stacked "
        "chips, fedora brim low, steepled fingers. Vera slides the chip stack "
        "forward and taps two fingers on the table's edge; Silas remains "
        "still, watching her hand as the room holds its breath."
    )
    take = _take(
        [Beat(4, long_description, shot_type="wide", dialogue=("Vera Kessler: Call.",))],
        limit=512,
    )

    for entry in take.multi_prompt():
        assert len(entry["prompt"]) <= 512


def test_a_shot_with_nothing_written_in_it_is_counted():
    """Dropping it is right. Dropping it silently is what delivered a 9s beat."""
    from interfaces.scene_take import plan_scene_take

    class _Shot:
        def __init__(self, visual, seconds):
            self.visual_desc = visual
            self.motion_desc = ""
            self.deliver_seconds = seconds
            self.shot_type = "medium"

    class _Backend:
        multishot = True
        max_beats = 5
        max_elements = 7
        max_prompt_chars = 512

        class duration:
            @staticmethod
            def send(wanted):
                return int(wanted)

    take = plan_scene_take(
        12,
        [_Shot("Vera deals.", 4), _Shot("", 4), _Shot("Silas folds.", 4)],
        _Backend(),
        elements=(_VERA, _SILAS),
    )

    assert take.beat_count == 2
    assert take.undescribed_shots == 1, (
        "the missing angle is otherwise only an arithmetic gap"
    )


def test_the_citation_never_runs_into_the_next_word():
    """\\b on both sides: "Verandah" is not Vera."""
    take = _take([Beat(4, "Vera crosses the verandah past Verax Holdings.")])

    description = take.cited(take.beats[0]).description

    assert "verandah" in description
    assert "Verax" in description
    assert len(re.findall(r"@Element1", description)) == 1
