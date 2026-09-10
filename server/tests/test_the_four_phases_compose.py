"""The four phases, switched on together, on one scene.

Each was tested alone. That is not the same as tested: they meet in places
none of their own tests reach -- the reference set has to survive into the
one-take path, the take's elements have to carry voices the audio stage
decided not to generate per scene, and the audio the take produces has to
come back out of the picture before a join that strips it.

So this runs the real code with all of them on and only the PROVIDERS faked.
ffmpeg is real here: the take's soundtrack is a genuine audio stream, lifted
out by the same subprocess production uses, because a test that fakes the
extraction proves nothing about the one thing that stage does.

Nothing here has been run against a live provider. What it establishes is that
the wiring holds, not that the models behave.
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MULTISHOT = "fal-ai/kling-video/v3/standard/image-to-video"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

async def _real_clip_with_sound(path: str) -> bool:
    """A one-second clip that genuinely has an audio stream."""
    from pipelines.script2video import _ffmpeg_binary

    process = await asyncio.create_subprocess_exec(
        _ffmpeg_binary(), "-y",
        "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
        "-c:v", "libx264", "-c:a", "aac", "-shortest", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()
    return process.returncode == 0 and os.path.isfile(path)


def _cast():
    from interfaces.character import CharacterInScene

    return [
        CharacterInScene(
            idx=0, name="Vivian Marsh",
            static_features="woman in her mid-thirties, angular chin",
            wardrobe="grey wool coat",
        ),
        CharacterInScene(
            idx=1, name="Julian Voss",
            static_features="man in his forties, sharp jaw, grey-streaked hair",
            wardrobe="dark three-piece suit",
        ),
    ]


def _storyboard():
    from interfaces.shot import StoryboardShot

    return [
        StoryboardShot(
            idx=0,
            visual_desc="Vivian Marsh deals, chips stacked at her elbow",
            motion_desc="slow push in", shot_type="medium shot", duration_seconds=5,
        ),
        StoryboardShot(
            idx=1,
            visual_desc="Julian Voss watches her hands",
            motion_desc="hold", shot_type="close-up", duration_seconds=4,
        ),
        StoryboardShot(
            idx=2,
            visual_desc="the card turns over on the felt",
            motion_desc="snap", shot_type="extreme close-up", duration_seconds=3,
        ),
    ]


class _Multishot:
    """A backend that cuts inside one generation and speaks."""

    MULTISHOT_ENDPOINT = MULTISHOT

    def __init__(self, clip_path):
        self.multishot = True
        self.clip_path = clip_path
        self.takes = []
        self.per_shot_calls = 0

    async def generate_scene_take(self, take, is_cancelled=None, generate_audio=True):
        self.takes.append({"take": take, "audio": generate_audio})
        return "https://fake.cdn/scene.mp4"

    async def generate_video_from_image(self, *a, **k):
        self.per_shot_calls += 1
        raise AssertionError("the one-take path must not fall through to per-shot")


# --------------------------------------------------------------------------
# Phase 1 + 2 + 3 + 4, on one scene
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_four_phases_render_one_scene_together(monkeypatch, tmp_path):
    from pipelines.script2video import Script2VideoPipeline
    import agents.storyboard_artist as sb_mod
    import pipelines.script2video as s2v_mod
    import tools.muapi_image_generator as img_mod

    # Phase 1: a reference model that reads the whole set.
    monkeypatch.setenv("MUAPI_KONTEXT_MODEL", "flux-kontext-pro-i2i")

    clip = tmp_path / "take.mp4"
    if not await _real_clip_with_sound(str(clip)):
        pytest.skip("ffmpeg could not build the fixture")

    characters = _cast()
    shots = _storyboard()
    generator = _Multishot(str(clip))
    frame_calls = []

    async def fake_storyboard(self, *a, **k):
        return list(shots)

    async def fake_reference_frame(self, prompt, references, aspect_ratio="16:9", is_cancelled=None):
        frame_calls.append({"prompt": prompt, "references": list(references)})
        return "https://fake.cdn/opening.png"

    async def fake_plain_frame(self, prompt, aspect_ratio="16:9", is_cancelled=None):
        raise AssertionError("a scene with a cast must not render an unreferenced frame")

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(str(clip), "rb") as src, open(path, "wb") as dst:
            dst.write(src.read())
        return path

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_storyboard)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_reference_frame)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image", fake_plain_frame)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    pipeline.video_gen = generator

    result = await pipeline.run(
        script="Vivian Marsh deals as Julian Voss watches.",
        characters=characters,
        working_dir=str(tmp_path / "scene"),
        character_portraits={
            "Vivian Marsh": "https://cdn/vivian-sheet.png",
            "Julian Voss": "https://cdn/julian-sheet.png",
        },
        location_plate_url="https://cdn/basement-plate.png",
        scene_duration=12,
        has_dialogue=True,
        scene_dialogue="Play your cards, Mr. Voss.",
        language="en",
        voice_samples={
            "Vivian Marsh": "https://cdn/vivian-voice.mp3",
            "Julian Voss": "https://cdn/julian-voice.mp3",
        },
        aspect_ratio="9:16",
    )

    # ---- Phase 3: one generation for the whole scene, not one per angle.
    assert len(generator.takes) == 1
    assert generator.per_shot_calls == 0
    take = generator.takes[0]["take"]
    assert take.beat_count == 3, "the storyboard's three angles became three beats"
    assert sum(b.seconds for b in take.beats) == 12 == take.seconds

    # ---- Phase 1: ONE opening frame, and it depicts the OPENING BEAT.
    #
    # The start image is literally the film's first frame, so it is drawn from
    # what beat 1 shows -- Vivian and the room. Handing it Julian's sheet would
    # push a face into a framing the storyboard wrote without him, which is the
    # mistake Phase 1's own plate branch exists to undo.
    assert len(frame_calls) == 1, "one frame for the scene, not one per angle"
    assert frame_calls[0]["references"] == [
        "https://cdn/vivian-sheet.png",
        "https://cdn/basement-plate.png",
    ], "the beat's anchor, then the set; nobody who is not in this framing"

    # ...and the face that is NOT in the opening frame is locked anyway, as an
    # element, because the take runs past that beat into one he is in. This is
    # the invariant that makes a one-take render safe: every face the SCENE
    # shows is bound, whether or not it opens the scene.
    assert [e.name for e in take.elements] == ["Vivian Marsh", "Julian Voss"]

    # ---- Phase 2: the backend's declaration decided the take's shape.
    from interfaces.video_backend import backend_for

    declared = backend_for(MULTISHOT)
    assert take.beat_count <= declared.max_beats
    assert len(take.elements) <= declared.max_elements
    assert declared.duration.honours(take.seconds)

    # ---- Phase 4: it speaks, in the voices this film cast.
    assert generator.takes[0]["audio"] is True
    by_name = {e.name: e for e in take.elements}
    assert by_name["Vivian Marsh"].voice_sample == "https://cdn/vivian-voice.mp3"
    assert by_name["Julian Voss"].voice_sample == "https://cdn/julian-voice.mp3"

    # ...and the voice is lifted back out of the picture, by real ffmpeg,
    # before the join that would have dropped it.
    assert result["speaks_for_itself"] is True
    assert result["take_audio_path"] and os.path.getsize(result["take_audio_path"]) > 0
    assert os.path.isfile(result["path"])
    assert len(result["shots"]) == 3, "downstream still sees the designed framings"


@pytest.mark.asyncio
async def test_a_language_the_backend_cannot_speak_falls_back_without_breaking(
    monkeypatch, tmp_path
):
    """The branch, exercised: everything else stays on, only the voice moves.

    A Turkish film on a backend that speaks English and Chinese must render as
    one take with its cast locked -- and come back MUTE, so the dialogue and
    lip-sync stages it always had still run.
    """
    from pipelines.script2video import Script2VideoPipeline
    import agents.storyboard_artist as sb_mod
    import pipelines.script2video as s2v_mod
    import tools.muapi_image_generator as img_mod

    monkeypatch.setenv("MUAPI_KONTEXT_MODEL", "flux-kontext-pro-i2i")

    silent = tmp_path / "silent.mp4"
    process = await asyncio.create_subprocess_exec(
        s2v_mod._ffmpeg_binary(), "-y",
        "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1",
        "-c:v", "libx264", str(silent),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await process.communicate()
    if process.returncode != 0:
        pytest.skip("ffmpeg could not build the fixture")

    generator = _Multishot(str(silent))
    shots = _storyboard()

    async def fake_storyboard(self, *a, **k):
        return list(shots)

    async def fake_reference_frame(self, prompt, references, aspect_ratio="16:9", is_cancelled=None):
        return "https://fake.cdn/opening.png"

    async def fake_download(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(str(silent), "rb") as src, open(path, "wb") as dst:
            dst.write(src.read())
        return path

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_storyboard)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_reference_frame)
    monkeypatch.setattr(s2v_mod, "download_video", fake_download)

    pipeline = Script2VideoPipeline(api_key="test-key", demo=False)
    pipeline.video_gen = generator

    result = await pipeline.run(
        script="Vivian Marsh kartlarını dağıtır.",
        characters=_cast(),
        working_dir=str(tmp_path / "tr"),
        character_portraits={"Vivian Marsh": "https://cdn/vivian-sheet.png"},
        scene_duration=12,
        has_dialogue=True,
        scene_dialogue="Kartlarını oyna.",
        language="tr",
    )

    assert len(generator.takes) == 1, "still one take -- only the VOICE moved"
    assert generator.takes[0]["audio"] is False
    assert result["speaks_for_itself"] is False, (
        "a mute take must not claim the dialogue stage's job"
    )
    assert result["take_audio_path"] is None
    assert os.path.isfile(result["path"])


# --------------------------------------------------------------------------
# Phase 1, the other half: the lock itself
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_cast_is_locked_as_sheets_when_the_backend_reads_them(monkeypatch):
    from pipelines.idea2video import Idea2VideoPipeline

    monkeypatch.setenv("MUSEFORGE_CHARACTER_SHEET", "1")
    prompts = []

    pipeline = Idea2VideoPipeline(api_key="test-key", demo=False)

    async def fake_generate(prompt, aspect_ratio="1:1", is_cancelled=None):
        prompts.append(prompt)
        return f"https://cdn/sheet_{len(prompts)}.png"

    pipeline.image_gen.generate_image = fake_generate
    portraits = await pipeline._lock_character_portraits(_cast(), style="Noir")

    assert len(portraits) == 2
    for prompt in prompts:
        assert "reference sheet" in prompt
        assert "2x2 grid of the SAME person" in prompt
        assert "Front-facing, neutral expression" not in prompt
    # The wardrobe still rides along: a sheet binds a face, not an outfit.
    assert any("grey wool coat" in p for p in prompts)
    assert any("dark three-piece suit" in p for p in prompts)


# --------------------------------------------------------------------------
# Phase 4, the other half: the audio reaches the mix and skips the sync
# --------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_self_voiced_scene_reaches_the_mixer_and_skips_the_sync(
    monkeypatch, tmp_path
):
    """The wiring in idea2video's collection loop, which no phase test reached.

    A scene that said its own lines has to arrive at the mixer as an ordinary
    dialogue layer -- the take's audio on the scene's FIRST line, the rest read
    for captions alone -- and be invisible to the lip-sync pass.
    """
    from unittest.mock import AsyncMock

    from interfaces.character import DramaScript
    from pipelines import idea2video as idea_mod

    take_audio = tmp_path / "scene_take_audio.m4a"
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

    synced = []

    async def never_syncs(**kwargs):
        for track in kwargs.get("dialogue_tracks") or []:
            if not track.get("speaks_for_itself"):
                synced.append(track)
        return []

    pipeline._lipsync_scenes = never_syncs
    pipeline._assemble_final_drama = AsyncMock(return_value=str(clip))

    script = DramaScript(
        title="The Tell",
        logline="Two players, one lie.",
        scenes=[
            {
                "action": "Vivian Marsh deals.",
                "dialogue": [{"character": "Vivian Marsh", "line": "Play your cards."}],
            }
        ],
    )

    await pipeline.continue_from_script(
        script, working_dir=str(tmp_path / "job"), language="en"
    )

    tracks = pipeline._assemble_final_drama.await_args.kwargs.get("dialogue_tracks")
    assert tracks, "the scene's line must reach the mix"
    voiced = [t for t in tracks if t.get("audio_url")]
    assert len(voiced) == 1, "one combined file per scene, on its first line"
    assert voiced[0]["audio_url"] == str(take_audio)
    assert voiced[0]["speaks_for_itself"] is True
    assert voiced[0]["line"] == "Play your cards.", "the words survive for captions"
    assert synced == [], "the sync pass must not touch a scene already in sync"
