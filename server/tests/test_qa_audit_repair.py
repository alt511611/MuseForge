"""QA audit & targeted repair: on a failed check, fix the SPECIFIC reported
issue with one corrective re-send instead of blindly regenerating the whole
frame from scratch (adapted from Virginia Tech's "Audit & Repair" technique).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key")


def _wire_common_mocks(monkeypatch, generate_image_with_reference):
    from interfaces.shot import StoryboardShot

    async def fake_design_storyboard(self, script, characters, user_requirement, director_style, **_kwargs):
        return [
            StoryboardShot(idx=0, visual_desc="Maria stands by the window", motion_desc="Maria turns")
        ]

    async def fake_generate_video(self, prompt, image_url, duration, aspect_ratio="16:9", plan="free", is_cancelled=None):
        return "https://fake.cdn/clip.mp4"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"fake")
        return path

    import agents.storyboard_artist as sb_mod
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod
    import pipelines.script2video as s2v_mod

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design_storyboard)
    monkeypatch.setattr(
        img_mod.MuAPIImageGenerator,
        "generate_image_with_reference",
        generate_image_with_reference,
    )
    monkeypatch.setattr(vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_generate_video)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)
    monkeypatch.setenv("MUSEFORGE_CHARACTER_QA_ENABLED", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-anthropic-key")


@pytest.mark.asyncio
async def test_qa_failure_triggers_single_corrective_repair(monkeypatch, tmp_path):
    """A failed audit must resend flux-pulid with the reference image AND
    the reported issue appended -- not a blind identical retry, and not a
    full from-scratch regeneration."""
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    from tools import character_qa as qa_mod

    calls = []

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        calls.append({"prompt": prompt, "reference_url": reference_url})
        if len(calls) == 1:
            return "https://fake.cdn/frame_bad.png"
        return "https://fake.cdn/frame_repaired.png"

    _wire_common_mocks(monkeypatch, fake_generate_image_with_reference)

    qa_responses = [
        {"character_ok": False, "setting_ok": True, "issue": "the coat color doesn't match the reference"},
    ]

    async def fake_verify_frame(frame_url, expected_character_desc, expected_setting, anthropic_api_key):
        return qa_responses.pop(0)

    monkeypatch.setattr(qa_mod, "verify_frame", fake_verify_frame)
    import pipelines.script2video as s2v_mod
    monkeypatch.setattr(s2v_mod, "verify_frame", fake_verify_frame)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [
        CharacterInScene(idx=0, name="Maria", static_features="a painter", is_visible=True),
    ]
    portraits = {"Maria": "https://fake.cdn/maria_portrait.png"}

    result = await pipeline.run(
        script="test script",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits=portraits,
    )

    # Exactly one repair attempt: two generate_image_with_reference calls total.
    assert len(calls) == 2, f"Expected exactly one repair re-send, got {len(calls)} total calls"

    first_prompt, second_prompt = calls[0]["prompt"], calls[1]["prompt"]
    assert "IMPORTANT CORRECTION" not in first_prompt
    assert "IMPORTANT CORRECTION: the coat color doesn't match the reference" in second_prompt
    # The repair prompt must still contain the original frame description --
    # this is a targeted fix, not a completely different prompt.
    assert "Maria stands by the window" in second_prompt

    # Both repair calls used the SAME reference image (identity preserved).
    assert calls[0]["reference_url"] == calls[1]["reference_url"] == "https://fake.cdn/maria_portrait.png"

    # The repaired frame -- not the flagged original -- is what gets animated.
    shot_meta = result["shots"][0]
    assert shot_meta["frame_url"] == "https://fake.cdn/frame_repaired.png"
    assert shot_meta["character_qa_warning"] is True
    assert shot_meta["qa_issue"] == "the coat color doesn't match the reference"


@pytest.mark.asyncio
async def test_qa_success_skips_repair_entirely(monkeypatch, tmp_path):
    """A passing audit must not trigger any extra generation call."""
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    from tools import character_qa as qa_mod

    calls = []

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        calls.append(prompt)
        return "https://fake.cdn/frame_good.png"

    _wire_common_mocks(monkeypatch, fake_generate_image_with_reference)

    async def fake_verify_frame(frame_url, expected_character_desc, expected_setting, anthropic_api_key):
        return {"character_ok": True, "setting_ok": True, "issue": ""}

    monkeypatch.setattr(qa_mod, "verify_frame", fake_verify_frame)
    import pipelines.script2video as s2v_mod
    monkeypatch.setattr(s2v_mod, "verify_frame", fake_verify_frame)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [CharacterInScene(idx=0, name="Maria", static_features="a painter", is_visible=True)]
    portraits = {"Maria": "https://fake.cdn/maria_portrait.png"}

    result = await pipeline.run(
        script="test script",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits=portraits,
    )

    assert len(calls) == 1, "No repair call should happen when QA passes"
    shot_meta = result["shots"][0]
    assert "character_qa_warning" not in shot_meta
    assert "qa_issue" not in shot_meta


@pytest.mark.asyncio
async def test_qa_disabled_never_calls_verify_frame(monkeypatch, tmp_path):
    """MUSEFORGE_CHARACTER_QA_ENABLED off must leave behavior fully unchanged
    -- no audit call, no repair call, no meta fields."""
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    from tools import character_qa as qa_mod

    calls = []

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        calls.append(prompt)
        return "https://fake.cdn/frame.png"

    _wire_common_mocks(monkeypatch, fake_generate_image_with_reference)
    monkeypatch.setenv("MUSEFORGE_CHARACTER_QA_ENABLED", "0")

    verify_calls = []

    async def fake_verify_frame(*args, **kwargs):
        verify_calls.append((args, kwargs))
        return {"character_ok": False, "setting_ok": False, "issue": "should never be called"}

    monkeypatch.setattr(qa_mod, "verify_frame", fake_verify_frame)
    import pipelines.script2video as s2v_mod
    monkeypatch.setattr(s2v_mod, "verify_frame", fake_verify_frame)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [CharacterInScene(idx=0, name="Maria", static_features="a painter", is_visible=True)]
    portraits = {"Maria": "https://fake.cdn/maria_portrait.png"}

    result = await pipeline.run(
        script="test script",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits=portraits,
    )

    assert verify_calls == [], "verify_frame must never be called when QA is disabled"
    assert len(calls) == 1, "No repair call should happen when QA is disabled"
    shot_meta = result["shots"][0]
    assert "character_qa_warning" not in shot_meta
    assert "setting_qa_warning" not in shot_meta
    assert "qa_issue" not in shot_meta


@pytest.mark.asyncio
async def test_repair_generation_failure_falls_open_to_original_frame(monkeypatch, tmp_path):
    """If the repair re-send itself fails, the pipeline must continue with
    the original (flagged) frame instead of crashing the shot."""
    from pipelines.script2video import Script2VideoPipeline
    from interfaces.character import CharacterInScene
    from tools import character_qa as qa_mod

    calls = []

    async def fake_generate_image_with_reference(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        calls.append(prompt)
        if len(calls) == 1:
            return "https://fake.cdn/frame_bad.png"
        raise RuntimeError("MuAPI repair call failed")

    _wire_common_mocks(monkeypatch, fake_generate_image_with_reference)

    async def fake_verify_frame(frame_url, expected_character_desc, expected_setting, anthropic_api_key):
        return {"character_ok": False, "setting_ok": True, "issue": "wrong hair color"}

    monkeypatch.setattr(qa_mod, "verify_frame", fake_verify_frame)
    import pipelines.script2video as s2v_mod
    monkeypatch.setattr(s2v_mod, "verify_frame", fake_verify_frame)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    characters = [CharacterInScene(idx=0, name="Maria", static_features="a painter", is_visible=True)]
    portraits = {"Maria": "https://fake.cdn/maria_portrait.png"}

    result = await pipeline.run(
        script="test script",
        characters=characters,
        working_dir=str(tmp_path),
        character_portraits=portraits,
    )

    # Repair was attempted (2 calls) but failed -- pipeline still completed
    # using the original frame, not crashed.
    assert len(calls) == 2
    shot_meta = result["shots"][0]
    assert shot_meta["frame_url"] == "https://fake.cdn/frame_bad.png"
    assert shot_meta["character_qa_warning"] is True
