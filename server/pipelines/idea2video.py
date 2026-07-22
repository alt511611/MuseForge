"""Full idea-to-video orchestration pipeline."""

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional

from agents.screenwriter import ScreenwriterAgent
from interfaces.character import CharacterInScene, DramaScript
from pipelines.script2video import (
    PipelineCancelled,
    Script2VideoPipeline,
    _make_image_generator,
    apply_color_grade,
    concatenate_videos,
    concatenate_videos_with_transitions,
    download_video,
    is_scene_transitions_enabled,
)
from tools.muapi_voice_generator import MuAPIVoiceGenerator, is_dialogue_enabled

logger = logging.getLogger(__name__)


def _make_music_generator(api_key: str, demo: bool):
    """Pick the music-generation backend. Defaults to MuAPI unchanged.
    MUSEFORGE_MUSIC_PROVIDER=falai opts into fal.ai Beatoven
    (endpoint ``beatoven/music-generation``). Lazy-imported.
    """
    provider = os.environ.get("MUSEFORGE_MUSIC_PROVIDER", "muapi")
    if provider == "falai":
        from tools.falai_music_generator import FalAIMusicGenerator

        return FalAIMusicGenerator(os.environ.get("FAL_KEY", ""), demo=demo)
    from tools.muapi_music_generator import MuAPIMusicGenerator

    return MuAPIMusicGenerator(api_key, demo=demo)


# Watermark applies to the Free plan only — Creator and Pro are watermark-free.
# This is the ONE real, enforced differentiator behind the "No watermark" /
# "Watermarked" pricing copy (see client/lib/i18n plan_*_features).
WATERMARK_PLANS = {"free"}
WATERMARK_TEXT = "MuseForge"

# moviepy's TextClip requires an explicit OpenType/TrueType font path (it has
# no built-in default). We probe a handful of common install locations
# instead of bundling a font file — the Dockerfile installs fonts-dejavu-core
# for exactly this purpose. If none are found, add_watermark() fails open.
_WATERMARK_FONT_CANDIDATES = [
    os.environ.get("MUSEFORGE_WATERMARK_FONT", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]


def _scene_action(scene: Any) -> str:
    if isinstance(scene, str):
        return scene
    if isinstance(scene, dict):
        return str(scene.get("action", ""))
    return str(getattr(scene, "action", ""))


def _scene_dialogue(scene: Any) -> List[Any]:
    if isinstance(scene, str):
        return []
    if isinstance(scene, dict):
        return list(scene.get("dialogue") or [])
    return list(getattr(scene, "dialogue", None) or [])


def _find_watermark_font() -> Optional[str]:
    for path in _WATERMARK_FONT_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    return None


async def add_background_music(
    video_path: str,
    output_path: str,
    music_url: Optional[str] = None,
    dialogue_tracks: Optional[List[Dict[str, Any]]] = None,
    scene_paths: Optional[List[str]] = None,
) -> str:
    """Mix music and timed dialogue once, with dialogue louder than music."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    video = None
    opened_audio = []
    final = None
    final_audio = None
    try:
        from moviepy import AudioFileClip, CompositeAudioClip, VideoFileClip

        video = VideoFileClip(video_path)
        dialogue_tracks = dialogue_tracks or []
        layers = []

        # Preserve source audio when present. Generated MuAPI clips are normally
        # silent, but this avoids unexpectedly discarding audio from future models.
        if video.audio is not None:
            layers.append(video.audio)

        if music_url:
            try:
                music = AudioFileClip(music_url).with_duration(video.duration)
                # Dialogue remains at full level; duck music only when speech exists.
                if dialogue_tracks:
                    music = music.with_volume_scaled(0.2)
                opened_audio.append(music)
                layers.append(music)
            except Exception as exc:
                logger.warning("Music track could not be loaded; continuing without it: %s", exc)

        scene_durations: List[float] = []
        for path in scene_paths or []:
            scene_clip = None
            try:
                scene_clip = VideoFileClip(path)
                scene_durations.append(float(scene_clip.duration or 0))
            except Exception:
                scene_durations.append(0.0)
            finally:
                if scene_clip is not None:
                    scene_clip.close()

        scene_starts: List[float] = []
        elapsed = 0.0
        for duration in scene_durations:
            scene_starts.append(elapsed)
            elapsed += duration
        line_offsets: Dict[int, float] = {}

        for track in dialogue_tracks:
            dialogue = None
            try:
                scene_index = int(track.get("scene_index", 0))
                scene_start = (
                    scene_starts[scene_index]
                    if 0 <= scene_index < len(scene_starts)
                    else 0.0
                )
                local_start = line_offsets.get(scene_index, 0.0)
                dialogue = AudioFileClip(track["audio_url"])
                available = (
                    scene_durations[scene_index] - local_start
                    if 0 <= scene_index < len(scene_durations)
                    else video.duration - scene_start - local_start
                )
                if available <= 0:
                    dialogue.close()
                    continue
                if dialogue.duration > available:
                    dialogue = dialogue.subclipped(0, available)
                dialogue = dialogue.with_start(scene_start + local_start)
                opened_audio.append(dialogue)
                layers.append(dialogue)
                line_offsets[scene_index] = local_start + float(dialogue.duration or 0) + 0.2
            except Exception as exc:
                if dialogue is not None:
                    try:
                        dialogue.close()
                    except Exception:
                        pass
                logger.warning("Dialogue track could not be mixed; skipping it: %s", exc)

        if layers:
            final_audio = CompositeAudioClip(layers).with_duration(video.duration)
            final = video.with_audio(final_audio)
        else:
            final = video
        final.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
    except Exception as exc:
        logger.warning("Audio mixing failed; shipping silent/source video: %s", exc)
        with open(video_path, "rb") as src:
            data = src.read()
        with open(output_path, "wb") as dst:
            dst.write(data)
    finally:
        if final is not None and final is not video:
            try:
                final.close()
            except Exception:
                pass
        if final_audio is not None:
            try:
                final_audio.close()
            except Exception:
                pass
        if video is not None:
            try:
                video.close()
            except Exception:
                pass
        for audio in opened_audio:
            try:
                audio.close()
            except Exception:
                pass
    return output_path


def _format_srt_timestamp(seconds: float) -> str:
    """SRT timestamp: HH:MM:SS,mmm"""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _estimate_line_duration_seconds(line: str) -> float:
    """Rough spoken duration from text when audio can't be probed (~2.5 words/sec)."""
    words = max(1, len((line or "").split()))
    return max(1.2, min(8.0, words / 2.5))


def _probe_audio_duration_seconds(audio_url: str) -> Optional[float]:
    try:
        from moviepy import AudioFileClip

        clip = AudioFileClip(audio_url)
        try:
            duration = float(clip.duration or 0)
            return duration if duration > 0 else None
        finally:
            clip.close()
    except Exception:
        return None


def _scene_start_offsets(scene_paths: Optional[List[str]]) -> List[float]:
    """Absolute start time of each scene in the concatenated drama (seconds)."""
    starts: List[float] = []
    elapsed = 0.0
    for path in scene_paths or []:
        starts.append(elapsed)
        duration = 0.0
        scene_clip = None
        try:
            from moviepy import VideoFileClip

            scene_clip = VideoFileClip(path)
            duration = float(scene_clip.duration or 0)
        except Exception:
            duration = 0.0
        finally:
            if scene_clip is not None:
                try:
                    scene_clip.close()
                except Exception:
                    pass
        elapsed += duration
    return starts


def build_srt_from_dialogue_tracks(
    dialogue_tracks: List[Dict[str, Any]],
    scene_paths: Optional[List[str]] = None,
) -> str:
    """Build an SRT document from dialogue tracks.

    Timing mirrors ``add_background_music``: lines within a scene are laid
    out sequentially from that scene's start, with a short gap between lines.
    Tracks may optionally carry explicit ``start_seconds`` / ``end_seconds``
    (or ``duration_seconds``) for tests / pre-timed callers.
    """
    scene_starts = _scene_start_offsets(scene_paths)
    line_offsets: Dict[int, float] = {}
    blocks: List[str] = []
    index = 0

    for track in dialogue_tracks or []:
        line = str(track.get("line") or "").strip()
        if not line:
            continue
        character = str(track.get("character") or "").strip()
        text = f"{character}: {line}" if character else line

        if "start_seconds" in track:
            start = float(track["start_seconds"])
            if "end_seconds" in track:
                end = float(track["end_seconds"])
            else:
                duration = float(
                    track.get("duration_seconds")
                    or _probe_audio_duration_seconds(str(track.get("audio_url") or ""))
                    or _estimate_line_duration_seconds(line)
                )
                end = start + duration
        else:
            scene_index = int(track.get("scene_index", 0))
            scene_start = (
                scene_starts[scene_index]
                if 0 <= scene_index < len(scene_starts)
                else 0.0
            )
            local_start = line_offsets.get(scene_index, 0.0)
            start = scene_start + local_start
            duration = float(
                track.get("duration_seconds")
                or _probe_audio_duration_seconds(str(track.get("audio_url") or ""))
                or _estimate_line_duration_seconds(line)
            )
            end = start + duration
            line_offsets[scene_index] = local_start + duration + 0.2

        if end <= start:
            end = start + 1.0

        index += 1
        # SRT uses blank lines between cues; escape nothing special beyond
        # stripping carriage returns so a single cue stays one logical block.
        safe_text = text.replace("\r\n", "\n").replace("\r", "\n")
        blocks.append(
            f"{index}\n"
            f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n"
            f"{safe_text}\n"
        )

    return "\n".join(blocks)


def _escape_subtitles_filter_path(path: str) -> str:
    """Escape a filesystem path for ffmpeg's subtitles= filter."""
    # Prefer forward slashes; escape characters that break the filter grammar.
    escaped = os.path.abspath(path).replace("\\", "/")
    escaped = escaped.replace(":", "\\:").replace("'", "\\'")
    return escaped


async def burn_subtitles(
    video_path: str,
    output_path: str,
    dialogue_tracks: list,
    scene_paths: Optional[List[str]] = None,
) -> str:
    """Burn dialogue captions into ``video_path`` via ffmpeg's subtitles filter.

    Builds a temporary .srt from ``dialogue_tracks`` (white text + black outline
    / box for readability). Fails open: on any error the original video is
    copied through unchanged — same pattern as watermark / color grade.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    def _copy_through() -> str:
        if os.path.abspath(video_path) != os.path.abspath(output_path):
            with open(video_path, "rb") as src:
                data = src.read()
            with open(output_path, "wb") as dst:
                dst.write(data)
        return output_path

    if not dialogue_tracks:
        return _copy_through()

    srt_path = None
    try:
        srt_body = build_srt_from_dialogue_tracks(
            list(dialogue_tracks), scene_paths=scene_paths
        )
        if not srt_body.strip():
            return _copy_through()

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".srt",
            prefix="museforge_subs_",
            dir=os.path.dirname(output_path) or ".",
            delete=False,
            encoding="utf-8",
        ) as srt_file:
            srt_path = srt_file.name
            srt_file.write(srt_body)

        ffmpeg_binary = os.environ.get("MUSEFORGE_FFMPEG_BINARY") or shutil.which("ffmpeg")
        if not ffmpeg_binary:
            try:
                import imageio_ffmpeg

                ffmpeg_binary = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ffmpeg_binary = "ffmpeg"

        # White primary text, black outline, BorderStyle=3 = opaque box behind
        # text for readability on busy backgrounds.
        force_style = (
            "FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BorderStyle=3,Outline=1,Shadow=0,Alignment=2,MarginV=36"
        )
        vf = (
            f"subtitles={_escape_subtitles_filter_path(srt_path)}"
            f":force_style='{force_style}'"
        )

        process = await asyncio.create_subprocess_exec(
            ffmpeg_binary,
            "-y",
            "-i",
            video_path,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-c:a",
            "copy",
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode == 0 and os.path.isfile(output_path):
            return output_path
        logger.warning(
            "Subtitle burn ffmpeg filter failed (exit=%s), shipping without captions: %s",
            process.returncode,
            stderr.decode("utf-8", errors="replace")[-1000:],
        )
    except Exception as exc:
        logger.warning("Subtitle burn unavailable, shipping without captions: %s", exc)
        try:
            os.unlink(output_path)
        except OSError:
            pass
        return _copy_through()
    finally:
        if srt_path:
            try:
                os.unlink(srt_path)
            except OSError:
                pass

    try:
        os.unlink(output_path)
    except OSError:
        pass
    return _copy_through()


async def add_watermark(video_path: str, output_path: str) -> str:
    """Burn a small, semi-transparent "MuseForge" text watermark into the
    bottom-right corner. Free plan only (see WATERMARK_PLANS).

    Fails open: if moviepy/ffmpeg text rendering isn't available (e.g. no
    ImageMagick on the host), the original video is copied through
    unwatermarked rather than failing the job.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    font_path = _find_watermark_font()
    if not font_path:
        logger.warning("No usable font found for watermark, shipping unwatermarked video")
        if os.path.abspath(video_path) != os.path.abspath(output_path):
            with open(video_path, "rb") as src:
                data = src.read()
            with open(output_path, "wb") as dst:
                dst.write(data)
        return output_path
    try:
        from moviepy import CompositeVideoClip, TextClip, VideoFileClip

        video = VideoFileClip(video_path)
        margin = max(10, int(video.h * 0.02))
        watermark = (
            TextClip(
                font=font_path,
                text=WATERMARK_TEXT,
                font_size=max(14, int(video.h * 0.035)),
                color="white",
                stroke_color="black",
                stroke_width=1,
            )
            .with_opacity(0.55)
            .with_duration(video.duration)
        )
        watermark = watermark.with_position(
            (video.w - watermark.w - margin, video.h - watermark.h - margin)
        )
        final = CompositeVideoClip([video, watermark])
        final.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
        video.close()
        watermark.close()
        final.close()
    except Exception as exc:
        logger.warning("Watermark rendering failed, shipping unwatermarked video: %s", exc)
        if os.path.abspath(video_path) != os.path.abspath(output_path):
            with open(video_path, "rb") as src:
                data = src.read()
            with open(output_path, "wb") as dst:
                dst.write(data)
    return output_path


def _parse_aspect_ratio(ratio: str) -> tuple:
    """Parse '9:16' / '1:1' into (w, h) floats. Raises ValueError if invalid."""
    parts = (ratio or "").strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid aspect ratio: {ratio!r}")
    w, h = float(parts[0]), float(parts[1])
    if w <= 0 or h <= 0:
        raise ValueError(f"Invalid aspect ratio: {ratio!r}")
    return w, h


async def export_alternate_format(
    source_path: str,
    output_path: str,
    target_ratio: str,
) -> str:
    """Center-crop ``source_path`` to ``target_ratio`` and write ``output_path``.

    IMPORTANT LIMITATION: this is a *naive center crop*, not smart subject-
    aware reframing. Content near the edges of the original frame may be
    lost. Suitable for quick 9:16 / 1:1 exports from a finished 16:9 master
    without another MuAPI render.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    target_w, target_h = _parse_aspect_ratio(target_ratio)
    target = target_w / target_h

    # moviepy is sync/CPU-bound — run in a worker thread so the event loop
    # stays responsive during the export.
    def _crop() -> str:
        from moviepy import VideoFileClip

        clip = VideoFileClip(source_path)
        try:
            src_w, src_h = clip.w, clip.h
            src_ratio = src_w / src_h
            if abs(src_ratio - target) < 1e-3:
                # Already the right ratio — just remux/copy encode.
                cropped = clip
            elif src_ratio > target:
                # Source is wider than target → crop left/right (center).
                new_w = src_h * target
                x1 = (src_w - new_w) / 2
                cropped = clip.cropped(x1=x1, y1=0, width=new_w, height=src_h)
            else:
                # Source is taller than target → crop top/bottom (center).
                new_h = src_w / target
                y1 = (src_h - new_h) / 2
                cropped = clip.cropped(x1=0, y1=y1, width=src_w, height=new_h)

            cropped.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                logger=None,
            )
            if cropped is not clip:
                cropped.close()
        finally:
            clip.close()
        return output_path

    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _crop)


class Idea2VideoPipeline:
    def __init__(self, api_key: str, demo: bool = False):
        self.api_key = api_key
        self.demo = demo
        self.screenwriter = ScreenwriterAgent(demo=demo)
        self.image_gen = _make_image_generator(api_key, demo=demo)
        self.script2video = Script2VideoPipeline(api_key, demo=demo)

    async def _lock_character_portraits(
        self,
        characters: List[CharacterInScene],
        style: str = "Cinematic",
        character_portraits_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Generate one portrait per character for the entire drama (consistency lock).

        character_portraits_override: user-uploaded reference photo(s), keyed
        by character name. These are used as-is instead of generating a
        fresh AI portrait for that character — this is what lets a user
        upload their own face/character photo and have it appear consistently
        across every scene.
        """
        portraits: Dict[str, str] = dict(character_portraits_override or {})
        for char in characters:
            if not char.is_visible:
                continue
            if char.name in portraits:
                # Already supplied by the user — skip AI generation for this one.
                char.portrait_url = portraits[char.name]
                continue
            prompt = (
                f"Character portrait, {style} style. "
                f"{char.static_features}. {char.dynamic_features}. "
                f"Front-facing, neutral expression, studio lighting, high detail."
            )
            url = await self.image_gen.generate_image(prompt, aspect_ratio="1:1")
            portraits[char.name] = url
            char.portrait_url = url
        return portraits

    def _characters_from_script(self, script: DramaScript) -> List[CharacterInScene]:
        return [
            CharacterInScene(
                idx=i,
                name=c.name,
                static_features=c.description,
                dynamic_features="",
                is_visible=True,
            )
            for i, c in enumerate(script.characters)
        ]

    async def _assemble_final_drama(
        self,
        scene_paths: List[str],
        working_dir: str,
        progress_callback: Optional[Callable] = None,
        music_url: Optional[str] = None,
        plan: str = "free",
        is_cancelled: Optional[Callable[[], bool]] = None,
        dialogue_tracks: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Concatenate all scene videos, color-grade, add background music,
        burn dialogue captions (when tracks present), then watermark
        (Free plan only) — exactly once per drama.

        Cancel is checked BEFORE each step starts (concat / grade / music /
        subtitles / watermark). Once an ffmpeg/moviepy render has begun we
        intentionally do NOT abort mid-write — that would leave a half-baked
        file on disk.
        """
        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        os.makedirs(working_dir, exist_ok=True)

        # Before concatenate
        _check_cancel()
        if progress_callback:
            await progress_callback("assembly", "Concatenating scene videos", 85)

        concatenated_path = os.path.join(working_dir, "drama_concatenated.mp4")
        # Crossfade transitions are opt-in (MUSEFORGE_SCENE_TRANSITIONS) --
        # moviepy's "compose" mode they require is heavier on memory than
        # the default ffmpeg stream-copy path, so it stays off unless
        # explicitly enabled.
        if is_scene_transitions_enabled():
            await concatenate_videos_with_transitions(scene_paths, concatenated_path)
        else:
            await concatenate_videos(scene_paths, concatenated_path)

        # Before color grade
        _check_cancel()
        if progress_callback:
            await progress_callback("grade", "Applying color grade", 89)

        graded_path = os.path.join(working_dir, "drama_graded.mp4")
        await apply_color_grade(concatenated_path, graded_path)

        # Before music mix
        _check_cancel()
        if progress_callback:
            await progress_callback("music", "Adding background music", 93)

        with_music_path = os.path.join(working_dir, "drama_with_music.mp4")
        if dialogue_tracks:
            await add_background_music(
                graded_path,
                with_music_path,
                music_url,
                dialogue_tracks=dialogue_tracks,
                scene_paths=scene_paths,
            )
        else:
            await add_background_music(graded_path, with_music_path, music_url)

        # Burn captions only when dialogue tracks are actually present —
        # no extra ffmpeg work when dialogue is off / empty.
        video_for_final = with_music_path
        if dialogue_tracks:
            _check_cancel()
            if progress_callback:
                await progress_callback("subtitles", "Burning captions", 95)
            subtitled_path = os.path.join(working_dir, "drama_subtitled.mp4")
            await burn_subtitles(
                with_music_path,
                subtitled_path,
                dialogue_tracks,
                scene_paths=scene_paths,
            )
            video_for_final = subtitled_path

        final_path = os.path.join(working_dir, "drama_final.mp4")
        if plan in WATERMARK_PLANS:
            # Before watermark render
            _check_cancel()
            if progress_callback:
                await progress_callback("music", "Applying watermark", 97)
            await add_watermark(video_for_final, final_path)
        else:
            final_path = video_for_final
        return final_path

    async def write_script_only(
        self,
        idea: str,
        style: str = "Cinematic",
        num_scenes: int = 3,
        user_requirement: str = "",
        progress_callback: Optional[Callable] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        preset_characters: Optional[List[Dict[str, Any]]] = None,
    ) -> DramaScript:
        """Phase A: screenwriting only — no portraits / frames / video."""

        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        async def progress(stage: str, message: str, pct: float, data=None):
            if progress_callback:
                await progress_callback(stage, message, pct, data)

        _check_cancel()
        await progress("screenwriting", "Writing script", 5)
        return await self.screenwriter.write_script(
            idea,
            style,
            num_scenes,
            user_requirement,
            preset_characters=preset_characters,
        )

    async def continue_from_script(
        self,
        script: DramaScript,
        style: str = "Cinematic",
        director_style: str = "cinematic_balanced",
        user_requirement: str = "",
        aspect_ratio: str = "16:9",
        working_dir: str = "/tmp/museforge_drama",
        progress_callback: Optional[Callable] = None,
        music_url: Optional[str] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        character_portraits_override: Optional[Dict[str, str]] = None,
        music_enabled: bool = False,
        dialogue_enabled: bool = False,
        plan: str = "free",
        library_characters: Optional[List[Dict[str, Any]]] = None,
    ) -> dict:
        """Phase B: everything after screenwriting (portraits → scenes → assemble)."""
        os.makedirs(working_dir, exist_ok=True)

        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        async def progress(stage: str, message: str, pct: float, data=None):
            if progress_callback:
                await progress_callback(stage, message, pct, data)

        characters = self._characters_from_script(script)
        if not characters:
            characters = [
                CharacterInScene(
                    idx=0, name="Protagonist",
                    static_features="main character", dynamic_features="", is_visible=True,
                )
            ]

        # Apply library character features + portraits (Pro reuse path).
        lib_by_name: Dict[str, Dict[str, Any]] = {}
        for lib in library_characters or []:
            name = str(lib.get("name") or "").strip()
            if not name:
                continue
            lib_by_name[name] = lib
            url = str(lib.get("portrait_url") or "").strip()
            if url:
                character_portraits_override = dict(character_portraits_override or {})
                character_portraits_override.setdefault(name, url)

        for char in characters:
            lib = lib_by_name.get(char.name)
            if lib and lib.get("static_features"):
                char.static_features = str(lib["static_features"])

        # If the user uploaded a reference photo under a name that doesn't
        # match any character the screenwriter came up with, add it as its
        # own character rather than silently dropping the upload.
        if character_portraits_override:
            existing_names = {c.name for c in characters}
            for name in character_portraits_override:
                if name not in existing_names:
                    lib = lib_by_name.get(name) or {}
                    characters.append(
                        CharacterInScene(
                            idx=len(characters),
                            name=name,
                            static_features=str(
                                lib.get("static_features") or "uploaded reference photo"
                            ),
                            dynamic_features="",
                            is_visible=True,
                        )
                    )

        _check_cancel()
        await progress("portraits", "Locking character portraits for consistency", 10)
        portraits = await self._lock_character_portraits(
            characters, style, character_portraits_override=character_portraits_override
        )

        # Dynamic reference selection (adapted from ViMax's "previous
        # timeline" technique): as scenes progress, prefer each character's
        # MOST RECENTLY generated frame over the static locked portrait as
        # the identity reference for the next shot. This tracks drift in
        # outfit/pose/lighting across the story better than always pinning
        # to the first-ever portrait. Reset per call so retries/re-runs on
        # the same pipeline instance don't leak state from a prior attempt.
        # Starts empty -- the very first shot of the whole drama has no
        # entry yet, so it still falls back to the locked portrait exactly
        # as before.
        self._last_frame_by_character: Dict[str, str] = {}

        scene_paths: List[str] = []
        scene_results: List[Dict[str, Any]] = []
        dialogue_tracks: List[Dict[str, Any]] = []
        dialogue_requested = (
            dialogue_enabled and is_dialogue_enabled() and not self.demo
        )
        voice_gen = MuAPIVoiceGenerator(self.api_key, demo=self.demo) if dialogue_requested else None
        total_scenes = max(1, len(script.scenes))

        for idx, scene in enumerate(script.scenes):
            _check_cancel()
            base_pct = 15 + (idx / total_scenes) * 65
            scene_script = _scene_action(scene)
            scene_dialogue = _scene_dialogue(scene)

            async def scene_progress(stage, message, pct, data=None, _base=base_pct):
                scaled = _base + (pct / 100) * (65 / total_scenes)
                await progress(stage, message, scaled, data)

            scene_dir = os.path.join(working_dir, f"scene_{idx}")
            scene_result = await self.script2video.run(
                script=scene_script,
                characters=characters,
                user_requirement=user_requirement,
                style=style,
                working_dir=scene_dir,
                progress_callback=scene_progress,
                scene_idx=idx,
                character_portraits=portraits,
                director_style=director_style,
                aspect_ratio=aspect_ratio,
                is_cancelled=is_cancelled,
                plan=plan,
                setting_location=getattr(script, "setting_location", "") or "",
                setting_time_of_day=getattr(script, "setting_time_of_day", "") or "",
                setting_era=getattr(script, "setting_era", "") or "",
                has_dialogue=dialogue_requested and bool(scene_dialogue),
                last_frame_by_character=self._last_frame_by_character,
            )
            assembled_scene_index = None
            if scene_result.get("path"):
                scene_paths.append(scene_result["path"])
                assembled_scene_index = len(scene_paths) - 1

            if voice_gen is not None and scene_dialogue and assembled_scene_index is not None:
                _check_cancel()
                try:
                    generated_tracks = await voice_gen.generate_scene_dialogue(
                        scene_dialogue,
                        is_cancelled=is_cancelled,
                    )
                    for track in generated_tracks:
                        dialogue_tracks.append(
                            {**track, "scene_index": assembled_scene_index}
                        )
                except Exception as exc:
                    logger.warning(
                        "Scene %s dialogue failed, continuing without its voice layer: %s",
                        idx + 1,
                        exc,
                    )

            serialized_scene = scene.model_dump() if hasattr(scene, "model_dump") else scene
            scene_results.append(
                {"index": idx, "script": serialized_scene, "shots": scene_result.get("shots", [])}
            )

        _check_cancel()
        final_path: Optional[str] = None
        video_url: Optional[str] = None

        # Optional instrumental background music (Creator/Pro only — gated
        # server-side in api.py before music_enabled ever reaches here).
        # Best-effort: any failure is logged and the job continues without
        # music rather than crashing. Never triggered in demo mode.
        # Cancel is checked BEFORE the MuAPI call starts — once it has begun
        # we let it finish (or fail) rather than orphan a half-written track.
        if music_enabled and not self.demo and not music_url:
            _check_cancel()
            try:
                music_gen = _make_music_generator(self.api_key, demo=self.demo)
                music_url = await music_gen.generate_instrumental(mood=script.mood or "cinematic")
            except PipelineCancelled:
                raise
            except Exception as exc:
                logger.warning("Background music generation failed, continuing without music: %s", exc)
                music_url = None

        if self.demo or not scene_paths:
            await progress("assembly", "Assembling preview", 90)
            for scene in reversed(scene_results):
                shots = scene.get("shots") or []
                if shots and shots[-1].get("video_url"):
                    video_url = shots[-1]["video_url"]
                    break
        else:
            final_path = await self._assemble_final_drama(
                scene_paths,
                working_dir,
                progress_callback,
                music_url,
                plan,
                is_cancelled=is_cancelled,
                dialogue_tracks=dialogue_tracks,
            )
            # Persist final video to Supabase Storage (signed URL) when available.
            if final_path and os.path.isfile(final_path):
                from tools.supabase_storage import upload_video

                job_id = os.path.basename(os.path.normpath(working_dir))
                stored = await upload_video(final_path, job_id)
                if stored and stored != final_path and stored.startswith("http"):
                    video_url = stored
                    # Delete local final file only after a successful remote upload.
                    try:
                        os.unlink(final_path)
                    except OSError:
                        pass
                    final_path = stored
                else:
                    # Fail-open: never expose a raw disk path to the client —
                    # serve via the authenticated streaming endpoint instead.
                    # (A bare "/tmp/..." URL becomes "https://host/tmp/..." and 404s.)
                    job_id = os.path.basename(os.path.normpath(working_dir))
                    video_url = video_url or f"/api/jobs/{job_id}/video"

        await progress(
            "complete",
            "Drama generation complete",
            100,
            {"video_path": final_path, "video_url": video_url},
        )

        return {
            "title": script.title,
            "logline": script.logline,
            "mood": script.mood,
            "video_path": final_path,
            "video_url": video_url,
            "scene_count": len(scene_results),
            "duration_estimate": script.estimated_duration_seconds,
            "characters": [c.model_dump() for c in characters],
            "portraits": portraits,
            "scenes": scene_results,
            "director_style": director_style,
            "style": style,
            "aspect_ratio": aspect_ratio,
            "demo": self.demo,
            "music_enabled": bool(music_url) if not self.demo else False,
            "dialogue_enabled": bool(dialogue_tracks) if not self.demo else False,
            "plan": plan,
            "setting_location": getattr(script, "setting_location", "") or "",
            "setting_time_of_day": getattr(script, "setting_time_of_day", "") or "",
            "setting_era": getattr(script, "setting_era", "") or "",
        }

    async def run(
        self,
        idea: str,
        style: str = "Cinematic",
        director_style: str = "cinematic_balanced",
        user_requirement: str = "",
        num_scenes: int = 3,
        aspect_ratio: str = "16:9",
        working_dir: str = "/tmp/museforge_drama",
        progress_callback: Optional[Callable] = None,
        music_url: Optional[str] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        character_portraits_override: Optional[Dict[str, str]] = None,
        music_enabled: bool = False,
        dialogue_enabled: bool = False,
        plan: str = "free",
        preset_characters: Optional[List[Dict[str, Any]]] = None,
    ) -> dict:
        """Full end-to-end run (script + production). Default path unchanged."""
        script = await self.write_script_only(
            idea=idea,
            style=style,
            num_scenes=num_scenes,
            user_requirement=user_requirement,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
            preset_characters=preset_characters,
        )
        return await self.continue_from_script(
            script=script,
            style=style,
            director_style=director_style,
            user_requirement=user_requirement,
            aspect_ratio=aspect_ratio,
            working_dir=working_dir,
            progress_callback=progress_callback,
            music_url=music_url,
            is_cancelled=is_cancelled,
            character_portraits_override=character_portraits_override,
            music_enabled=music_enabled,
            dialogue_enabled=dialogue_enabled,
            plan=plan,
            library_characters=preset_characters,
        )
