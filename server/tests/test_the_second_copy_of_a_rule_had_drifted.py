"""Three places that restated a rule instead of asking for it, and drifted.

- approve-script had its own credit arithmetic, written before the price list
  learned that a picture which speaks its own lines is not charged for a
  lip-sync pass. Customers on that path paid a per-scene surcharge for a
  stage that never ran.
- An admin retry listed the fields it copied, and the list stopped being
  complete: a Pro 4K micro-drama came back 1080p and cinematic.
- The screenwriter's JSON reader took everything between the first brace and
  the last one anywhere in the reply, so a model that added a second object
  after its script failed the whole paid job on a script that was fine.
"""

import inspect
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

import api as _api  # noqa: E402


# ── the quote at approval time ───────────────────────────────────────────────

def test_approve_script_quotes_from_the_price_list(monkeypatch):
    """Not from a second copy of it kept next to the charge."""
    source = inspect.getsource(_api.approve_script)

    assert "build_credit_breakdown(" in source
    assert "LIPSYNC_EXTRA_CREDIT_COST" not in source
    assert "MUSIC_EXTRA_CREDIT_COST" not in source


def test_a_film_the_picture_speaks_is_not_charged_for_lip_sync(monkeypatch):
    """The surcharge the copied arithmetic could not waive, since it had never
    heard of the film's language."""
    monkeypatch.setattr(_api, "is_dialogue_enabled", lambda: True)
    monkeypatch.setattr(_api, "_lipsync_configured", lambda: True)
    monkeypatch.setattr(_api, "_picture_will_carry_dialogue", lambda lang: True)

    quote = _api.build_credit_breakdown(
        4,
        dialogue_enabled=True,
        lipsync_enabled=True,
        plan="pro",
        language="en",
    )

    assert quote["total_credits"] == 4 + 4 * _api.DIALOGUE_EXTRA_CREDIT_COST
    assert any(row["key"] == "estimate_row_lipsync_native" for row in quote["breakdown"])


# ── the retry ────────────────────────────────────────────────────────────────

def test_a_retry_carries_what_decides_the_film_as_well_as_the_bill():
    """delivery_tier and narrative_mode are not billing fields; they are what
    the render IS. A retry that drops them is a different film."""
    source = inspect.getsource(_api.admin_retry_job)

    for field in (
        "narrative_mode",
        "delivery_tier",
        "series_id",
        "series_brief",
        "language",
        "lipsync_enabled",
        "library_characters",
    ):
        assert f"{field}=old.{field}" in source or f"{field}=list(old.{field}" in source, field


# ── the script reader ────────────────────────────────────────────────────────

def test_a_reply_with_a_second_object_after_the_script_still_parses():
    from agents.screenwriter import ScreenwriterAgent

    agent = ScreenwriterAgent(api_key="k", demo=True)
    reply = (
        'Here is the script:\n{"title": "Harbor", "scenes": ["a"]}\n\n'
        'And a shorter alternative:\n{"title": "Harbor (short)", "scenes": []}'
    )

    assert agent._parse_json(reply)["title"] == "Harbor"


def test_a_brace_inside_a_string_does_not_end_the_object():
    from agents.screenwriter import _first_json_object

    assert _first_json_object('{"logline": "she said \\"} now\\""}') == (
        '{"logline": "she said \\"} now\\""}'
    )


def test_a_reply_cut_off_mid_object_says_so():
    from agents.screenwriter import ScreenwriterAgent

    agent = ScreenwriterAgent(api_key="k", demo=True)

    with pytest.raises(ValueError, match="truncated"):
        agent._parse_json('{"title": "Harbor", "scenes": ["a"')


def test_a_reply_with_no_json_at_all_still_says_that():
    from agents.screenwriter import ScreenwriterAgent

    agent = ScreenwriterAgent(api_key="k", demo=True)

    with pytest.raises(ValueError, match="No JSON"):
        agent._parse_json("I'd rather not write that.")


def test_a_template_script_is_as_long_as_the_seconds_it_was_sold(monkeypatch):
    """8 was a second answer to a question interfaces/second_budget already
    answers, and the two disagree whenever the budget is retuned."""
    from agents.screenwriter import SECONDS_PER_CREDIT, ScreenwriterAgent

    agent = ScreenwriterAgent(api_key="k", demo=True)
    script = agent._write_template("a harbour goodbye", "Cinematic", 3)

    assert script.estimated_duration_seconds == len(script.scenes) * SECONDS_PER_CREDIT


# ── the repairs that stopped at the first character ──────────────────────────

def test_both_protagonists_of_a_two_hander_get_the_brief_s_gender():
    """The pass returned at the first protagonist the writer had already
    gendered, so the second one -- the case it exists for -- kept none."""
    from agents.screenwriter import ScreenwriterAgent
    from interfaces.character import CharacterProfile, DramaScript

    script = DramaScript(
        title="The Tell",
        logline="two women at a table",
        mood="tense",
        user_brief="she watches her opponent's hands and she says nothing",
        scenes=["a"],
        characters=[
            CharacterProfile(
                name="Mara", description="a woman in her forties", role="protagonist"
            ),
            CharacterProfile(
                name="Yara", description="late thirties, sharp", role="protagonist"
            ),
        ],
        setting_location="card room",
        setting_time_of_day="night",
        setting_era="present day",
    )

    ScreenwriterAgent._apply_brief_gender(script)

    assert script.characters[0].description == "a woman in her forties"
    assert script.characters[1].description.startswith("woman")


def test_a_demo_script_that_was_asked_for_dialogue_speaks():
    """Every stage that only exists when somebody speaks was untestable
    without spending real provider money on a script."""
    from agents.screenwriter import ScreenwriterAgent

    agent = ScreenwriterAgent(api_key="k", demo=True)
    silent = agent._write_template("a harbour goodbye", "Cinematic", 3)
    spoken = agent._write_template(
        "a harbour goodbye", "Cinematic", 3, require_dialogue=True
    )

    assert all(not scene.dialogue for scene in silent.scenes)
    assert any(scene.dialogue for scene in spoken.scenes)


def test_a_demo_micro_drama_ends_on_a_question():
    """cliffhanger is what the next episode is commissioned from, so a demo
    that leaves it empty cannot exercise a series at all."""
    from agents.screenwriter import ScreenwriterAgent

    agent = ScreenwriterAgent(api_key="k", demo=True)

    micro = agent._write_template(
        "a harbour goodbye", "Cinematic", 3, narrative_mode="micro_drama"
    )
    cinematic = agent._write_template("a harbour goodbye", "Cinematic", 3)

    assert micro.cliffhanger
    assert cinematic.cliffhanger == ""
