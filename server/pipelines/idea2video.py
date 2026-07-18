"""Full idea-to-video orchestration pipeline."""

import logging
import os
from typing import Any, Callable, Dict, List, Optional

from agents.screenwriter import ScreenwriterAgent
from interfaces.character import CharacterInScene, DramaScript
from pipelines.script2video import (
    PipelineCancelled,
    Script2VideoPipeline,
    concatenate_videos,
    download_video,
)
from tools.muapi_image_generator import MuAPIImageGenerator

logger = logging.getLogger(__name__)

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


def _find_watermark_font() -> Optional[str]:
    for path in _WATERMARK_FONT_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    return None


async def add_background_music(
    video_path: str,
    output_path: str,
    music_url: Optional[str] = None,
) -> str:
    """Add background music to the final concatenated video (called once per drama)."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    try:
        from moviepy import AudioFileClip, VideoFileClip

        video = VideoFileClip(video_path)
        if music_url:
            audio = AudioFileClip(music_url).with_duration(video.duration)
            final = video.with_audio(audio)
        else:
            final = video
        final.write_videofile(output_path, codec="libx264", audio_codec="aac", logger=None)
        video.close()
        if music_url:
            audio.close()
        final.close()
    except Exception:
        with open(video_path, "rb") as src:
            data = src.read()
        with open(output_path, "wb") as dst:
            dst.write(data)
    return output_path


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


class Idea2VideoPipeline:
    def __init__(self, api_key: str, demo: bool = False):
        self.api_key = api_key
        self.demo = demo
        self.screenwriter = ScreenwriterAgent(demo=demo)
        self.image_gen = MuAPIImageGenerator(api_key, demo=demo)
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
    ) -> str:
        """Concatenate all scene videos, add background music, then watermark
        (Free plan only) — exactly once per drama."""
        os.makedirs(working_dir, exist_ok=True)

        if progress_callback:
            await progress_callback("assembly", "Concatenating scene videos", 85)

        concatenated_path = os.path.join(working_dir, "drama_concatenated.mp4")
        await concatenate_videos(scene_paths, concatenated_path)

        if progress_callback:
            await progress_callback("music", "Adding background music", 93)

        with_music_path = os.path.join(working_dir, "drama_with_music.mp4")
        await add_background_music(concatenated_path, with_music_path, music_url)

        final_path = os.path.join(working_dir, "drama_final.mp4")
        if plan in WATERMARK_PLANS:
            if progress_callback:
                await progress_callback("music", "Applying watermark", 97)
            await add_watermark(with_music_path, final_path)
        else:
            final_path = with_music_path
        return final_path

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
        plan: str = "free",
    ) -> dict:
        os.makedirs(working_dir, exist_ok=True)

        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        async def progress(stage: str, message: str, pct: float, data=None):
            if progress_callback:
                await progress_callback(stage, message, pct, data)

        _check_cancel()
        await progress("screenwriting", "Writing script", 5)
        script = await self.screenwriter.write_script(idea, style, num_scenes, user_requirement)

        characters = self._characters_from_script(script)
        if not characters:
            characters = [
                CharacterInScene(
                    idx=0, name="Protagonist",
                    static_features="main character", dynamic_features="", is_visible=True,
                )
            ]

        # If the user uploaded a reference photo under a name that doesn't
        # match any character the screenwriter came up with, add it as its
        # own character rather than silently dropping the upload.
        if character_portraits_override:
            existing_names = {c.name for c in characters}
            for name in character_portraits_override:
                if name not in existing_names:
                    characters.append(
                        CharacterInScene(
                            idx=len(characters), name=name,
                            static_features="uploaded reference photo",
                            dynamic_features="", is_visible=True,
                        )
                    )

        _check_cancel()
        await progress("portraits", "Locking character portraits for consistency", 10)
        portraits = await self._lock_character_portraits(
            characters, style, character_portraits_override=character_portraits_override
        )

        scene_paths: List[str] = []
        scene_results: List[Dict[str, Any]] = []
        total_scenes = max(1, len(script.scenes))

        for idx, scene_script in enumerate(script.scenes):
            _check_cancel()
            base_pct = 15 + (idx / total_scenes) * 65

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
            )
            if scene_result.get("path"):
                scene_paths.append(scene_result["path"])
            scene_results.append(
                {"index": idx, "script": scene_script, "shots": scene_result.get("shots", [])}
            )

        _check_cancel()
        final_path: Optional[str] = None
        video_url: Optional[str] = None

        # Optional instrumental background music (Creator/Pro only — gated
        # server-side in api.py before music_enabled ever reaches here).
        # Best-effort: any failure is logged and the job continues without
        # music rather than crashing. Never triggered in demo mode.
        if music_enabled and not self.demo and not music_url:
            try:
                from tools.muapi_music_generator import MuAPIMusicGenerator

                music_gen = MuAPIMusicGenerator(self.api_key, demo=self.demo)
                music_url = await music_gen.generate_instrumental(mood=script.mood or "cinematic")
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
                scene_paths, working_dir, progress_callback, music_url, plan
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
                    # Fail-open / demo: keep serving the local path.
                    video_url = video_url or final_path

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
            "plan": plan,
        }
