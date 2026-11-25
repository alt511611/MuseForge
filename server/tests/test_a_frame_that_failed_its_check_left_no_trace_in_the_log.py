"""Five frame checks ran and the log said nothing about any of them.

Job 3570bab0: the frame QA was called five times, two replies were long enough
to carry an issue, and no line said whether a frame passed, failed, was repaired
or was kept. A scene whose room changed between shots could not be traced back
to a verdict, so the question "did the check see it?" had no answer.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_qa_audit_repair import _wire_common_mocks  # noqa: E402


async def _run(monkeypatch, tmp_path, verdict):
    from interfaces.character import CharacterInScene
    from pipelines.script2video import Script2VideoPipeline
    import pipelines.script2video as s2v_mod
    from tools import character_qa as qa_mod

    async def draw(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        return "https://fake.cdn/frame.png"

    _wire_common_mocks(monkeypatch, draw)

    async def fake_verify_frame(frame_url, expected_character_desc, expected_setting, anthropic_api_key):
        return verdict

    monkeypatch.setattr(qa_mod, "verify_frame", fake_verify_frame)
    monkeypatch.setattr(s2v_mod, "verify_frame", fake_verify_frame)
    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    await pipeline.run(
        script="test script",
        characters=[CharacterInScene(idx=0, name="Maria", static_features="a painter", is_visible=True)],
        working_dir=str(tmp_path),
        character_portraits={"Maria": "https://fake.cdn/maria.png"},
    )


@pytest.mark.asyncio
async def test_a_failed_frame_says_what_was_wrong_and_what_was_done(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    await _run(monkeypatch, tmp_path, {
        "character_ok": True, "setting_ok": False,
        "issue": "the wall is white brick, the set is bare concrete",
    })
    text = caplog.text
    assert "Frame QA failed shot 0" in text
    assert "white brick" in text and "repairing from the reference" in text


@pytest.mark.asyncio
async def test_a_frame_that_passed_says_so(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    await _run(monkeypatch, tmp_path, {"character_ok": True, "setting_ok": True, "issue": ""})
    assert "Frame QA passed shot 0" in caplog.text
