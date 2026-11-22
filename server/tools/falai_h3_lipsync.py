"""Optional, fail-open "talking close-up" via fal.ai MiniMax H3 Max Lip Sync.

Selected via MUSEFORGE_LIPSYNC_PROVIDER=falai_h3 (default stays "muapi").

THIS ONE DOES NOT CORRECT A MOUTH, IT REDRAWS THE TAKE. Every other lip-sync
backend takes the finished scene clip and edits the lower face of the frames it
was given. This endpoint takes ONE still and the audio and generates a new
clip whose length is the audio's. So the scene is redrawn from its first frame:
the face, wardrobe and set are the still's, the head and body move the way the
model thinks someone saying these words moves, and any action the original take
had is gone. That is the right trade for a single speaker in a close-up, which
is the shot lip sync is for (idea2video._speaks_in_a_readable_framing already
refuses framings too wide to read a mouth in, and _has_one_visible_speaker
refuses a two-hander); it is the wrong one for a scene whose point is what
happens around the speaker. Hence opt-in.

Why it exists, measured 2026-11-22 on one Turkish line over one 768P close-up
(one experiment, n=1, identity and sync judged by mouth-region motion
against the audio envelope plus a look at the frames):

    route      wall clock    mouth ~ audio (r)
    h3 lip     18 s          +0.59
    sync v2    80 s          +0.17     (the take it was given: -0.11)
    sync v3    66 s          +0.11
    kling      206 s         +0.21     (and it cut 0.5 s off the line)

The three that edit the given frames stayed close to the clip they were handed;
this one followed the voice. It also held the face, headband and set -- but
turned a frightened take into an angry one, which is what "redraws" costs.

Three things this module has to do that the sibling backends do not:

* Hand over a STILL. The first frame of the clip it was given is cut with
  ffmpeg and uploaded. That is why the scene's opening has to be the face you
  want: the pipeline's own first frame is.
* Pad the audio to the endpoint's floor. The schema asks for at least 5 s of
  audio; a short line is padded with silence rather than refused, so the mouth
  rests after the words, which is also what a person does.
* Return a clip the SIZE of the scene. The endpoint draws "the supported aspect
  ratio nearest the image" at its own pixel size (1344x768 for a 16:9 source
  that was 1280x720), and concatenate_videos copies packets on the assumption
  that every clip shares dimensions. A clip in another size would corrupt the
  join, so a mismatch is scaled-to-cover and cropped to the source's size and
  re-uploaded before it is returned.

Same contract as the other backends -- ``sync(video, audio, is_cancelled,
on_submitted) -> url | None`` and every failure path returns None: lip sync is
polish after the expensive generation is already paid for, and losing it must
cost a mouth, never the job. Length is NOT handled here; idea2video's guard
trims or restores whatever comes back, exactly as for the others.

Price: $0.05/0.08/0.16/0.32 per second at 480P/768P/1080P/2K (1.2x past 15 s),
billed on the AUDIO's length. A 10 s scene at 768P is about $0.80, against
$0.50 on sync v2 -- but it replaces the sync, it does not add to a clip you
would otherwise have paid to improve.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Any, Callable, Optional, Tuple

from tools.falai_common import fal_generate, make_fal_client

logger = logging.getLogger(__name__)

ENDPOINT_DEFAULT = "minimax/h3-max/lip-sync/image-to-video"

#: The schema: "at least 5 seconds long".
MIN_AUDIO_SECONDS = 5.0
VALID_RESOLUTIONS = ("480P", "768P", "1080P", "2K")
DEFAULT_RESOLUTION = "768P"
TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}


def _resolution() -> str:
    """FALAI_H3_LIPSYNC_RESOLUTION, case-insensitively, or 768P. An unknown
    value falls back: it is a 422 on every scene otherwise."""
    raw = (os.environ.get("FALAI_H3_LIPSYNC_RESOLUTION", "") or "").strip()
    for known in VALID_RESOLUTIONS:
        if raw.lower() == known.lower():
            return known
    return DEFAULT_RESOLUTION


def _transcription() -> bool:
    """FALAI_H3_LIPSYNC_TRANSCRIPTION. On by default (the endpoint's own); turn
    it off for audio that is mostly music or laughter, which a transcript turns
    into words nobody said."""
    raw = (os.environ.get("FALAI_H3_LIPSYNC_TRANSCRIPTION", "") or "").strip().lower()
    return raw not in FALSY


async def _run(*args: str) -> Tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, _ = await process.communicate()
    return process.returncode or 0, stdout.decode("utf-8", "ignore").strip()


async def _probe_seconds(path_or_url: str) -> float:
    code, out = await _run(
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path_or_url
    )
    try:
        return float(out) if code == 0 else 0.0
    except ValueError:
        return 0.0


async def _probe_size(path_or_url: str) -> Tuple[int, int]:
    code, out = await _run(
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
        "stream=width,height", "-of", "csv=p=0:s=x", path_or_url,
    )
    try:
        width, height = out.splitlines()[0].split("x")
        return (int(width), int(height)) if code == 0 else (0, 0)
    except (ValueError, IndexError):
        return 0, 0


async def _first_frame(video: str, out_path: str) -> bool:
    code, _ = await _run("ffmpeg", "-v", "error", "-y", "-i", video, "-frames:v", "1", out_path)
    return code == 0 and os.path.isfile(out_path)


async def _pad_audio(audio: str, out_path: str, seconds: float) -> bool:
    """Silence after the words until the file is ``seconds`` long."""
    code, _ = await _run(
        "ffmpeg", "-v", "error", "-y", "-i", audio, "-af", f"apad=whole_dur={seconds}",
        "-t", str(seconds), out_path,
    )
    return code == 0 and os.path.isfile(out_path)


async def _conform(video: str, size: Tuple[int, int], out_path: str) -> bool:
    """Scale to cover ``size`` and crop, so the join never meets a stranger."""
    width, height = size
    code, _ = await _run(
        "ffmpeg", "-v", "error", "-y", "-i", video,
        "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1",
        "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", out_path,
    )
    return code == 0 and os.path.isfile(out_path)


class _Reporting:
    """Wraps a fal client so the request id is announced the moment it exists.

    fal_generate owns the poll, the cancel, the content-flag retry and the
    timeout; it does not know about the job ledger, which charges lip sync per
    scene up front and has to learn the ticket before a crash mid-poll can lose
    track of it. Announcing from ``submit`` keeps that without a second poll
    loop.
    """

    def __init__(self, client: Any, on_submitted: Optional[Callable[[str], None]]):
        self._client = client
        self._on_submitted = on_submitted

    async def submit(self, endpoint: str, arguments: Optional[dict] = None, **kwargs: Any):
        handle = await self._client.submit(endpoint, arguments=arguments, **kwargs)
        if self._on_submitted:
            try:
                self._on_submitted(handle.request_id)
            except Exception as exc:
                logger.warning(
                    "on_submitted callback failed for %s request_id=%s; continuing without it: %s",
                    endpoint, handle.request_id, exc,
                )
        return handle

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


class FalAIH3Lipsync:
    #: Read by idea2video's account-lock tracking. Same vendor and account as
    #: the Sync Lipsync backend, so a fal.ai refusal is one lock, not two.
    provider_name = "falai"

    def __init__(self, api_key: str = "", demo: bool = False):
        self.demo = demo
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        # Like the Sync backend, an unconfigured deployment renders without
        # lip sync rather than failing every job that has dialogue.
        self.client = make_fal_client(self.api_key, demo=not self.api_key)

    @property
    def endpoint(self) -> str:
        return os.environ.get("FALAI_H3_LIPSYNC_MODEL", "").strip() or ENDPOINT_DEFAULT

    def available(self) -> bool:
        return bool(self.api_key) and not self.demo

    async def sync(
        self,
        video_path_or_url: str,
        audio_url: str,
        is_cancelled: Optional[Callable[[], bool]] = None,
        on_submitted: Optional[Callable[[str], None]] = None,
    ) -> Optional[str]:
        """A URL to the redrawn, scene-sized clip, or None to keep the take."""
        if not self.available() or not audio_url or not video_path_or_url:
            return None

        workdir = tempfile.mkdtemp(prefix="h3_lipsync_")
        try:
            if not str(video_path_or_url).startswith(("http://", "https://")) and not os.path.isfile(
                video_path_or_url
            ):
                return None

            frame_path = os.path.join(workdir, "first_frame.png")
            if not await _first_frame(video_path_or_url, frame_path):
                logger.warning("H3 lip sync: could not cut a first frame from the scene clip.")
                return None
            image_url = await self.client.upload_file(frame_path)

            # The audio can be a local path (the direct ElevenLabs voice writes
            # bytes into the job dir), which fal cannot fetch.
            audio_source = audio_url
            audio_is_url = str(audio_url).startswith(("http://", "https://"))
            if not audio_is_url and not os.path.isfile(audio_url):
                return None
            seconds = await _probe_seconds(audio_source)
            if 0.0 < seconds < MIN_AUDIO_SECONDS:
                padded = os.path.join(workdir, "audio_padded.mp3")
                if await _pad_audio(audio_source, padded, MIN_AUDIO_SECONDS):
                    audio_source, audio_is_url = padded, False
            if not audio_is_url:
                audio_source = await self.client.upload_file(audio_source)

            result = await fal_generate(
                _Reporting(self.client, on_submitted),
                self.endpoint,
                {
                    "image_url": image_url,
                    "audio_url": audio_source,
                    "resolution": _resolution(),
                    "enable_transcription": _transcription(),
                },
                is_cancelled=is_cancelled,
            )
            video_url = ((result or {}).get("video") or {}).get("url")
            if not video_url:
                logger.warning("H3 lip sync completed with no video URL: %s", result)
                return None

            return await self._at_the_scenes_size(video_path_or_url, video_url, workdir)
        except Exception as exc:
            logger.warning("H3 lip sync unavailable for this scene, using the unsynced clip: %s", exc)
            return None
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    async def _at_the_scenes_size(self, source: str, video_url: str, workdir: str) -> Optional[str]:
        """``video_url`` untouched when it already matches ``source``'s size,
        otherwise a conformed copy re-uploaded. None when the size cannot be
        made to match: a clip in another size breaks the join, so keeping the
        original take is the safe answer."""
        want = await _probe_size(source)
        got = await _probe_size(video_url)
        if want == (0, 0) or got == (0, 0):
            # Unmeasurable: not worth discarding a paid clip over. The same
            # fail-open the length guard uses.
            logger.warning("H3 lip sync: could not measure sizes (%s vs %s); returning as is.", want, got)
            return video_url
        if want == got:
            return video_url
        conformed = os.path.join(workdir, "conformed.mp4")
        if not await _conform(video_url, want, conformed):
            logger.warning("H3 lip sync: %s clip could not be conformed to %s; keeping the take.", got, want)
            return None
        logger.info("H3 lip sync: clip came back %sx%s, conformed to the scene's %sx%s.", *got, *want)
        return await self.client.upload_file(conformed)
