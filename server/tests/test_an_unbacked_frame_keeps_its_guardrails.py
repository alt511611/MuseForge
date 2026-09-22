"""Job 5abefcaf-7a49, scene 3: a text-only establishing angle on MUSEFORGE_
IMAGE_PROVIDER=falai_multiref -- no character reference sent, so the frame
prompt was the ONLY thing telling the model this was a one-woman shot with a
lit face. Under budget pressure the ladder dropped "Cast is closed" and "The
face is lit and readable, not a silhouette" exactly as their ordinary rank
says they may -- rank 3 and rank 4 both assume a reference image is backing
them up, and this frame had none. The rendered frame came out fine, which is
luck, not a guarantee: a two-shot reference-free scene has nothing else
standing between it and a stray face or a blown-out silhouette.

This file is the fix: when build_frame_prompt is told has_reference=False,
the cast-closure and face-visibility clauses outrank the acted expression
(worth losing first, when there is nothing else to lose) but still yield to
the room itself -- a scene in a different location is exactly as bad a
failure as a stranger in frame, per the ladder's own comments, so this
promotion must not be able to evict "Setting:" the way a first attempt at
this fix (REQUIRED, not a bounded rank) did.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import build_frame_prompt  # noqa: E402

CROWDED_LOCATION = (
    "a rain-soaked cargo harbour, container stacks eight high under gantry "
    "cranes, wet asphalt, sodium floodlights on steel masts, a customs shed "
    "with lit windows, mooring bollards and coiled hawsers along the quay"
)


def _characters(count):
    return [
        CharacterInScene(
            idx=i,
            name=f"Character{i}",
            static_features=(
                "a woman in her early thirties, sharp cheekbones, dark hair "
                "pulled back in a wet knot, tired grey eyes, lean build, a "
                "faded scar across her left eyebrow"
            ),
            is_visible=True,
            wardrobe=(
                "a soaked navy dock parka over a charcoal crew-neck sweater, "
                "steel-toed boots"
            ),
        )
        for i in range(count)
    ]


def _long_shot():
    return StoryboardShot(
        idx=0,
        visual_desc="She cuts the seal " + "under the sodium lamp " * 60,
        motion_desc="slow push in",
        expression_desc="jaw set, eyes narrowed against the rain",
        shot_type="medium",
        lens="35mm",
    )


def _crowded_prompt(has_reference):
    characters = _characters(8)
    return build_frame_prompt(
        style="Sci-Fi",
        shot=_long_shot(),
        setting_location=CROWDED_LOCATION,
        setting_time_of_day="night",
        setting_era="present day",
        has_dialogue=True,
        lipsync_enabled=True,
        characters=characters,
        matched_char=characters[0],
        has_reference=has_reference,
    )


def test_an_unbacked_frame_keeps_cast_closure_and_face_visibility():
    """THE DELIVERED SHAPE: job 5abefcaf-7a49's scene 3 was a one-woman
    establishing angle, not an eight-character ensemble -- crowded enough to
    overflow on its long shot description alone, the same way the real
    frame did."""
    characters = _characters(1)
    prompt = build_frame_prompt(
        style="Sci-Fi",
        shot=_long_shot(),
        setting_location=CROWDED_LOCATION,
        setting_time_of_day="night",
        setting_era="present day",
        has_dialogue=True,
        lipsync_enabled=True,
        characters=characters,
        matched_char=characters[0],
        has_reference=False,
    )
    assert "Cast is closed" in prompt
    assert "lit and readable, not a silhouette" in prompt


def test_an_extreme_ensemble_can_still_outrun_even_the_promoted_rank():
    """Not a guarantee -- a rank, and ranks can still lose to a big enough
    shortfall. Eight described characters plus the same long shot is heavier
    than the delivered job ever was; the promoted guardrails buy real
    margin (see the one-character version above) but are not a REQUIRED-
    style exemption, which is the whole point of using a bounded rank
    instead of one."""
    prompt = _crowded_prompt(has_reference=False)
    assert "Setting:" in prompt
    assert "Cast is closed" in prompt


def test_an_unbacked_frame_still_keeps_the_room_over_its_own_guardrails():
    """The regression a first attempt at this fix caused: making the
    guardrails REQUIRED (never droppable) left the ladder nothing to shed
    once the cosmetic tiers were gone, and it ate "Setting:" instead -- the
    one clause the whole ladder exists to protect first. The fix has to
    raise the guardrails' rank, not exempt them."""
    prompt = _crowded_prompt(has_reference=False)
    assert "Setting:" in prompt


def test_a_referenced_frame_keeps_the_ordinary_ladder():
    """With a reference image doing the same job, the clauses stay at their
    ordinary rank (3 / 4) -- droppable before the acted expression, exactly
    as they were before this fix. Nothing about a backed frame should
    change.

    Needs a heavier overflow than _crowded_prompt's: with the REAL T5
    tokenizer measuring (not the char-count estimate this repo falls back
    to without sentencepiece installed), that fixture's shortfall is small
    enough that cast/face survive on their ORDINARY rank too, which proves
    nothing about whether the promotion is what is protecting them.

    A longer shot description does not buy the overflow: build_frame_prompt
    compacts visual_desc toward its own floor before the token ladder ever
    runs, so padding the input just gets proportionally trimmed back out.
    What does NOT compact away is the per-character identity clause -- more
    named faces is more REQUIRED text with a hard floor -- so a bigger
    ensemble (10, not 8) is what actually raises the baseline the ladder has
    to fit everything else around. Picked at the size that costs exactly
    cast and face and nothing else (measured against the real T5 tokenizer):
    enough ensemble to need both of them, not so much that expression or
    the room get pulled in too and the comparison stops being about rank.
    """
    characters = _characters(10)
    heavy_shot = _long_shot()
    prompt = build_frame_prompt(
        style="Sci-Fi",
        shot=heavy_shot,
        setting_location=CROWDED_LOCATION,
        setting_time_of_day="night",
        setting_era="present day",
        has_dialogue=True,
        lipsync_enabled=True,
        characters=characters,
        matched_char=characters[0],
        has_reference=True,
    )
    assert "Cast is closed" not in prompt
    assert "lit and readable, not a silhouette" not in prompt
    # What their ordinary rank buys back: the acted expression, worth more
    # than either of them once a reference is doing their job.
    assert "Facial expression and body language" in prompt


def test_default_call_sites_are_unaffected():
    """has_reference defaults to False, which is deliberately the SAFER
    default (a caller that forgets to pass it gets the stronger guardrail,
    not the weaker one) -- but for every scene that IS backed by a
    reference, script2video.py now threads has_reference=True explicitly at
    both call sites (the per-shot path and the one-take path)."""
    import pipelines.script2video as s2v
    import inspect

    src = inspect.getsource(s2v)
    assert src.count("has_reference=bool(frame_references)") >= 1
    assert src.count("has_reference=has_ref") >= 1
