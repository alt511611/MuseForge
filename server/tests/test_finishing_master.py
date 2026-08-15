"""Motion prompt, master finishing (fades + loudness), music arc hint.

Three professional-finish gaps:
- the animation model only ever received motion_desc, so the designed camera
  move and acted expression never reached it (and identity could drift
  WITHIN a shot -- that drift happens in the video model, not the frame);
- the finished drama opened and cut on hard black-less edges;
- the mix carried no delivery loudness, and the score got a one-word brief.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _has_ffmpeg():
    import shutil

    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg  # noqa: F401

        return True
    except Exception:
        return False


_HAS_FFMPEG = _has_ffmpeg()
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene, DramaScript, ScriptScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.idea2video import (  # noqa: E402
    FADE_IN_SECONDS,
    FADE_OUT_SECONDS,
    _music_style_hint,
    finalize_master,
    is_finishing_enabled,
)
from pipelines.script2video import build_motion_prompt  # noqa: E402


# --- motion prompt ------------------------------------------------------


def test_motion_prompt_carries_camera_expression_and_identity():
    shot = StoryboardShot(
        idx=0,
        visual_desc="Elif sets the cup near her mother's hand",
        motion_desc="her hand crosses the table slowly",
        expression_desc="chin trembling, eyes brimming",
        camera_movement="slow push-in",
    )
    char = CharacterInScene(idx=0, name="Elif", static_features="24")
    prompt = build_motion_prompt(shot, char)

    assert "Camera: slow push-in." in prompt
    assert "her hand crosses the table slowly" in prompt
    assert "chin trembling, eyes brimming" in prompt
    # The character lock, restated for the ANIMATION step.
    assert "Keep Elif's facial identity EXACTLY as in the source image" in prompt
    assert "no morphing" in prompt


def test_motion_prompt_degrades_without_optional_fields():
    shot = StoryboardShot(
        idx=0, visual_desc="x", motion_desc="pan across the room",
        camera_movement="", expression_desc="",
    )
    prompt = build_motion_prompt(shot, None)
    assert "pan across the room" in prompt
    assert "Camera:" not in prompt
    assert "each character's facial identity" in prompt


@pytest.mark.asyncio
async def test_motion_prompt_reaches_the_video_model(monkeypatch, tmp_path):
    """End-to-end: the prompt Kling receives must carry the camera move."""
    import agents.storyboard_artist as sb_mod
    import pipelines.script2video as s2v_mod
    import tools.muapi_image_generator as img_mod
    import tools.muapi_video_generator as vid_mod

    captured = {}

    async def fake_design(self, script, characters, user_requirement="",
                          director_style="cinematic_balanced", **kwargs):
        return [
            StoryboardShot(
                idx=0, visual_desc="two women", motion_desc="hands meet",
                camera_movement="slow push-in",
                expression_desc="tearful relief",
            )
        ]

    async def fake_img(self, prompt, reference_url, aspect_ratio="16:9", is_cancelled=None):
        return "https://fake.cdn/f.png"

    async def fake_vid(self, prompt, image_url, duration=5, aspect_ratio="16:9",
                       plan="free", is_cancelled=None, shot_profile=None):
        captured["prompt"] = prompt
        return "https://fake.cdn/v.mp4"

    async def fake_dl(url, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        open(path, "wb").write(b"x")
        return path

    monkeypatch.setattr(sb_mod.StoryboardArtist, "design_storyboard", fake_design)
    monkeypatch.setattr(img_mod.MuAPIImageGenerator, "generate_image_with_reference", fake_img)
    monkeypatch.setattr(vid_mod.MuAPIVideoGenerator, "generate_video_from_image", fake_vid)
    monkeypatch.setattr(s2v_mod, "download_video", fake_dl)

    pipeline = s2v_mod.Script2VideoPipeline(api_key="k", demo=False)
    await pipeline.run(
        script="They speak.",
        characters=[CharacterInScene(idx=0, name="Ayse", static_features="52")],
        working_dir=str(tmp_path / "s"),
        character_portraits={"Ayse": "https://fake.cdn/p.png"},
    )
    assert "Camera: slow push-in." in captured["prompt"]
    assert "tearful relief" in captured["prompt"]
    assert "facial identity EXACTLY" in captured["prompt"]


# --- finishing pass -----------------------------------------------------


def test_finishing_on_by_default(monkeypatch):
    monkeypatch.delenv("MUSEFORGE_FINISHING", raising=False)
    assert is_finishing_enabled() is True
    monkeypatch.setenv("MUSEFORGE_FINISHING", "0")
    assert is_finishing_enabled() is False


@pytest.mark.asyncio
async def test_finalize_master_fades_the_picture(tmp_path):
    """First frame must be black(ish) after the fade-in; a mid frame must
    not be. Verified through real ffmpeg output, not the command line."""
    from moviepy import ColorClip, VideoFileClip

    src = str(tmp_path / "src.mp4")
    clip = ColorClip(size=(160, 90), color=(200, 150, 120), duration=4.0)
    clip.write_videofile(src, fps=10, codec="libx264", audio=False, logger=None)
    clip.close()

    out = str(tmp_path / "finished.mp4")
    result = await finalize_master(src, out)
    assert result == out

    with VideoFileClip(out) as got:
        first = got.get_frame(0.05).mean()
        mid = got.get_frame(2.0).mean()
        last = got.get_frame(max(0.0, got.duration - 0.08)).mean()
    assert first < mid * 0.35, (first, mid)
    assert last < mid * 0.35, (last, mid)


@pytest.mark.asyncio
async def test_finalize_master_skips_clips_too_short_to_fade(tmp_path):
    from moviepy import ColorClip

    src = str(tmp_path / "src.mp4")
    clip = ColorClip(size=(160, 90), color=(120, 90, 60), duration=1.0)
    clip.write_videofile(src, fps=10, codec="libx264", audio=False, logger=None)
    clip.close()

    out = str(tmp_path / "out.mp4")
    await finalize_master(src, out)
    # Copied through byte-identical: no fades that would eat the whole clip.
    assert open(out, "rb").read() == open(src, "rb").read()


@pytest.mark.asyncio
async def test_finalize_master_fails_open_on_garbage(tmp_path):
    src = str(tmp_path / "not_video.mp4")
    open(src, "wb").write(b"garbage")
    out = str(tmp_path / "out.mp4")
    await finalize_master(src, out)
    assert open(out, "rb").read() == b"garbage"


def test_fade_lengths_are_sane():
    assert 0.3 <= FADE_IN_SECONDS <= 1.5
    assert 0.3 <= FADE_OUT_SECONDS <= 2.0


@pytest.mark.asyncio
async def test_assembly_runs_finishing_before_watermark(tmp_path, monkeypatch):
    import pipelines.idea2video as idea2video_mod

    monkeypatch.delenv("MUSEFORGE_FINISHING", raising=False)
    calls = []

    async def _fake_concat(scene_paths, output_path):
        calls.append("concat")
        open(output_path, "wb").write(b"concat")
        return output_path

    async def _fake_grade(video_path, output_path, director_style="cinematic_balanced", **_kw):
        calls.append("grade")
        open(output_path, "wb").write(b"graded")
        return output_path

    async def _fake_music(video_path, output_path, music_url=None, **_kw):
        calls.append("music")
        open(output_path, "wb").write(b"music")
        return output_path

    async def _fake_finish(video_path, output_path):
        calls.append("finishing")
        open(output_path, "wb").write(b"finished")
        return output_path

    async def _fake_wm(video_path, output_path):
        calls.append("watermark")
        assert os.path.basename(video_path) == "drama_finished.mp4"
        open(output_path, "wb").write(b"wm")
        return output_path

    monkeypatch.setattr(idea2video_mod, "concatenate_videos", _fake_concat)
    monkeypatch.setattr(idea2video_mod, "apply_color_grade", _fake_grade)
    monkeypatch.setattr(idea2video_mod, "add_background_music", _fake_music)
    monkeypatch.setattr(idea2video_mod, "finalize_master", _fake_finish)
    monkeypatch.setattr(idea2video_mod, "add_watermark", _fake_wm)

    pipeline = idea2video_mod.Idea2VideoPipeline(api_key="", demo=False)
    await pipeline._assemble_final_drama(
        ["s0.mp4"], str(tmp_path / "job"), plan="free"
    )
    assert calls == ["concat", "grade", "music", "finishing", "watermark"]


# --- music arc hint -----------------------------------------------------


def test_music_hint_describes_the_arc():
    script = DramaScript(
        title="t", logline="l", theme="Forgiving is not forgetting.",
        scenes=[
            ScriptScene(action="a", emotion="guarded anticipation"),
            ScriptScene(action="b", emotion="steeled resolve"),
            ScriptScene(action="c", emotion="quiet release"),
        ],
    )
    hint = _music_style_hint(script)
    assert "opening with guarded anticipation" in hint
    assert "resolving into quiet release" in hint
    assert "forgiving is not forgetting" in hint


def test_music_hint_empty_for_legacy_scripts():
    script = DramaScript(title="t", logline="l", scenes=["plain", "strings"])
    assert _music_style_hint(script) == ""


def test_music_hint_reaches_the_generator_prompt():
    """Guard the consumption end: generate_instrumental must embed the hint."""
    import inspect

    from tools.muapi_music_generator import MuAPIMusicGenerator

    source = inspect.getsource(MuAPIMusicGenerator.generate_instrumental)
    assert "style_hint" in source


@pytest.mark.asyncio
@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not available")
async def test_the_master_is_delivered_at_48khz(tmp_path):
    """loudnorm works internally at 192kHz and leaves the stream there, so
    ffmpeg picks whatever the encoder will take next -- measured on a
    delivered master: 96kHz AAC. No platform asks for it, nothing in a drama
    needs it, and at a fixed bitrate it spends bandwidth on headroom nobody
    can hear instead of on the dialogue.
    """
    import subprocess

    from pipelines.idea2video import (
        DELIVERY_SAMPLE_RATE,
        finalize_master,
        resolve_ffmpeg_binary,
    )

    ff = resolve_ffmpeg_binary()
    source = str(tmp_path / "with_audio.mp4")
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=24:duration=6",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6:sample_rate=96000",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "96000", "-shortest", source],
        check=True, capture_output=True,
    )

    out = await finalize_master(source, str(tmp_path / "finished.mp4"))
    probe = subprocess.run(
        [ff, "-hide_banner", "-i", out], capture_output=True, text=True
    ).stderr
    audio_line = [l for l in probe.splitlines() if "Audio:" in l][0]
    assert f"{DELIVERY_SAMPLE_RATE} Hz" in audio_line, audio_line
