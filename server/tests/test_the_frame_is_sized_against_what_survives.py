"""The axis was dropped to reclaim 40 characters, and 189 went unused.

Delivered job 812714ad-1f9, the same basement card game as 21e3d767-bce and
the same cast: a woman dealer and the man across the table. Every frame prompt
in it said

    dropping 262 chars ... (Shot on 35mm film, natural filmic grain ...)
    dropping 220 chars ... (180-degree rule, LOCKED for the whole film ...)

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
        visual_desc="Q" * description_chars,
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
    assert "Lighting continuity" in prompt
    assert "Setting:" in prompt
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS


def test_the_clauses_the_reserve_did_not_count_are_all_present():
    """Each of the 757 uncounted characters, still in the frame. If any of
    these has gone, the reserve is over-drawn again and the axis is only
    surviving because something above it left."""
    prompt = _prompt()

    assert "mouth is fully visible" in prompt      # REQUIRED, lip-sync
    assert "Facial expression and body language" in prompt
    assert "The cast is closed" in prompt
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
        "The cast is closed",           # rank 3
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
    """The line none of this crosses. The budget comes out of wardrobe prose,
    which the costume lock still covers -- never out of a described face."""
    prompt = _prompt()

    for face in (
        "Mara Vance", "sharp cheekbones", "thin scar through one eyebrow",
        "Tomas Rye", "shadowed jaw", "crooked nose broken once",
    ):
        assert face in prompt, face
    assert "Costume is LOCKED" in prompt
