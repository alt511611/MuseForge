"""The element binds her face; nothing in the request bound her clothes.

Delivered drama 10e143bb -- an old bookseller who finds a letter she wrote at
nineteen and walks to the address on it -- ran as three takes of 8, 10 and 12
seconds. Read frame by frame, the lead changes at 18.083s, which is the seam
between the second take and the third:

    0.0 - 18.083s   cream wool cardigan, bej skirt, tan shoulder bag,
                    hair in a bun, a yellow envelope in her hand
    18.083 - 30.125 brown jacket, dark top, long chain necklace,
                    hair loose to the shoulder, a small white card

Her face survives it well enough to read as the same casting, and the pearl
earring survives it exactly -- the element lock is working. What no part of
the take request ever said was what she had on. The pipeline has known since
interfaces/character that "the identity reference image binds a face, not an
outfit, so wardrobe has to be restated as text in every frame prompt or the
costume changes between scenes even when the face holds". The take prompt was
the one prompt never given that treatment, and it is the prompt that now
drives twelve seconds of picture instead of one still.
"""

from interfaces.scene_take import (
    MAX_CAST_CLAUSE_CHARS,
    Beat,
    Element,
    SceneTake,
    wire_length,
)

ELENA = Element(
    name="Elena Vasquez",
    images=("elena.png",),
    wardrobe="a cream wool cardigan over a pale grey dress, tan leather shoulder bag",
)
TOMAS = Element(
    name="Tomas Rehn",
    images=("tomas.png",),
    wardrobe="a dark green wool jacket over an open-collar shirt",
)


def _take(*elements, description="the bookseller reads the letter she wrote"):
    return SceneTake(
        seconds=12,
        beats=(Beat(seconds=12, description=description),),
        elements=elements,
        max_prompt_chars=512,
    )


def test_the_cast_clause_says_what_they_are_wearing():
    clause = _take(ELENA).cast_clause()

    assert "@Element1 is Elena Vasquez" in clause
    assert "cream wool cardigan" in clause, (
        "a take told only who she is will dress her again at the next seam"
    )


def test_the_clothes_are_told_to_hold_across_the_cuts():
    """The cuts inside a take are the seams the costume drifts at.

    Said once, on the first beat, because the beats of a take are cuts inside
    ONE generation -- a sentence there is read over all of them, and per beat
    it would cost this much of every budget in the scene.
    """
    clause = _take(ELENA).cast_clause()

    assert "hold across every cut" in clause
    take = _take(ELENA, TOMAS)
    assert take.multi_prompt()[0]["prompt"].startswith("@Element1 is Elena Vasquez")


def test_a_crowded_cast_cannot_eat_the_beat_it_is_attached_to():
    """The cast clause never gives, so it is the one clause that needs a ceiling.

    Past the description's floor, what _fit_beat_prompt drops next is the
    SPOKEN LINES -- so an unbounded cast clause is one that can silence the
    beat it is carried on, which is a worse failure than the drift it exists
    to prevent.
    """
    crowd = [
        Element(
            name=f"Character Number {index}",
            images=(f"{index}.png",),
            wardrobe="a heavy charcoal overcoat, a red scarf, leather gloves",
        )
        for index in range(4)
    ]

    clause = _take(*crowd).cast_clause()

    assert wire_length(clause) <= MAX_CAST_CLAUSE_CHARS
    for index in range(4):
        assert f"@Element{index + 1} is Character Number {index}" in clause, (
            "the names never give: they are what the tokens mean"
        )


def test_the_line_survives_the_wardrobe():
    """Dressing the cast may not cost the beat its words.

    A beat that is not told what to say invents speech, while the subtitle
    burned into the same frame still comes from the script -- the failure
    test_a_take_says_what_the_script_wrote exists for.
    """
    take = SceneTake(
        seconds=12,
        beats=(
            Beat(
                seconds=12,
                description="the bookseller reads the letter she wrote " * 8,
                dialogue=("Elena: Fifty years... and I never sent it.",),
            ),
        ),
        elements=(ELENA, TOMAS),
        max_prompt_chars=512,
    )

    prompt = take.multi_prompt()[0]["prompt"]

    assert 'Elena says: "Fifty years... and I never sent it."' in prompt
    assert wire_length(prompt) <= 512


def test_an_outfit_that_cannot_be_said_whole_is_not_said_in_half():
    """Half a garment is a garment the model finishes by itself.

    Which is the drift being fixed, arrived at from the other direction: the
    room left over after four names is enough for "a dark green wool jacket
    over an" and nothing that reads as a costume.
    """
    crowd = [ELENA, TOMAS] + [
        Element(name=f"Extra {index}", images=(f"{index}.png",), wardrobe="a long navy raincoat")
        for index in range(3)
    ]

    clause = _take(*crowd).cast_clause()

    for dangling in (" over an.", " over a.", " over an;", " over a;"):
        assert dangling not in clause
    # And what room there is goes down the cast in order: an extra in a
    # raincoat cannot be dressed over a lead whose dress would not fit,
    # because the cast is ranked and the lead is what the scene is about.
    dressed = [part for part in clause.split("; ") if ", wearing " in part]
    if dressed:
        assert dressed[0].startswith("@Element1 ")


def test_a_cast_nobody_dressed_still_gets_its_names():
    clause = _take(Element(name="Elena Vasquez", images=("elena.png",))).cast_clause()

    assert clause.startswith("@Element1 is Elena Vasquez.")
    assert "wearing" not in clause
