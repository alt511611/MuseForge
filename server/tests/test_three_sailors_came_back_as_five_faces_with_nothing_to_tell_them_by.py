"""Three sailors were delivered as five faces.

A 30-second drama from "Üç denizci ... dev bir canavar sallarını paramparça
eder" cut from a wide shot of three men in beige tunics to a man in a red
headband who had not been in it, then to a big black-bearded man who was never
seen again. The locked portrait holds a face; nothing held WHICH of three
identically dressed men this one was, and nothing made sure the brief's three
were three entries in the cast at all.

Two guards: every character carries a mark that survives a cut (and rides at
the FRONT of the wardrobe, which is cut from the end), and a head-count the
brief states is asked for once if the cast comes back short.
"""

import json
import logging
from types import SimpleNamespace

import anthropic
import pytest

from agents.screenwriter import ScreenwriterAgent
from interfaces import cast_count, cast_marks
from interfaces.character import CharacterProfile, DramaScript
from interfaces.scene_take import _fit_wardrobe

TURKISH_BRIEF = (
    "Üç denizci kıyıya yakın sakin sularda ilerlerken, denizin altından kalkan "
    "bir dev canavar sallarını paramparça eder ve adamlar baygın halde "
    "kumsala vurur."
)

TUNIC = "sleeveless beige linen tunic, rope belt, bare feet"


def _sailor(name, mark="", wardrobe=TUNIC):
    return CharacterProfile(name=name, description="man in his forties", wardrobe=wardrobe, mark=mark)


# ── the mark ────────────────────────────────────────────────────────────────


def test_the_mark_goes_in_front_of_the_outfit():
    assert cast_marks.fold("a red headband", TUNIC) == f"a red headband, {TUNIC}"


def test_a_mark_the_outfit_already_says_is_not_said_twice():
    once = cast_marks.fold("a red headband", f"a red headband, {TUNIC}")
    assert once.count("red headband") == 1


def test_folding_is_idempotent():
    once = cast_marks.fold("a red headband", TUNIC)
    assert cast_marks.fold("a red headband", once) == once


def test_a_mark_is_a_phrase_not_a_costume():
    long = "a red silk headband knotted at the back with two long trailing ends and gold thread"
    folded = cast_marks.fold(long, TUNIC)
    assert len(folded.split(", ")[0]) <= cast_marks.MAX_MARK_CHARS


def test_the_mark_survives_the_cast_clause_running_out_of_room():
    """The clause cuts an outfit from the end. A mark placed last would be the
    first thing it lost, and it is the one thing that must not be."""
    folded = cast_marks.fold("a red headband", TUNIC)
    assert "red headband" in _fit_wardrobe(folded, 30)


def test_three_men_in_one_tunic_are_one_look():
    crew = [_sailor("Aras"), _sailor("Bora"), _sailor("Cem")]
    assert len(cast_marks.collisions(crew)) == 3
    assert cast_marks.unmarked(crew) == ["Aras", "Bora", "Cem"]


def test_three_men_in_one_tunic_are_told_apart_by_their_marks():
    crew = [
        _sailor("Aras", "a red headband"),
        _sailor("Bora", "a white handlebar moustache"),
        _sailor("Cem", "a scar through the left eyebrow"),
    ]
    assert cast_marks.collisions(crew) == []
    assert cast_marks.unmarked(crew) == []


def test_a_lone_character_has_nobody_to_be_mistaken_for():
    assert cast_marks.unmarked([_sailor("Aras")]) == []


def test_the_script_is_read_with_the_mark_in_the_wardrobe(caplog):
    script = DramaScript(
        title="Raft",
        logline="x",
        characters=[
            _sailor("Aras", "a red headband"),
            _sailor("Bora"),
        ],
        scenes=[],
    )
    with caplog.at_level(logging.WARNING):
        ScreenwriterAgent._apply_character_marks(script)
    assert script.characters[0].wardrobe.startswith("a red headband")
    assert script.characters[1].wardrobe == TUNIC
    assert "No mark for ['Bora']" in caplog.text


def test_the_prompt_asks_for_a_mark_and_for_a_counted_group_listed_one_by_one():
    prompt = ScreenwriterAgent(demo=True)._system_prompt("en")
    assert "A MARK THAT SURVIVES A CUT" in prompt
    assert '"mark"' in prompt
    assert "A GROUP THE BRIEF COUNTS IS THAT MANY PEOPLE" in prompt


# ── the count ───────────────────────────────────────────────────────────────


def test_the_brief_that_was_delivered_counts_three():
    assert cast_count.counted_group(TURKISH_BRIEF) == 3


@pytest.mark.parametrize(
    "brief, wanted",
    [
        ("Three old sailors row home", 3),
        ("İki arkadaş ormanda kaybolur", 2),
        ("Dört asker köprüyü korur", 4),
        ("two years later, a woman returns", 0),
        ("İki saat sonra bir adam gelir", 0),
        ("Five minutes to midnight", 0),
        ("The manager counts three letters", 0),
        ("A lone sailor", 0),
    ],
)
def test_only_a_counted_group_of_people_is_a_count(brief, wanted):
    assert cast_count.counted_group(brief) == wanted


def test_a_cast_that_lists_everyone_is_not_short():
    assert cast_count.shortfall(TURKISH_BRIEF, 3) == 0
    assert cast_count.shortfall(TURKISH_BRIEF, 5) == 0


def test_a_cast_that_lists_fewer_is_short_by_the_briefs_count():
    assert cast_count.shortfall(TURKISH_BRIEF, 1) == 3


# ── asking once more ────────────────────────────────────────────────────────


def _script_json(names):
    return json.dumps(
        {
            "title": "Raft",
            "logline": "x",
            "setting_location": "open sea",
            "characters": [
                {"name": n, "description": "man in his forties", "wardrobe": TUNIC, "mark": m}
                for n, m in names
            ],
            "scenes": [{"action": "They row.", "emotion": "calm"}],
        }
    )


def _message(text, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        stop_details=None,
        usage=SimpleNamespace(output_tokens=1000),
    )


class _Stream:
    def __init__(self, message):
        self._message = message

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self._message


def _answers(monkeypatch, *replies):
    """Each stream call gets the next reply; returns the calls made."""
    calls = []

    def fake_stream(*args, **kwargs):
        calls.append(kwargs)
        reply = replies[min(len(calls), len(replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return _Stream(reply)

    class _Client:
        def __init__(self, *a, **k):
            self.messages = SimpleNamespace(stream=fake_stream)

    monkeypatch.setattr(anthropic, "AsyncAnthropic", _Client)
    return calls


async def _write(brief=TURKISH_BRIEF):
    return await ScreenwriterAgent(api_key="test")._write_with_claude(brief, "Cinematic", 3, "")


CAST_OF_ONE = _script_json([("Aras", "a red headband")])
CAST_OF_THREE = _script_json(
    [("Aras", "a red headband"), ("Bora", "a white moustache"), ("Cem", "a scarred eyebrow")]
)


@pytest.mark.asyncio
async def test_a_short_cast_is_asked_for_once_and_the_full_cast_is_used(monkeypatch):
    calls = _answers(monkeypatch, _message(CAST_OF_ONE), _message(CAST_OF_THREE))
    script = await _write()
    assert [c.name for c in script.characters] == ["Aras", "Bora", "Cem"]
    assert len(calls) == 2
    # The correction is a continuation of the conversation, not a fresh ask.
    turns = [m["role"] for m in calls[1]["messages"]]
    assert turns == ["user", "assistant", "user"]
    assert "counts 3 people" in calls[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_a_cast_that_was_complete_costs_no_second_call(monkeypatch):
    calls = _answers(monkeypatch, _message(CAST_OF_THREE))
    await _write()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_brief_with_no_count_costs_no_second_call(monkeypatch):
    calls = _answers(monkeypatch, _message(CAST_OF_ONE))
    await _write("A lone sailor rows home at dusk")
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_a_failed_correction_keeps_the_script_that_was_usable(monkeypatch):
    _answers(monkeypatch, _message(CAST_OF_ONE), RuntimeError("upstream down"))
    script = await _write()
    assert [c.name for c in script.characters] == ["Aras"]


@pytest.mark.asyncio
async def test_a_correction_that_is_still_short_keeps_the_first_script(monkeypatch):
    two = _script_json([("Aras", "a red headband"), ("Bora", "a white moustache")])
    _answers(monkeypatch, _message(CAST_OF_ONE), _message(two))
    script = await _write()
    assert [c.name for c in script.characters] == ["Aras"]


@pytest.mark.asyncio
async def test_the_corrected_cast_is_marked_too(monkeypatch):
    _answers(monkeypatch, _message(CAST_OF_ONE), _message(CAST_OF_THREE))
    script = await _write()
    assert script.characters[1].wardrobe.startswith("a white moustache")
