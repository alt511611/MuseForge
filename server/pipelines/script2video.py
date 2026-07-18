"""Per-scene script-to-video pipeline."""

import asyncio
import os
from typing import Any, Callable, Dict, List, Optional

import httpx

from agents.storyboard_artist import StoryboardArtist
from interfaces.character import CharacterInScene
from tools.muapi_image_generator import MuAPIImageGenerator
from tools.muapi_video_generator import MuAPIVideoGenerator
from tools.muapi_client import MuAPICancelled


class PipelineCancelled(Exception):
    """Raised cooperatively when a job is cancelled mid-flight."""


async def download_video(url: str, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
    return path


async def concatenate_videos(paths: List[str], out_path: str) -> str:
    """Concatenate video clips using moviepy, with a byte-copy fallback."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    try:
        from moviepy import VideoFileClip, concatenate_videoclips

        clips = [VideoFileClip(p) for p in paths]
        final = concatenate_videoclips(clips, method="compose")
        final.write_videofile(out_path, codec="libx264", audio=False, logger=None)
        for clip in clips:
            clip.close()
        final.close()
    except Exception:
        with open(out_path, "wb") as f:
            for p in paths:
                with open(p, "rb") as src:
                    f.write(src.read())
    return out_path


class Script2VideoPipeline:
    def __init__(self, api_key: str, demo: bool = False):
        self.api_key = api_key
        self.demo = demo
        self.image_gen = MuAPIImageGenerator(api_key, demo=demo)
        self.video_gen = MuAPIVideoGenerator(api_key, demo=demo)
        self.storyboard_artist = StoryboardArtist(demo=demo)

    async def run(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: str = "",
        style: str = "Cinematic",
        working_dir: str = "/tmp/museforge_scene",
        progress_callback: Optional[Callable] = None,
        scene_idx: int = 0,
        character_portraits: Optional[Dict[str, str]] = None,
        director_style: str = "cinematic_balanced",
        aspect_ratio: str = "16:9",
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        os.makedirs(working_dir, exist_ok=True)
        portraits = character_portraits or {}

        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        async def progress(stage: str, message: str, pct: float, data=None):
            if progress_callback:
                await progress_callback(stage, message, pct, data)

        _check_cancel()
        await progress("storyboard", f"Designing storyboard for scene {scene_idx + 1}", 10)
        shots = await self.storyboard_artist.design_storyboard(
            script, characters, user_requirement, director_style
        )

        shot_videos: List[Optional[str]] = [None] * len(shots)
        shot_meta: List[Optional[Dict[str, Any]]] = [None] * len(shots)
        completed_count = 0
        progress_lock = asyncio.Lock()

        # Frame + video generation for each shot are independent of every
        # OTHER shot (only frame->video within the same shot is
        # sequential) -- run shots concurrently instead of one-at-a-time.
        # Kling video generation alone can take 1-3+ minutes; 3 shots done
        # sequentially could take 10-15 minutes, while running them
        # concurrently caps wall-clock time near the slowest single shot.
        # Semaphore caps concurrent MuAPI requests so a multi-shot scene
        # doesn't fire a burst of simultaneous calls at the provider.
        semaphore = asyncio.Semaphore(int(os.environ.get("MUSEFORGE_SHOT_CONCURRENCY", "2")))

        async def _process_shot(i: int, shot) -> None:
            nonlocal completed_count
            async with semaphore:
                try:
                    _check_cancel()

                    reference_url = None
                    visible_chars = [c for c in characters if c.is_visible]
                    if visible_chars and portraits.get(visible_chars[0].name):
                        reference_url = portraits[visible_chars[0].name]

                    frame_prompt = (
                        f"{style} style. {shot.visual_desc}. "
                        f"Shot type: {shot.shot_type}. Lens: {shot.lens}."
                    )

                    async with progress_lock:
                        await progress("frames", f"Generating frame {i + 1}/{len(shots)}", 20 + i * 5)

                    if reference_url:
                        frame_url = await self.image_gen.generate_image_with_reference(
                            frame_prompt, reference_url, aspect_ratio, is_cancelled=is_cancelled
                        )
                    else:
                        frame_url = await self.image_gen.generate_image(
                            frame_prompt, aspect_ratio, is_cancelled=is_cancelled
                        )

                    shot.frame_url = frame_url

                    _check_cancel()
                    async with progress_lock:
                        await progress("video", f"Animating shot {i + 1}/{len(shots)}", 50 + i * 5)

                    video_url = await self.video_gen.generate_video_from_image(
                        prompt=shot.motion_desc,
                        image_url=frame_url,
                        duration=int(getattr(shot, "duration_seconds", 5.0)),
                        aspect_ratio=aspect_ratio,
                        is_cancelled=is_cancelled,
                    )
                except MuAPICancelled as exc:
                    # Translate the low-level "stopped polling mid-wait"
                    # signal into the pipeline-level cancellation exception
                    # that jobs.py already knows how to handle cleanly (as
                    # a clean "cancelled" job state, not a generic error).
                    raise PipelineCancelled(str(exc)) from exc
                shot.video_url = video_url
                shot_meta[i] = shot.model_dump() if hasattr(shot, "model_dump") else dict(vars(shot))

                if not self.demo:
                    local_path = os.path.join(working_dir, f"shot_{i}.mp4")
                    await download_video(video_url, local_path)
                    shot_videos[i] = local_path

                async with progress_lock:
                    completed_count += 1
                    await progress(
                        "video",
                        f"Completed shot {completed_count}/{len(shots)}",
                        50 + int(completed_count / len(shots) * 40),
                    )

        await asyncio.gather(*[_process_shot(i, shot) for i, shot in enumerate(shots)])

        shot_meta = [m for m in shot_meta if m is not None]
        shot_videos = [v for v in shot_videos if v is not None]

        primary_url = shot_meta[-1]["video_url"] if shot_meta else None

        if self.demo:
            await progress(
                "scene_complete", f"Scene {scene_idx + 1} complete", 100, {"url": primary_url}
            )
            return {"path": None, "url": primary_url, "shots": shot_meta}

        output_path = os.path.join(working_dir, "scene_output.mp4")
        if len(shot_videos) == 1:
            output_path = shot_videos[0]
        elif len(shot_videos) > 1:
            await concatenate_videos(shot_videos, output_path)

        await progress("scene_complete", f"Scene {scene_idx + 1} complete", 100, {"path": output_path})
        return {"path": output_path, "url": primary_url, "shots": shot_meta}
