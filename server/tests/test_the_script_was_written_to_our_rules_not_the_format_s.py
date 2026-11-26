"""The script was written to this pipeline's rules, not to the format's.

Compared against how vertical drama is written in 2026 -- the format guides
(Scenemixer, Scenepaper, OpenMicroDrama, Genra) and the editorial passes the
script tools sell (character voice checks, on-the-nose detection, coverage) --
the screenwriter already had most of it. Missing:

* the hook outside micro-drama mode: three renders of one brief all opened on
  four to nine seconds of a patrol walk;
* a cap on a single line, which is also a subtitle on a phone;
* a voice check and an exposition check in the dialogue edit, which never knew
  who anyone was;
* in a series, a different kind of cliffhanger from the last one.
"""

import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces.character import CharacterProfile, DialogueLine, DramaScript, ScriptScene  # noqa: E402
from interfaces.series import SCREENWRITER_CLAUSE as SERIES_CLAUSE  # noqa: E402
from tools import dialogue_editor  # noqa: E402


def _prompt(**kw):
    return ScreenwriterAgent(api_key="", demo=True)._system_prompt(**kw)


def test_every_drama_opens_inside_its_story_not_only_a_micro_drama():
    for mode in ("cinematic", "micro_drama"):
        prompt = _prompt(narrative_mode=mode)
        assert "OPEN INSIDE THE STORY" in prompt
        assert "walking, patrolling" in prompt


def test_a_voiced_script_is_told_the_line_cap_and_why():
    prompt = _prompt(require_dialogue=True)
    assert "TWENTY WORDS AT MOST" in prompt
    assert "subtitle" in prompt
    assert "exposition" in prompt
    assert "sounds like" in prompt


def test_the_cap_the_writer_is_told_is_the_cap_the_editor_enforces():
    assert dialogue_editor.MAX_LINE_WORDS == 20
    assert f"No line over {dialogue_editor.MAX_LINE_WORDS} words" in dialogue_editor.SYSTEM


def test_a_series_does_not_end_on_the_same_kind_of_hook_twice():
    assert "different\nKIND of question" in SERIES_CLAUSE


# --- the edit -----------------------------------------------------------------


class _Client:
    def __init__(self, reply):
        self.messages = self
        self._reply = reply
        self.sent = None

    async def create(self, **kw):
        self.sent = kw
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(self._reply))])


def _script(line="Yeah, copy. One of these is lit up like it shouldn't be."):
    return DramaScript(
        title="Harbour",
        logline="x",
        characters=[
            CharacterProfile(name="Mara", description="woman, late thirties, dock worker", role="protagonist"),
            CharacterProfile(name="Sol", description="man in his sixties, heard only over the radio", role="supporting"),
        ],
        scenes=[ScriptScene(action="a", dialogue=[DialogueLine(character="Mara", line=line)])],
    )


def _reply(line):
    return {"scenes": [{"dialogue": [{"character": "Mara", "line": line}]}]}


async def test_the_editor_is_told_who_everyone_is():
    client = _Client(_reply("Copy. One of these is glowing."))
    await dialogue_editor.edit_dialogue(_script(), client, "m")
    sent = json.loads(client.sent["messages"][0]["content"])
    assert {c["name"] for c in sent["cast"]} == {"Mara", "Sol"}
    assert "heard only over the radio" in json.dumps(sent["cast"])
    assert "sound like THEMSELVES" in client.sent["system"]


async def test_an_edit_that_runs_past_the_cap_and_the_draft_is_refused():
    long_line = " ".join(["word"] * 24)
    out = await dialogue_editor.edit_dialogue(_script(), _Client(_reply(long_line)), "m")
    assert out.scenes[0].dialogue[0].line.startswith("Yeah, copy.")


async def test_an_edit_that_shortens_an_overlong_draft_is_taken_even_if_still_long():
    draft = " ".join(["draft"] * 30)
    shorter = " ".join(["better"] * 22)
    out = await dialogue_editor.edit_dialogue(_script(draft), _Client(_reply(shorter)), "m")
    assert out.scenes[0].dialogue[0].line == shorter


async def test_an_edit_inside_the_cap_is_taken():
    out = await dialogue_editor.edit_dialogue(_script(), _Client(_reply("Copy. This one's glowing.")), "m")
    assert out.scenes[0].dialogue[0].line == "Copy. This one's glowing."
