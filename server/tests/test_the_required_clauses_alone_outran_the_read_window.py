"""The ladder ran out of things to drop, said so, and sent the prompt anyway.

`fit_image_prompt` drops clauses worst-rank-first until the prompt fits T5's
512-token window, and `_drop_to` stops at REQUIRED by design -- it will not cut
into the style, the shot, its framing, the character lock or the mouth line.
Until now nothing answered the state that leaves behind. When the REQUIRED
clauses alone overran the window, the over-long prompt was returned, and
`build_frame_prompt` logged:

    Frame prompt is 563 tokens against a 512-token window with nothing optional
    left to drop — its required clauses alone exceed what FLUX will read, and
    the tail will be truncated silently. 1656 chars: Sci-Fi style. Elif stands
    frozen before the container's fully open doors, her we...

...and then sent it. T5 did the truncating, from the end, in silence. A module
whose entire purpose is that a budget should be enforced by the ladder rather
than by the tokenizer was handing the tokenizer the one case the ladder could
not handle.

DELIVERED JOB 4631cc44-d30 is where that line comes from, and its ratio is why
this went unseen for so long: 1656 characters at 563 tokens is 2.94 chars per
token, against the 3.98 this repo measured on its own English prose. The script
was in TURKISH. T5's vocabulary is English-centric, so Turkish costs roughly
40% more tokens for the same sentence -- a prompt that is comfortable in
English is over the window in Turkish, with nothing about it looking wrong.

What is at stake in the tail depends on the scene's shape, and both are
unrepairable by any later pass. Scene 2 of that job carried a world_change, so
its last REQUIRED clauses are the changed-state lock -- "the event the film was
commissioned for". On a scene without one, the last REQUIRED clause is the
lip-sync mouth line, and losing that is
`test_the_mouth_survives_the_budget`'s failure: the sync is requested, billed,
returned, and composited onto a frame with no mouth presented to camera.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from tools.t5_budget import count_tokens, tokenizer_is_real  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_CHARS,
    MAX_IMAGE_PROMPT_TOKENS,
    REQUIRED,
    build_frame_prompt,
    fit_image_prompt,
)

MOUTH = "mouth is fully visible"

#: Job 4631cc44-d30's own cast, in the language its script was written in.
ELIF = CharacterInScene(
    idx=0,
    name="Elif",
    static_features=(
        "otuzlu yaşlarının sonunda bir kadın, keskin köşeli yüz hatları, ıslak "
        "kısa kesilmiş koyu saçlar, sol kaşının üzerinde solmuş bir yara izi, "
        "çukura kaçmış gri gözler, ince dudaklar, çıkık elmacık kemikleri, "
        "soluk tenli"
    ),
    wardrobe=(
        "sarı yüksek görünürlüklü yağmurluk, altında lacivert iş poları, ağır "
        "su geçirmez pantolon, siyah eldivenler, göğsünde lamine liman giriş "
        "kartı, omuz askısında telsiz"
    ),
)

#: The clause that breaks the lock, and the one the ladder promotes to REQUIRED
#: when it is carried -- which is what puts a scene over the window with
#: nothing optional left to give.
BLACKOUT = "limandaki bütün ışıklar o kapıyı açtığı anda sönüyor"


def _turkish_frame(**kwargs):
    shot = StoryboardShot(
        idx=0,
        shot_type="medium shot",
        lens="35mm",
        motion_desc="yavaş içeri kaydırma",
        expression_desc="çenesi sıkılmış, yağmura karşı gözleri kısılmış",
        visual_desc=(
            "Elif konteynerin kilit koluna çömelmiş, telsizi ağzına kaldırmış, "
            "el feneri ıslak oluklu çeliği tarıyor"
        ),
    )
    params = dict(
        setting_location=(
            "yağmurla ıslanmış kargo limanı, sodyum projektörleri altında sıra "
            "sıra dizilmiş konteynerler ve ölü vinçler"
        ),
        setting_time_of_day="gece",
        setting_era="yakın gelecek",
        has_dialogue=True,
        lipsync_enabled=True,
        characters=[ELIF],
        matched_char=ELIF,
        has_location_plate=True,
        world_change=BLACKOUT,
        world_state="liman tamamen karanlıkta, yalnızca el feneriyle aydınlanıyor",
    )
    params.update(kwargs)
    return build_frame_prompt("Sci-Fi", shot, **params)


def test_the_tokenizer_is_the_real_one():
    """Everything below is only as good as this. Against the fallback estimate
    the Turkish ratio this file turns on does not exist -- the estimate is a
    constant, and a constant cannot be 40% wrong in one language."""
    assert tokenizer_is_real(), (
        "sentencepiece or assets/t5_spiece.model is missing; the frame budget "
        "is being estimated and these assertions mean nothing"
    )


def test_turkish_costs_what_the_delivered_job_said_it_cost():
    """The measurement the whole failure rests on, pinned so a future change
    to the tokenizer or the vendored vocabulary cannot quietly move it."""
    turkish = "yağmurla ıslanmış kargo limanı, konteyner sıraları arasında"
    english = "a rain-soaked cargo harbour, a lane between container rows"
    assert len(turkish) / count_tokens(turkish) < 2.5
    assert len(english) / count_tokens(english) > 3.5


def test_the_delivered_turkish_frame_now_fits_what_the_model_reads():
    """THE TEST THIS FILE EXISTS FOR.

    Job 4631cc44-d30's shape: a Turkish one-hander carrying a world_change, so
    the plate and the setting are REQUIRED alongside the identity lock and the
    mouth. It assembled at 525 tokens and was sent at 525 tokens.
    """
    prompt = _turkish_frame()
    used = count_tokens(prompt)
    assert used <= MAX_IMAGE_PROMPT_TOKENS, (
        f"{used} tokens: the tail is truncated silently and the frame is drawn "
        "from part of its instructions"
    )
    assert len(prompt) <= MAX_IMAGE_PROMPT_CHARS


def test_what_it_cost_was_words_off_the_longest_clause_not_the_tail():
    """The trade, stated so it cannot be reversed by accident.

    The identity clause is the longest REQUIRED clause and the only one with a
    PICTURE also holding it -- every frame is drawn from a reference portrait,
    and flux-pulid is an identity model outright. So it is the one that gives
    up words. What it buys is every short clause behind it, none of which has
    anything else carrying it.
    """
    prompt = _turkish_frame()
    # Trimmed, not deleted: the lock itself is still in the conditioning.
    assert "Appearance is FIXED" in prompt
    assert "Elif" in prompt
    # And the short clauses the tail is made of are all still here.
    assert MOUTH in prompt, "the clause the sync pass depends on was dropped"
    assert "Shot type: medium shot" in prompt
    assert BLACKOUT in prompt, "the story's own event was cut off the end"


def test_every_tail_clause_ends_inside_the_window():
    """Not "is it in the prompt" -- it always was, on the delivered frame.
    Whether the model reads it. This is the assertion T5's silence makes
    impossible to replace with an observation of the render."""
    prompt = _turkish_frame()
    for clause in (MOUTH, "Shot type: medium shot", BLACKOUT):
        assert clause in prompt
        head = prompt[: prompt.index(clause) + len(clause)]
        assert count_tokens(head) <= MAX_IMAGE_PROMPT_TOKENS, (
            f"{clause!r} ends past the {MAX_IMAGE_PROMPT_TOKENS}-token window, "
            "and nothing in the render will say so"
        )


def test_a_scene_with_no_world_change_keeps_its_mouth_at_the_tail():
    """The other shape, where the mouth IS the last required clause rather
    than sitting behind the changed-state lock."""
    prompt = _turkish_frame(world_change="", world_state="")
    assert count_tokens(prompt) <= MAX_IMAGE_PROMPT_TOKENS
    assert MOUTH in prompt
    head = prompt[: prompt.index(MOUTH) + len(MOUTH)]
    assert count_tokens(head) <= MAX_IMAGE_PROMPT_TOKENS


# ── the mechanism, independent of how a frame happens to be assembled ───────


def test_an_all_required_prompt_trims_its_longest_clause_not_its_last():
    """Straight at `fit_image_prompt`, with nothing droppable in it at all.

    A long Turkish description and one short required clause behind it. Cutting
    the assembled prompt at 512 tokens -- which is what T5 does, and what this
    function used to leave it to do -- deletes the short one whole to save a
    few words of a description with hundreds to spare.
    """
    long_clause = "yağmurla ıslanmış kargo limanı konteyner sıraları " * 28
    prompt = fit_image_prompt(
        [(REQUIRED, long_clause), (REQUIRED, "The speaking mouth is fully visible. ")]
    )
    assert count_tokens(long_clause) > MAX_IMAGE_PROMPT_TOKENS, (
        "this clause no longer overruns the window, so it no longer tests it"
    )
    assert count_tokens(prompt) <= MAX_IMAGE_PROMPT_TOKENS
    assert MOUTH in prompt
    # The long clause was cut down, not cut out.
    assert "kargo limanı" in prompt


def test_the_trim_lands_on_a_word_and_keeps_the_clauses_apart():
    """Segments are joined with no glue -- each carries its own trailing
    ". " -- so a trim that strips the punctuation welds this clause onto the
    next one, which is a different way to lose a clause than the one being
    prevented."""
    prompt = fit_image_prompt(
        [
            (REQUIRED, "yağmurla ıslanmış kargo limanı konteyner sıraları " * 28),
            (REQUIRED, "Shot type: medium shot. "),
        ]
    )
    assert "Shot type: medium shot" in prompt
    assert "sıralarıShot" not in prompt, "the trim welded two clauses together"
    assert ". Shot type" in prompt
