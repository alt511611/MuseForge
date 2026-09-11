"""The words reach the model that speaks them, and the delivery note is honest.

Job a66acd59 rendered its 30 seconds as one take with native audio and shipped
with two warnings, both wrong: "The script has no spoken lines, so there was
nothing to voice" over a drama whose burned-in subtitle reads "You're quick for
a man who's never played before", and "Lip sync did not run on any scene" over
a scene whose mouths were driven by the generation that made them.

Both came from the same mistake -- asking the TTS QUEUE a question about the
SCRIPT. On a native-audio take no speech task is ever created, because the take
says the lines, so the queue is empty on exactly the job where the dialogue
worked best.

Underneath them was a third and worse one: the beats carried only what the shot
LOOKS like. The model was given a picture to make and no words to say, so it
improvised speech while the subtitle burned into the same frame came from the
script -- a viewer hears one scene and reads another.
"""

import pytest

from interfaces.scene_take import Beat, _spread_dialogue, plan_scene_take
from interfaces.video_backend import BACKENDS


class _Shot:
    def __init__(self, visual, seconds):
        self.visual_desc = visual
        self.motion_desc = ""
        self.shot_type = ""
        self.deliver_seconds = seconds


def _multishot_backend():
    return next(b for b in BACKENDS.values() if getattr(b, "multishot", False))


def test_a_beat_is_told_the_words_not_only_the_picture():
    take = plan_scene_take(
        12,
        [_Shot("the dealer's hands over the deck", 6), _Shot("the man's face", 6)],
        _multishot_backend(),
        dialogue=["Vera: You're quick for a man who's never played before."],
    )

    assert take is not None
    spoken = take.multi_prompt()[0]["prompt"]
    assert 'Vera says: "You\'re quick for a man who\'s never played before."' in spoken, (
        "a native-audio take given no lines invents them, and the subtitle "
        "burned into the same frame still comes from the script"
    )


def test_a_mute_take_is_not_handed_lines_it_will_not_say():
    take = plan_scene_take(
        12,
        [_Shot("the dealer's hands over the deck", 12)],
        _multishot_backend(),
        dialogue=[],
    )

    assert take is not None
    assert "Spoken aloud" not in take.multi_prompt()[0]["prompt"]


def test_a_line_lands_in_the_beat_it_is_said_in():
    """Speech runs from the scene's start, so its place is decided by time.

    Not by which shot the storyboard happened to describe it in: the mixer
    anchors a scene's speech at the scene's first frame and the subtitles are
    timed the same way, so a line three seconds in belongs to whichever beat
    is on screen three seconds in.
    """
    beats = [Beat(4, "one"), Beat(4, "two"), Beat(4, "three")]

    spread = _spread_dialogue(
        [
            "Vera: You're quick for a man who's never played before.",
            "The Man: Beginner's luck.",
            "Vera: Twice?",
        ],
        beats,
    )

    # The first line runs 3.6s at WORDS_PER_SECOND, so the answer to it is
    # still inside the opening beat; "Twice?" comes at 4.8s, after the cut.
    assert spread[0] == (
        "Vera: You're quick for a man who's never played before.",
        "The Man: Beginner's luck.",
    )
    assert spread[1] == ("Vera: Twice?",)
    assert spread[2] == ()


def test_more_lines_than_beats_still_all_get_said():
    """A line past the last beat's end goes in the last beat, not nowhere."""
    beats = [Beat(2, "one"), Beat(2, "two")]

    spread = _spread_dialogue([f"Vera: line number {i}" for i in range(6)], beats)

    assert sum(len(lines) for lines in spread) == 6
    assert len(spread[-1]) >= 3


@pytest.mark.asyncio
async def test_a_self_voiced_job_is_not_told_its_script_was_silent(
    monkeypatch, tmp_path
):
    """The two delivery notes job a66acd59 shipped, neither of them true.

    Both were read off the TTS queue, which is empty on exactly the job where
    the dialogue worked: the take says the lines, so no speech task is ever
    created and no sync pass is ever needed.
    """
    from unittest.mock import AsyncMock

    from interfaces.character import DramaScript
    from pipelines import idea2video as idea_mod

    monkeypatch.setenv("MUSEFORGE_DIALOGUE", "1")
    take_audio = tmp_path / "take.m4a"
    take_audio.write_bytes(b"fake audio")
    clip = tmp_path / "scene.mp4"
    clip.write_bytes(b"fake video")

    pipeline = idea_mod.Idea2VideoPipeline("test-key", demo=False)
    pipeline._lock_character_portraits = AsyncMock(return_value={})
    pipeline._lock_location_plate = AsyncMock(return_value=None)
    pipeline._generate_foley = AsyncMock(return_value=[])
    pipeline.script2video.run = AsyncMock(
        return_value={
            "path": str(clip),
            "url": "https://cdn/scene.mp4",
            "shots": [],
            "take_audio_path": str(take_audio),
            "speaks_for_itself": True,
        }
    )
    pipeline._lipsync_scenes = AsyncMock(return_value=[])
    pipeline._assemble_final_drama = AsyncMock(return_value=str(clip))

    script = DramaScript(
        title="The Tell",
        logline="Two players, one lie.",
        scenes=[
            {
                "action": "Vera Kessler deals.",
                "dialogue": [
                    {
                        "character": "Vera Kessler",
                        "line": "You're quick for a man who's never played before.",
                    }
                ],
            }
        ],
    )

    result = await pipeline.continue_from_script(
        script,
        working_dir=str(tmp_path / "job"),
        language="en",
        dialogue_enabled=True,
        lipsync_enabled=True,
    )

    # Proof the self-voiced path is what ran: the track the mixer was handed
    # is the audio lifted out of the take, not a file a TTS provider made.
    tracks = pipeline._assemble_final_drama.await_args.kwargs.get("dialogue_tracks")
    assert [t for t in tracks if t.get("audio_url") == str(take_audio)]

    warnings = result.get("warnings") or []
    assert not any("no spoken lines" in w for w in warnings), (
        "the script had a line; it was the voice QUEUE that was empty"
    )
    assert not any("Lip sync did not run" in w for w in warnings), (
        "the mouths were driven by the generation that made the picture"
    )
