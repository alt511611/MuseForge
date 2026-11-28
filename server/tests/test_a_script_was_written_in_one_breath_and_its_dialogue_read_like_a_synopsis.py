"""The story and the twenty-field schema were one call, and the lines showed it.

Six briefs, written once by the production agent and once more with only the
dialogue passed through a separate editor, were read blind by a judge of another
model family in both orders: the edited script won overall on 6 of 6
("every light in the city went out" became "everything just went dark" -- but
also "glowing like it's alive" became "breathing"). The edit is allowed to change
words and nothing else, and to fail without costing anyone their script.
"""

import json
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from interfaces.character import DialogueLine, DramaScript, ScriptScene  # noqa: E402
from tools import dialogue_editor  # noqa: E402


def _script():
    return DramaScript(
        title="t", logline="l",
        scenes=[
            ScriptScene(action="a", dialogue=[
                DialogueLine(character="Mara", line="I have decided to open the container now."),
                DialogueLine(character="Rhea", line="You must not do that, it is dangerous."),
            ]),
            ScriptScene(action="b", dialogue=[]),
        ],
    )


class _Client:
    def __init__(self, reply=None, boom=None):
        self.calls = 0
        self.messages = self
        self._reply, self._boom = reply, boom

    async def create(self, **kw):
        self.calls += 1
        if self._boom:
            raise self._boom
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(self._reply))])


def _reply(*lines):
    return {"scenes": [{"dialogue": [{"character": c, "line": l} for c, l in lines]}, {"dialogue": []}]}


async def test_the_words_change_and_nothing_else():
    client = _Client(_reply(("Mara", "Opening it."), ("Rhea", "Don't.")))
    out = await dialogue_editor.edit_dialogue(_script(), client, "m")
    assert [d.line for d in out.scenes[0].dialogue] == ["Opening it.", "Don't."]
    assert [d.character for d in out.scenes[0].dialogue] == ["Mara", "Rhea"]


async def test_a_scene_whose_line_count_changed_keeps_its_first_draft():
    client = _Client(_reply(("Mara", "Opening it.")))
    out = await dialogue_editor.edit_dialogue(_script(), client, "m")
    assert out.scenes[0].dialogue[0].line.startswith("I have decided")


async def test_a_line_handed_to_another_speaker_is_not_accepted():
    client = _Client(_reply(("Rhea", "Opening it."), ("Mara", "Don't.")))
    out = await dialogue_editor.edit_dialogue(_script(), client, "m")
    assert out.scenes[0].dialogue[0].line.startswith("I have decided")


async def test_an_editor_that_fails_costs_nobody_their_script():
    out = await dialogue_editor.edit_dialogue(_script(), _Client(boom=RuntimeError("503")), "m")
    assert out.scenes[0].dialogue[1].line.startswith("You must not")


def test_lines_the_customer_wrote_are_not_for_the_editor_to_touch():
    assert dialogue_editor.customer_wrote_the_lines('She says "I never left" and goes.')
    assert not dialogue_editor.customer_wrote_the_lines("A dock worker finds a container.")


def test_the_editor_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_DIALOGUE_EDITOR", "0")
    assert not dialogue_editor.enabled()
