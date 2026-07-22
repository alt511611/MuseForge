"""Per-scene script-to-video pipeline."""

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional

import httpx

from agents.storyboard_artist import StoryboardArtist
from interfaces.character import CharacterInScene
from tools.character_qa import (
    format_expected_setting,
    is_character_qa_enabled,
    verify_frame,
)
from tools.muapi_image_generator import MuAPIImageGenerator
from tools.muapi_video_generator import MuAPIVideoGenerator
from tools.muapi_client import MuAPICancelled

logger = logging.getLogger(__name__)


class PipelineCancelled(Exception):
    """Raised cooperatively when a job is cancelled mid-flight."""


def build_frame_prompt(
    style: str,
    shot,
    setting_location: str = "",
    setting_time_of_day: str = "",
    setting_era: str = "",
    has_dialogue: bool = False,
) -> str:
    """Build the image prompt for a shot, injecting locked setting when present.

    Empty setting fields (legacy/demo scripts) keep the old prompt shape —
    no bare "Setting: , ." fragment.
    """
    parts = [
        p.strip()
        for p in (setting_location, setting_time_of_day, setting_era)
        if (p or "").strip()
    ]
    if parts:
        # Prefer "location, time_of_day" when both exist (user-requested shape).
        setting_clause = f"Setting: {', '.join(parts)}. "
    else:
        setting_clause = ""
    dialogue_clause = (
        "For this dialogue shot, the speaking character's mouth should be "
        "naturally obscured, shown in profile, or not be the focal point. "
        if has_dialogue
        else ""
    )
    return (
        f"{style} style. {setting_clause}{shot.visual_desc}. "
        f"{dialogue_clause}Shot type: {shot.shot_type}. Lens: {shot.lens}."
    )


async def download_video(url: str, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
    return path


async def concatenate_videos(paths: List[str], out_path: str) -> str:
    """Concatenate clips with low-memory fallbacks.

    Fast path uses ffmpeg's concat demuxer and stream-copy, which does not
    decode frames. If the clips are not codec-compatible, moviepy re-encodes
    them with ``method="chain"``. Raw byte-copy remains the last-resort,
    fail-open behavior.
    """
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    # 1) Native concat demuxer: near-zero memory because packets are copied
    # without decoding/re-encoding. This requires matching codecs/streams.
    concat_list_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            prefix="museforge_concat_",
            dir=os.path.dirname(out_path) or ".",
            delete=False,
            encoding="utf-8",
        ) as concat_file:
            concat_list_path = concat_file.name
            for path in paths:
                # ffmpeg concat-demuxer escaping for single quotes.
                escaped = os.path.abspath(path).replace("'", "'\\''")
                concat_file.write(f"file '{escaped}'\n")

        ffmpeg_binary = os.environ.get("MUSEFORGE_FFMPEG_BINARY") or shutil.which("ffmpeg")
        if not ffmpeg_binary:
            # Local dev/test environments may only have moviepy's bundled
            # imageio-ffmpeg binary; production Docker installs ffmpeg.
            try:
                import imageio_ffmpeg

                ffmpeg_binary = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ffmpeg_binary = "ffmpeg"

        process = await asyncio.create_subprocess_exec(
            ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-c",
            "copy",
            "-an",
            out_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode == 0 and os.path.isfile(out_path):
            return out_path
        logger.warning(
            "ffmpeg concat stream-copy failed (exit=%s), using moviepy chain: %s",
            process.returncode,
            stderr.decode("utf-8", errors="replace")[-1000:],
        )
    except Exception as exc:
        logger.warning("ffmpeg concat unavailable, using moviepy chain: %s", exc)
    finally:
        if concat_list_path:
            try:
                os.unlink(concat_list_path)
            except OSError:
                pass

    # Remove a partial ffmpeg output before either fallback writes it.
    try:
        os.unlink(out_path)
    except OSError:
        pass

    # 2) Re-encode fallback. All generated clips share dimensions/aspect ratio,
    # so chain avoids compose's memory-heavy canvas/compositing behavior.
    clips = []
    final = None
    try:
        from moviepy import VideoFileClip, concatenate_videoclips

        clips = [VideoFileClip(p) for p in paths]
        final = concatenate_videoclips(clips, method="chain")
        final.write_videofile(out_path, codec="libx264", audio=False, logger=None)
        return out_path
    except Exception as exc:
        logger.warning("moviepy chain concat failed, using raw byte-copy: %s", exc)
    finally:
        if final is not None:
            try:
                final.close()
            except Exception:
                pass
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

    # 3) Preserve the existing last-resort raw byte-copy fallback.
    try:
        with open(out_path, "wb") as f:
            for p in paths:
                with open(p, "rb") as src:
                    f.write(src.read())
    except Exception as exc:
        # Keep the pipeline fail-open even if a source disappears mid-copy.
        logger.error("raw concat fallback failed: %s", exc)
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
        plan: str = "free",
        setting_location: str = "",
        setting_time_of_day: str = "",
        setting_era: str = "",
        has_dialogue: bool = False,
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
            script,
            characters,
            user_requirement,
            director_style,
            setting_location=setting_location,
            setting_time_of_day=setting_time_of_day,
            setting_era=setting_era,
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
        qa_enabled = is_character_qa_enabled() and not self.demo
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        expected_setting = format_expected_setting(
            setting_location, setting_time_of_day, setting_era
        )

        async def _process_shot(i: int, shot) -> None:
            nonlocal completed_count
            async with semaphore:
                qa_result: Dict[str, Any] = {}
                try:
                    _check_cancel()

                    reference_url = None
                    matched_char = None
                    shot_text = f"{shot.visual_desc} {shot.motion_desc}".lower()
                    visible_chars = [c for c in characters if c.is_visible]

                    # Found via a real report of character-swap between
                    # scenes: previously this ALWAYS used visible_chars[0]
                    # (the first character in the list) as the reference
                    # portrait for every single shot, regardless of which
                    # character the shot's own text actually describes.
                    # Now: pick whichever known character's name appears
                    # FIRST (by text position, i.e. narrative order --
                    # "Sam looks at Maria" -> Sam is the subject) in this
                    # shot's own visual_desc/motion_desc.
                    named_matches = [
                        (shot_text.find(c.name.lower()), c)
                        for c in visible_chars
                        if c.name.lower() in shot_text
                    ]
                    if named_matches:
                        named_matches.sort(key=lambda pair: pair[0])
                        matched_char = named_matches[0][1]
                    elif visible_chars:
                        # No character name appears in this shot's text at
                        # all (e.g. a pure landscape/establishing shot) --
                        # fall back to the first visible character, same
                        # as the previous (unconditional) behavior.
                        matched_char = visible_chars[0]

                    if matched_char and portraits.get(matched_char.name):
                        reference_url = portraits[matched_char.name]

                    frame_prompt = build_frame_prompt(
                        style,
                        shot,
                        setting_location=setting_location,
                        setting_time_of_day=setting_time_of_day,
                        setting_era=setting_era,
                        has_dialogue=has_dialogue,
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

                    # Audit & targeted repair (adapted from Virginia Tech's
                    # "Audit & Repair" technique): on QA failure, fix the
                    # SPECIFIC reported issue with one corrective re-send
                    # rather than blindly regenerating the whole frame from
                    # scratch. Only character-referenced shots can be
                    # repaired this way (flux-pulid needs the reference
                    # image); a single repair attempt, fail-open throughout.
                    if qa_enabled and frame_url and anthropic_key:
                        char_desc = matched_char.static_features if matched_char else ""
                        qa_result = await verify_frame(
                            frame_url=frame_url,
                            expected_character_desc=char_desc,
                            expected_setting=expected_setting,
                            anthropic_api_key=anthropic_key,
                        )
                        qa_failed = not qa_result.get(
                            "character_ok", True
                        ) or not qa_result.get("setting_ok", True)
                        issue = (qa_result.get("issue") or "").strip()
                        if qa_failed and reference_url and issue:
                            _check_cancel()
                            repair_prompt = (
                                f"{frame_prompt} IMPORTANT CORRECTION: {issue}"
                            )
                            try:
                                frame_url = await self.image_gen.generate_image_with_reference(
                                    repair_prompt,
                                    reference_url,
                                    aspect_ratio,
                                    is_cancelled=is_cancelled,
                                )
                                shot.frame_url = frame_url
                            except Exception as exc:
                                # Fail-open: keep the original (flagged) frame
                                # rather than blocking the shot on a failed
                                # repair attempt.
                                logger.warning(
                                    "QA repair regeneration failed for shot %s, "
                                    "keeping original frame: %s",
                                    i,
                                    exc,
                                )

                    _check_cancel()
                    async with progress_lock:
                        await progress("video", f"Animating shot {i + 1}/{len(shots)}", 50 + i * 5)

                    video_url = await self.video_gen.generate_video_from_image(
                        prompt=shot.motion_desc,
                        image_url=frame_url,
                        duration=int(getattr(shot, "duration_seconds", 5.0)),
                        aspect_ratio=aspect_ratio,
                        plan=plan,
                        is_cancelled=is_cancelled,
                    )
                except MuAPICancelled as exc:
                    # Translate the low-level "stopped polling mid-wait"
                    # signal into the pipeline-level cancellation exception
                    # that jobs.py already knows how to handle cleanly (as
                    # a clean "cancelled" job state, not a generic error).
                    raise PipelineCancelled(str(exc)) from exc
                shot.video_url = video_url
                meta = shot.model_dump() if hasattr(shot, "model_dump") else dict(vars(shot))
                # Record which character was actually used as the reference
                # for this shot -- lets a future "inconsistency" report be
                # diagnosed from real data (was the wrong character matched,
                # or did MuAPI itself drift?) instead of guessing blind.
                meta["reference_character"] = matched_char.name if matched_char else None

                # QA/repair already ran above (before video generation) so a
                # detected issue could actually be fixed in the frame that
                # gets animated, instead of just reported after the fact.
                if qa_result:
                    if not qa_result.get("character_ok", True):
                        meta["character_qa_warning"] = True
                    if not qa_result.get("setting_ok", True):
                        meta["setting_qa_warning"] = True
                    if qa_result.get("issue"):
                        meta["qa_issue"] = qa_result["issue"]

                shot_meta[i] = meta

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
