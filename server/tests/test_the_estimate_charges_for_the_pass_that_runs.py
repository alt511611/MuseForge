"""A credit per scene for a stage the pipeline had already decided to skip.

`build_credit_breakdown` added the lip-sync surcharge whenever the toggle was
on and the deployment was configured for it. The pipeline asks a second
question the quote never did: on a job whose scene is rendered as ONE take by
a backend that speaks the film's language, the mouths were driven by the
generation that made the picture, so the lip-sync pass never runs at all
(pipelines/idea2video.picture_carries_dialogue). A 12-scene Pro job on
MUSEFORGE_VIDEO_PROVIDER=falai_multishot in English was therefore quoted -- and
charged, because /api/generate deducts from this same function -- 12 credits
for zero provider calls.

Both halves of the question are knowable before the job exists: the backend
comes from the environment, the language comes off the request. So the estimate
now asks it, through the same two functions the render asks through.

The row stays in the breakdown at zero rather than vanishing. A user who
switched the toggle on and saw the total not move could not tell whether the
feature was free, refused, or unpriced -- and only one of those is true.

The same job was ALSO quoted the time. interfaces/render_eta puts both
soundtrack stages in the tail, after the last scene lands -- 20 seconds a scene
for the TTS and 40 for the sync pass -- so that 12-scene job promised twelve
minutes of waiting for provider calls nobody makes. Both are gated on the same
question now, in the prior (api.render_plan_for) and in the live countdown the
viewer actually watches (jobs.arm_job_eta).
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import api as api_mod  # noqa: E402

SPEAKS = ("en", "zh")  # Kling v3's native audio -- interfaces/video_backend


@pytest.fixture
def pro_job_with_lipsync_on(monkeypatch):
    """A Pro deployment where every existing gate on the surcharge is open.

    Dialogue on, lip sync flagged and keyed: whatever these tests observe is
    then the LANGUAGE question and nothing else.
    """
    monkeypatch.setenv("MUSEFORGE_LIPSYNC_ENABLED", "1")
    monkeypatch.delenv("MUSEFORGE_LIPSYNC_PROVIDER", raising=False)
    monkeypatch.setenv("MUAPI_KEY", "real-muapi-key")
    monkeypatch.setattr(api_mod, "is_dialogue_enabled", lambda: True)


def _quote(language, scenes=3):
    return api_mod.build_credit_breakdown(
        scenes,
        dialogue_enabled=True,
        lipsync_enabled=True,
        plan="pro",
        language=language,
    )


def _rows(quote, key):
    return [row for row in quote["breakdown"] if row["key"] == key]


def test_a_picture_that_speaks_is_not_billed_for_the_sync_it_never_needs(
    pro_job_with_lipsync_on, monkeypatch
):
    """The regression, priced: one take, native audio, English drama.

    The base and dialogue rows are asserted alongside the total so a future
    change that drops the surcharge by dropping DIALOGUE instead cannot pass
    this test.
    """
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_multishot")

    quote = _quote("en", scenes=12)

    assert _rows(quote, "estimate_row_lipsync") == []
    assert quote["total_credits"] == 12 + 12  # base + dialogue, no sync pass


def test_the_free_pass_is_a_line_item_not_a_missing_one(
    pro_job_with_lipsync_on, monkeypatch
):
    """Silence would read as "your toggle did nothing" at the moment the user
    is deciding whether to spend. The row says which of the two it was."""
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_multishot")

    native = _rows(_quote("en"), "estimate_row_lipsync_native")

    assert len(native) == 1
    assert native[0]["credits"] == 0


@pytest.mark.parametrize("language", ["tr", "es", "ja"])
def test_a_language_the_picture_cannot_speak_still_pays_for_its_own_mouths(
    pro_job_with_lipsync_on, monkeypatch, language
):
    """The half of the question that looks like a detail and is not. Kling v3
    covers English and Chinese; a Turkish drama keeps every stage it had --
    the voice generator, the lip-sync pass, and the bill for both."""
    assert language not in SPEAKS
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_multishot")

    quote = _quote(language)

    assert _rows(quote, "estimate_row_lipsync")[0]["credits"] == 3
    assert _rows(quote, "estimate_row_lipsync_native") == []
    assert quote["total_credits"] == 3 + 3 + 3


def test_the_default_provider_pays_for_lipsync_in_every_language(
    pro_job_with_lipsync_on, monkeypatch
):
    """No deployment that has not opted into one-take rendering may be quoted
    differently than it was: the picture arrives mute on the shot-by-shot
    path, English or not, and the pass it needs is a real provider call."""
    monkeypatch.delenv("MUSEFORGE_VIDEO_PROVIDER", raising=False)

    assert _rows(_quote("en"), "estimate_row_lipsync")[0]["credits"] == 3


def test_a_backend_selected_for_single_shots_never_speaks_for_the_picture(
    pro_job_with_lipsync_on, monkeypatch
):
    """`falai` and `falai_multishot` are separate selections on purpose. A
    deployment that set the first one months ago renders shot-by-shot, so
    pricing it as a speaking take would undercharge a pass it does run."""
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai")

    assert _rows(_quote("en"), "estimate_row_lipsync")[0]["credits"] == 3


def test_an_unknown_language_is_quoted_as_the_english_it_will_be_written_in(
    pro_job_with_lipsync_on, monkeypatch
):
    """interfaces/language normalises an unrecognised code to English, and
    generate() stores the normalised value -- so the quote must ask about the
    language the film gets, not the one the client typed."""
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_multishot")

    assert _rows(_quote("klingon"), "estimate_row_lipsync") == []


def test_a_silent_film_is_not_offered_a_free_lipsync_row(
    pro_job_with_lipsync_on, monkeypatch
):
    """The zero-credit row answers "what happened to my toggle?", so it may
    only appear for someone who set the toggle. Nobody asked here."""
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_multishot")

    quote = api_mod.build_credit_breakdown(3, plan="pro", language="en")

    assert _rows(quote, "estimate_row_lipsync_native") == []
    assert quote["total_credits"] == 3


# ── The clock, which was quoted the same job ──────────────────────────────────

def test_a_speaking_take_is_not_quoted_the_minutes_it_does_not_spend(
    pro_job_with_lipsync_on, monkeypatch
):
    """Both stages sit in the TAIL, behind the last scene, so their cost is
    added wall-clock rather than something the scene loop hides. A 12-scene
    English job was promised 12 x (20 + 40) seconds of work that never runs."""
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_multishot")

    plan = api_mod.render_plan_for(
        12, dialogue_enabled=True, lipsync_enabled=True,
        plan="pro", demo=False, language="en",
    )
    spoken = api_mod.render_plan_for(
        12, dialogue_enabled=True, lipsync_enabled=True,
        plan="pro", demo=False, language="tr",
    )

    assert (plan.dialogue, plan.lipsync) == (False, False)
    assert (spoken.dialogue, spoken.lipsync) == (True, True)
    assert spoken.tail - plan.tail == 12 * (20 + 40)


def test_the_clock_a_viewer_watches_asks_the_question_too(monkeypatch):
    """The prior is quoted once, before the job starts; the countdown on the
    generate page is armed separately from the JOB. Fixing only the first
    leaves the wrong number on the screen the user is actually looking at."""
    import jobs as jobs_mod
    from interfaces.render_eta import RenderPlan

    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_multishot")
    armed = {}

    class _Job:
        num_scenes = 6
        music_enabled = False
        dialogue_enabled = True
        lipsync_enabled = True
        demo = False
        language = "en"

        class _Eta:
            def arm(self, plan, now):
                armed["plan"] = plan

        _eta = _Eta()

    jobs_mod.arm_job_eta(_Job())

    assert isinstance(armed["plan"], RenderPlan)
    assert (armed["plan"].dialogue, armed["plan"].lipsync) == (False, False)


def test_a_demo_run_is_never_asked_which_backend_would_have_spoken(
    pro_job_with_lipsync_on, monkeypatch
):
    """Demo runs no provider at all, which is why the pipeline guards the
    question with `not self.demo`. Its ETA is the flat demo constant either
    way -- this is here so the two stay the same shape of decision."""
    monkeypatch.setenv("MUSEFORGE_VIDEO_PROVIDER", "falai_multishot")

    plan = api_mod.render_plan_for(
        6, dialogue_enabled=True, lipsync_enabled=True,
        plan="pro", demo=True, language="en",
    )

    assert plan.dialogue is True
    assert api_mod.prior_seconds(plan) == 5
