"""A second character brought a rule with it, and then knocked it off the ladder.

Delivered job 21e3d767-bce, brief "A card dealer in a basement game realises
the man across the table is copying her own tell". The cast was finally right
-- a woman dealer and a man opposite her, two faces, two voices. Every frame
prompt then said:

    dropping 262 chars ... (Shot on 35mm film, natural filmic grain ...)
    dropping 302 chars ... (Screen direction (LOCKED for the entire story ...)
    dropping 325 chars ... (Lighting continuity (identical in every shot ...)

and the film shows it: the two players swap sides across three of its four
two-shots, the key light changes four times in thirty seconds, and by the last
scene there is no table and no stairwell.

The 180-degree clause is emitted ONLY for exactly two visible characters. So
the rule that exists for two-handers is the rule two-handers push over the
budget, and it sat at the optional-direction rank, second in line to go.

Measured, a rich two-hander at the description cap: the prompt wanted 3351
characters of a 3000 budget. Dropping the film-look note -- the intended
sacrifice -- left it 89 over, and 89 characters cost the whole 233-character
axis.

Nothing here re-ranks the ladder. The ladder already records which losses are
cheap, and this was not a case for reversing it: the description kept all 320
of its characters while the film lost its geometry. MAX_VISUAL_DESC_CHARS was
measured "for a one-hander" and its own note settles who pays -- the shot's
description is cut to its share, "not worth the rules it was costing". A
two-hander's share is smaller by exactly the clause a two-hander adds.

The two continuity clauses were also written in prose and are now written
tight. Same instructions, fewer characters -- every token the older tests pin
is still there.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.lighting import resolve_lighting  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_CHARS,
    MAX_VISUAL_DESC_CHARS,
    MIN_VISUAL_DESC_CHARS,
    build_frame_prompt,
    build_screen_direction_clause,
)


#: Two people described the way a screenwriter actually describes them.
CAST = [
    (
        "Vera Kessler",
        "woman in her late thirties, sharp cheekbones, dark hair pulled back "
        "into a low knot, pale grey eyes, a thin scar through one eyebrow",
        "black tailored jacket over a white collarless shirt, jet drop earrings",
    ),
    (
        "Daniel Voss",
        "man in his mid-forties, lean build, shadowed jaw, deep-set eyes, "
        "greying at the temples, a crooked nose broken once",
        "dark three-piece suit, charcoal fedora, loosened black tie",
    ),
]


def _prompt(description_chars=MAX_VISUAL_DESC_CHARS, cast_size=2):
    characters = [
        CharacterInScene(
            idx=i, name=n, static_features=d, dynamic_features="",
            wardrobe=w, is_visible=True,
        )
        for i, (n, d, w) in enumerate(CAST[:cast_size])
    ]
    # "Q" as filler: it appears nowhere in the cast, the setting or the
    # style, so counting it counts the description and nothing else.
    shot = StoryboardShot(
        idx=0,
        visual_desc="Q" * description_chars,
        motion_desc="slow push-in",
        expression_desc="guarded",
        shot_type="medium shot",
        lens="50mm",
    )
    return build_frame_prompt(
        style="Noir",
        shot=shot,
        setting_location="a basement card room behind a locked stairwell door, "
                         "green felt table under a low tin shade",
        setting_time_of_day="night",
        setting_era="1950s",
        has_dialogue=True,
        lipsync_enabled=True,
        characters=characters,
        matched_char=characters[0],
    )


# ── the locks survive ───────────────────────────────────────────────────────


def test_a_two_hander_keeps_all_three_continuity_locks():
    """The delivered failure, at the description length that caused it."""
    prompt = _prompt(description_chars=MAX_VISUAL_DESC_CHARS)

    assert "180-degree rule" in prompt, "the axis was dropped again"
    assert "Lighting continuity" in prompt, "the light was dropped again"
    assert "Setting:" in prompt
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS


def test_it_holds_however_long_the_shot_description_runs():
    """A runaway description is cut to its share rather than spending the
    film's geometry -- including one far past the cap."""
    for length in (72, 200, MAX_VISUAL_DESC_CHARS, 800):
        prompt = _prompt(description_chars=length)
        assert "180-degree rule" in prompt, length
        assert "Lighting continuity" in prompt, length
        assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS, length


def test_both_faces_are_still_locked():
    """The whole point of the second character. The budget is taken from the
    description, never from the identity clause that stops the frame drawing
    a stranger."""
    prompt = _prompt()
    assert "Vera Kessler" in prompt and "Daniel Voss" in prompt


def test_a_one_hander_is_left_exactly_as_it_was():
    """No axis clause, so nothing is subtracted and the description keeps the
    cap it was measured with."""
    prompt = _prompt(description_chars=MAX_VISUAL_DESC_CHARS, cast_size=1)
    assert "Q" * MAX_VISUAL_DESC_CHARS in prompt
    assert "Lighting continuity" in prompt
    assert "180-degree rule" not in prompt  # only ever emitted for two


def test_the_film_look_note_is_still_the_first_thing_sacrificed():
    """Unchanged intent: the quality suffix is what a crowded frame gives up,
    and it is given up before any rule."""
    assert "Shot on 35mm" not in _prompt()


# ── the description pays, down to a floor ───────────────────────────────────


def test_the_two_hander_description_is_cut_by_what_the_axis_costs():
    axis = build_screen_direction_clause([
        CharacterInScene(idx=i, name=n, static_features=d, dynamic_features="",
                         wardrobe=w, is_visible=True)
        for i, (n, d, w) in enumerate(CAST)
    ])
    assert axis, "the fixture must actually be a two-hander"

    expected = max(MIN_VISUAL_DESC_CHARS, MAX_VISUAL_DESC_CHARS - len(axis))
    prompt = _prompt(description_chars=800)
    kept = prompt.count("Q")
    assert kept <= expected
    assert kept >= MIN_VISUAL_DESC_CHARS


def test_the_floor_leaves_the_shot_its_own_two_sentences():
    """"The first two sentences of a shot description are the shot" -- the cut
    is allowed to take the atmosphere, never the shot."""
    assert MIN_VISUAL_DESC_CHARS >= 200
    assert _prompt(description_chars=800).count("Q") >= MIN_VISUAL_DESC_CHARS


# ── the clauses got shorter, not weaker ─────────────────────────────────────


def test_the_axis_clause_still_says_everything_it_said():
    clause = build_screen_direction_clause([
        CharacterInScene(idx=i, name=n, static_features=d, dynamic_features="",
                         wardrobe=w, is_visible=True)
        for i, (n, d, w) in enumerate(CAST)
    ])
    assert "180-degree rule" in clause
    assert "LOCKED" in clause
    assert "Vera Kessler is on frame-left facing screen-right" in clause
    assert "Daniel Voss is on frame-right facing screen-left" in clause
    assert "singles" in clause          # holds when only one is in frame
    assert "Never mirror" in clause     # and never flipped
    assert len(clause) < 260, f"the point was to make it fit: {len(clause)}"


def test_the_lighting_clause_still_says_everything_it_said():
    clause = resolve_lighting("night").as_clause(interior=True)
    assert "Lighting continuity" in clause
    assert "every shot" in clause
    assert "key light" in clause
    assert "Do not change" in clause
    assert len(clause) < 300, f"the point was to make it fit: {len(clause)}"
