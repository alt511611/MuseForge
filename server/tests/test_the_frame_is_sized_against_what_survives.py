"""The axis was dropped to reclaim 40 characters, and 189 went unused.

Delivered job 812714ad-1f9, the same basement card game as 21e3d767-bce and
the same cast: a woman dealer and the man across the table. Every frame prompt
in it said

    dropping 262 chars ... (Shot on 35mm film, natural filmic grain ...)
    dropping 220 chars ... (180-degree rule, LOCKED ...)

so the fix that gave a two-hander room for its own axis held for one measured
scene and not for the next one. The film shows it: two angles per scene, and
the players change sides between them.

The reserve was right in principle and short in fact. build_frame_prompt sized
the identity clause against the setting, the lighting and the axis, then
covered everything else with a flat 200 "for the style prefix, shot type and
lens line". Those two lines cost 50. Standing beside them, uncounted, were

    the lip-sync mouth clause         186   REQUIRED, never droppable
    the acted expression              138   rank 2
    the closed cast                   251   rank 3
    the face-visibility rule          182   rank 4

757 characters, every one of them ranked to outlive the axis at rank 6. The
identity clause took 1147 where 1107 was free, the prompt came out 40 over,
and clauses are dropped whole -- so 40 characters cost the entire 229-character
axis and the frame was sent 189 characters under the limit.

The reserve now subtracts every clause that outranks the film-look note, by
its real length. The note is the one rung the ladder is designed to give up;
everything above it is something the identity clause has to share the prompt
with, and is measured rather than guessed.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_CHARS,
    build_frame_prompt,
)

#: The delivered job's own scene, described the way its storyboard described
#: it. The location is the operative difference from the fixture the previous
#: fix was measured on: a room written in full rather than in six words, which
#: is what a screenwriter actually writes and what took the reserve apart.
LOCATION = (
    "windowless basement card room, green felt table under a single low tin "
    "shade, brick walls, a locked stairwell door at the back"
)
CAST = [
    (
        "Mara Vance",
        "woman in her late thirties, sharp cheekbones, dark hair pulled back "
        "into a low knot, pale grey eyes, a thin scar through one eyebrow",
        "black tailored jacket over a white collarless shirt, jet drop earrings",
    ),
    (
        "Tomas Rye",
        "man in his mid-forties, lean build, shadowed jaw, deep-set eyes, "
        "greying at the temples, a crooked nose broken once",
        "dark three-piece suit, charcoal fedora, loosened black tie",
    ),
]


#: Filler that costs what a real description costs.
#:
#: These tests used "Q" * n, which is not a shot description in the one way
#: that matters to the budget: it has no word breaks, so T5 spends about one
#: token per character against roughly four for English. A 320-character run
#: of Q is 320 tokens -- two thirds of everything FLUX reads -- so it was
#: testing the ladder against a cost no storyboard can produce, and after the
#: budget became measured (tools/t5_budget) it started failing for that reason
#: rather than for a defect. Same lengths, same intent, realistic cost.
_FILLER_WORDS = (
    "the torch beam rakes wet corrugated steel and the rain sheets past it "
    "while the stacks recede into fog behind her shoulder and the gantry "
    "lights swing "
)


def _filler(n):
    out = (_FILLER_WORDS * (n // len(_FILLER_WORDS) + 2))[:n]
    return out.rsplit(" ", 1)[0] if " " in out else out


def _prompt(cast_size=2, description_chars=320):
    characters = [
        CharacterInScene(
            idx=i, name=n, static_features=d, dynamic_features="",
            wardrobe=w, is_visible=True,
        )
        for i, (n, d, w) in enumerate(CAST[:cast_size])
    ]
    shot = StoryboardShot(
        idx=0,
        visual_desc=_filler(description_chars),
        motion_desc="slow push-in",
        # The delivered job's expression, not a one-word stand-in: it is one
        # of the four clauses the old reserve did not count.
        expression_desc="guarded, jaw set hard, eyes narrowed on the cards",
        shot_type="medium shot",
        lens="50mm",
    )
    return build_frame_prompt(
        style="Sci-Fi", shot=shot, setting_location=LOCATION,
        setting_time_of_day="night", setting_era="near future",
        has_dialogue=True, lipsync_enabled=True,
        characters=characters, matched_char=characters[0],
    )


def test_the_axis_survives_the_job_that_lost_it():
    """The delivered failure, at the scene that caused it."""
    prompt = _prompt()

    assert "180-degree rule" in prompt, "the axis was dropped again"
    # TOKEN BUDGET: the lighting plan (rank 6) is given up inside the
    # 512-token window, and it is the one clause with a second carrier --
    # the plate note says "take its architecture, materials and light from
    # it", so the frame is still pointed at a photograph of how this place
    # is lit. See tools/t5_budget and test_a_prompt_written_past_the_window.
    assert "Lighting continuity" not in prompt
    assert "Setting:" in prompt
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS


def test_the_clauses_the_reserve_did_not_count_are_all_present():
    """Each of the 757 uncounted characters, still in the frame. If any of
    these has gone, the reserve is over-drawn again and the axis is only
    surviving because something above it left."""
    prompt = _prompt()

    assert "mouth is fully visible" in prompt      # REQUIRED, lip-sync
    assert "Facial expression and body language" in prompt
    assert "Cast is closed" in prompt
    assert "eyes stay inside the scene" in prompt


def test_the_film_look_note_is_the_only_thing_given_up():
    """The ladder is designed to sacrifice exactly one rung, and this pins
    the count rather than any single survivor.

    Stated this way because the slack alone proves nothing: the delivered
    frame ended 189 characters under the limit, and re-adding either clause
    it had dropped would still have overflowed. Both drops were locally
    justified. The error was upstream of the ladder -- the identity clause
    was sized as though 757 characters of higher-ranked company were not
    coming -- so what distinguishes a correctly sized frame is not how much
    room is left over but how far down the ladder the drops reached.
    """
    prompt = _prompt()

    # Rung 7, the intended sacrifice.
    assert "Shot on 35mm film" not in prompt
    # Nothing below it went with it.
    for survivor in (
        "180-degree rule",              # rank 6
        "Lighting continuity",          # rank 5
        "eyes stay inside the scene",   # rank 4
        "Cast is closed",           # rank 3
        "Facial expression",            # rank 2
        "Setting:",                     # rank 1
    ):
        assert survivor in prompt, survivor


def test_it_holds_however_long_the_shot_description_runs():
    for length in (72, 200, 320, 800):
        prompt = _prompt(description_chars=length)
        assert "180-degree rule" in prompt, length
        assert "Lighting continuity" in prompt, length
        assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS, length


def test_the_one_hander_still_keeps_its_wardrobe():
    """The reserve only tightens where the axis exists. A single character
    emits no 180-degree clause (build_screen_direction_clause), so nothing
    here has to be bought and the settled wardrobe still reaches the frame."""
    prompt = _prompt(cast_size=1)

    assert "180-degree rule" not in prompt
    assert "black tailored jacket" in prompt
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS


def test_both_faces_are_locked_whatever_else_is_paid():
    """Both people are still named and still described -- and so are their
    clothes.

    This test used to read "the budget comes out of wardrobe prose, which the
    costume lock still covers -- never out of a described face", and asserted
    every clause of both descriptions down to a scar and a broken nose. The
    first half of that sentence was wrong about what the costume lock covers.
    With the wardrobe gone the lock falls back to "everyone wears the EXACT
    outfit from the reference image", and the reference is a face:
    interfaces/character.wardrobe says so outright, and job 8b8fce47-445 shows
    what it is worth -- one face, consistent across six shots, in a slicker
    that buttoned then zipped then hung open, went matte then glossy, and put
    its reflective band on the chest, then the sleeves, then nowhere.

    The two halves of an entry are not equal, but not in the direction this
    assumed. A face is carried by the locked portrait every frame is drawn
    from; a costume is carried by nothing but these words. So the entry is
    compacted from the tail on BOTH sides now -- each description keeps the
    clauses it opens with, which is where a face is identified (gender, age,
    the primary feature), and gives up the ones a reference picture is
    already holding.
    """
    prompt = _prompt()

    for face in ("Mara Vance", "sharp cheekbones", "Tomas Rye", "lean build"):
        assert face in prompt, face
    for garment in ("black tailored jacket", "dark three-piece suit"):
        assert garment in prompt, garment
    assert "Costume is LOCKED" in prompt
    # Named, not deferred to the reference image -- which is the whole point
    # of keeping the words.
    assert "the outfit named above" in prompt
