"""Job 265209d6: the listener was given the speaker's mouth.

A two-hander at a card table. Victor had every line of the last two scenes, and
the video model moved ROSA's mouth through them -- in the raw take, before any
lip sync touched it (a sync-3 run with Victor's face selected left the take as
it was). Nothing in the motion prompt said who was talking. And Victor spoke
through the thumb the script had him drag across his lip.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    build_motion_prompt,
    scene_speaker_keys,
    who_talks_in_frame,
)

ROSA = CharacterInScene(idx=0, name="Rosa Calder", static_features="woman")
VICTOR = CharacterInScene(idx=1, name="Victor Sable", static_features="man")
DIALOGUE = (
    "Victor Sable: Fella I took this from owes you a bad year, Rosa.\n"
    "Victor Sable: Felt only fair I pass the favor along."
)


def _two_shot():
    return StoryboardShot(
        idx=0,
        visual_desc="Victor Sable turns his hand face-up while Rosa Calder watches across the felt",
        motion_desc="Victor flips the card and drags his thumb across his lip",
        shot_type="medium",
    )


def test_who_speaks_is_read_from_the_scene_s_lines():
    assert scene_speaker_keys(DIALOGUE) == {"victor sable"}
    assert scene_speaker_keys("DISPATCHER (O.S.): Copy.\nMara: On it.") == {"mara"}
    assert scene_speaker_keys("") == set()


def test_the_frame_is_split_into_who_talks_and_who_listens():
    speakers, listeners = who_talks_in_frame(_two_shot(), [ROSA, VICTOR], VICTOR, {"victor sable"})
    assert speakers == ["Victor Sable"]
    assert listeners == ["Rosa Calder"]


def test_the_listener_is_told_to_keep_her_mouth_closed():
    prompt = build_motion_prompt(
        _two_shot(), VICTOR, speaking=True,
        speakers=["Victor Sable"], listeners=["Rosa Calder"],
    )
    assert "Rosa Calder only listens in this shot: the mouth closed" in prompt
    assert "While Victor Sable speaks, the mouth is clear of hands" in prompt


def test_a_shot_after_the_last_word_says_nothing_about_who_talks():
    prompt = build_motion_prompt(
        _two_shot(), VICTOR, speaking=False,
        speakers=["Victor Sable"], listeners=["Rosa Calder"],
    )
    assert "only listens" not in prompt
    assert "has finished speaking" in prompt


def test_a_scene_both_of_them_speak_in_has_no_listener():
    keys = scene_speaker_keys("Rosa Calder: Walk away.\nVictor Sable: No.")
    speakers, listeners = who_talks_in_frame(_two_shot(), [ROSA, VICTOR], VICTOR, keys)
    assert listeners == []
    assert sorted(speakers) == ["Rosa Calder", "Victor Sable"]


# --- through the real per-shot path --------------------------------------------


class _MiniMaxLike:
    accepts_reference_set = True
    can_start_from_frame = True
    uses_character_reference_to_video = True

    def __init__(self):
        self.prompts = []

    async def generate_video_from_image(self, prompt, image_url, duration=5,
                                        aspect_ratio="16:9", plan="free",
                                        is_cancelled=None, shot_profile=None, **kwargs):
        self.prompts.append(prompt)
        return "https://cdn/video.mp4"


@pytest.mark.asyncio
async def test_the_take_is_told_who_talks(monkeypatch, tmp_path):
    from pipelines.script2video import Script2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")

    async def fake_ref(self, prompt, references, aspect_ratio="16:9", is_cancelled=None, **kw):
        return "https://cdn/frame.jpg"

    async def fake_design(self, script, characters, *a, **kw):
        shot = _two_shot()
        shot.duration_seconds = 5.0
        return [shot]

    async def fake_download(url, path):
        open(path, "wb").write(b"v")
        return path

    async def fake_trim(path, out_path, seconds, from_head=True):
        return path

    monkeypatch.setattr("agents.storyboard_artist.StoryboardArtist.design_storyboard", fake_design)
    monkeypatch.setattr(
        "tools.muapi_image_generator.MuAPIImageGenerator.generate_image_with_reference", fake_ref
    )
    monkeypatch.setattr("pipelines.script2video.download_video", fake_download)
    monkeypatch.setattr("pipelines.script2video.trim_to_duration", fake_trim)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    backend = _MiniMaxLike()
    pipeline.video_gen = backend
    await pipeline.run(
        script="Victor turns over his winning hand.",
        characters=[ROSA, VICTOR],
        working_dir=str(tmp_path),
        character_portraits={"Rosa Calder": "https://cdn/rosa.jpg", "Victor Sable": "https://cdn/victor.jpg"},
        has_dialogue=True,
        scene_dialogue=DIALOGUE,
        scene_duration=5.0,
    )
    assert "Rosa Calder only listens" in backend.prompts[0]
