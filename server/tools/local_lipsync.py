"""Optional, fail-open lip synchronisation against a self-hosted LatentSync.

Selected via MUSEFORGE_LIPSYNC_PROVIDER=local (default remains "muapi").

WHY A THIRD BACKEND. The two hosted ones bill per synced scene, and lip sync
is the one stage that is pure polish: it runs after the expensive generation
is already paid for, and every scene with a line pays again. On a self-hosted
LatentSync (bytedance/LatentSync, Apache-2.0) the marginal cost of a synced
scene is GPU seconds we are already renting, so the feature stops being the
thing a deployment turns off to protect its margin.

The second reason is the one the MuAPI module documents against itself: that
endpoint exposes no ``sync_mode``, so the pipeline has to measure the returned
clip and repair a trimmed tail after the fact. A service we run ourselves can
be told not to trim in the first place -- MUSEFORGE_LOCAL_LIPSYNC_SYNC_MODE is
forwarded on every request. The length guard in idea2video stays regardless:
it is cheap, it is shared with the other two providers, and a guard that only
runs when we expect trouble is a guard that has stopped being a guard.

THE CONTRACT this expects from the service, kept deliberately small so that a
LatentSync wrapper, a ComfyUI workflow endpoint or anything else can satisfy
it:

    POST {base}/lipsync
        JSON  {"video_url", "audio_url", "sync_mode"}   when both are URLs
        FORM  video=@file audio=@file sync_mode=...     when either is on disk
      -> {"video_url": "..."}            finished inline, or
      -> {"job_id": "..."}               poll for it

    GET {base}/lipsync/{job_id}
      -> {"status": "queued|processing|completed|failed",
          "video_url": "...", "error": "..."}

A relative ``video_url`` in either response is resolved against the base, so a
service that answers "/outputs/scene_2.mp4" needs no extra configuration.

WHAT THIS RETURNS is a URL, not a path, exactly like the hosted backends: the
caller hands the result straight to download_video(), which fetches over HTTP
(pipelines/script2video.download_video). Returning a filesystem path here
would read as success and then fail in the caller on every single scene.

Every failure path returns ``None`` rather than raising, for the same reason
the other two do: losing lip sync must cost mouth accuracy, never the job.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Callable, Optional
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)

#: Forwarded verbatim. "silence" pads the AUDIO to the video; the alternative
#: every hosted provider defaults to trims the VIDEO to the audio, which lets a
#: short line quietly shorten a scene the customer bought seconds of (see
#: interfaces/second_budget.py).
SYNC_MODE = os.environ.get("MUSEFORGE_LOCAL_LIPSYNC_SYNC_MODE", "silence")

DEFAULT_POLL_INTERVAL = 3.0

#: 3.0s x 240 = 12 minutes, matching the MuAPI backend. The number means
#: something different here and lands in the same place: there the ceiling is
#: how long a hosted request can queue before it is presumed lost, here it is
#: one clip's turn on one GPU. LatentSync is the slowest of the open models on
#: purpose -- it buys mouth interior, teeth and tongue detail with compute --
#: and a 5-8 second take on a single 4090 runs in minutes, not seconds.
DEFAULT_MAX_POLLS = 240

#: Seconds before a single HTTP call to the service is abandoned. Generous
#: because the submit call may block for the whole inference when the service
#: chooses to answer inline rather than hand back a job id.
REQUEST_TIMEOUT = float(os.environ.get("MUSEFORGE_LOCAL_LIPSYNC_TIMEOUT", "900"))

#: How many scenes may be inside the service at once.
#:
#: THIS IS NOT A TUNING KNOB, IT IS THE POINT. idea2video syncs scenes
#: CONCURRENTLY -- the wall clock is the slowest scene rather than the sum --
#: which is right against a hosted fleet and wrong against one GPU. Three
#: LatentSync runs sharing 16GB do not go three times faster; they go slower
#: than one at a time, and past a certain resolution they go out of memory and
#: fail all three, turning a fan-out that was designed to save time into a way
#: to lose every mouth in the drama at once. One in flight by default; raise it
#: only for a service that is itself a queue in front of several GPUs.
CONCURRENCY = max(1, int(os.environ.get("MUSEFORGE_LOCAL_LIPSYNC_CONCURRENCY", "1")))

#: Built on first use rather than at import so the semaphore belongs to the
#: loop that actually runs the jobs. Shared across instances on purpose: the
#: thing being rationed is the box, not the object.
_gpu_slot: Optional[asyncio.Semaphore] = None


def _slot() -> asyncio.Semaphore:
    global _gpu_slot
    if _gpu_slot is None:
        _gpu_slot = asyncio.Semaphore(CONCURRENCY)
    return _gpu_slot


def _is_url(value: str) -> bool:
    return str(value).startswith(("http://", "https://"))


class LocalLipsync:
    def __init__(self, base_url: str = "", demo: bool = False):
        self.demo = demo
        self.base_url = (
            base_url or os.environ.get("MUSEFORGE_LOCAL_LIPSYNC_URL", "")
        ).strip().rstrip("/")

    def available(self) -> bool:
        """Configured, not reachable.

        Deliberately does no health check. This is called synchronously on the
        job's own path, and a service that is up when asked and down two
        seconds later would pass it anyway -- so the honest answer here is
        "somewhere to send this", and an unreachable box is handled the way
        every other failure is: one warning, the unsynced take, the job lives.
        """
        return bool(self.base_url) and not self.demo

    def _absolute(self, url: str) -> str:
        """Resolve a possibly-relative result URL against the service base."""
        if not url:
            return ""
        if _is_url(url):
            return url
        return urljoin(self.base_url + "/", url.lstrip("/"))

    async def sync(
        self,
        video_path_or_url: str,
        audio_url: str,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Optional[str]:
        """Return a URL to the lip-synced clip, or None if it could not be done.

        Either input may be a local path or an http(s) URL, in any combination:
        the scene clip is always on disk at this point, while the voice track is
        a URL on the MuAPI voice backend and a LOCAL PATH on the ElevenLabs one
        (which returns bytes and writes them into the job directory). Anything
        on disk is posted as multipart; anything already addressable is passed
        by URL so the service fetches it without a round trip through here.
        """
        if not self.available() or not audio_url or not video_path_or_url:
            return None

        try:
            async with _slot():
                # Checked INSIDE the slot as well as before the work: a scene
                # can sit in this queue for minutes behind other scenes, and a
                # job cancelled while it waited should not then start a run.
                if is_cancelled and is_cancelled():
                    return None

                async with httpx.AsyncClient(
                    timeout=REQUEST_TIMEOUT, follow_redirects=True
                ) as client:
                    payload = await self._submit(
                        client, video_path_or_url, audio_url
                    )
                    if payload is None:
                        return None

                    synced_url = payload.get("video_url")
                    if synced_url:
                        return self._absolute(synced_url)

                    job_id = payload.get("job_id")
                    if not job_id:
                        logger.warning(
                            "Local lip sync answered with neither a video_url "
                            "nor a job_id: %s",
                            payload,
                        )
                        return None

                    return await self._await_result(client, job_id, is_cancelled)
        except Exception as exc:
            logger.warning(
                "Lip sync unavailable for this scene, using the unsynced clip: %s", exc
            )
            return None

    async def _submit(
        self, client: httpx.AsyncClient, video: str, audio: str
    ) -> Optional[dict]:
        """POST the pair and return the decoded response, or None."""
        endpoint = f"{self.base_url}/lipsync"

        files = {}
        opened = []
        data = {"sync_mode": SYNC_MODE}
        try:
            for field, value in (("video", video), ("audio", audio)):
                if _is_url(value):
                    data[f"{field}_url"] = value
                    continue
                if not os.path.isfile(value):
                    # Same shape as the hosted backends: a missing input is a
                    # skipped mouth, not an exception thrown through the job.
                    logger.warning(
                        "Local lip sync had no %s to send at %s, "
                        "keeping the unsynced take",
                        field,
                        value,
                    )
                    return None
                handle = open(value, "rb")
                opened.append(handle)
                files[field] = (os.path.basename(value), handle, "application/octet-stream")

            if files:
                resp = await client.post(endpoint, data=data, files=files)
            else:
                resp = await client.post(endpoint, json=data)
            resp.raise_for_status()
            return resp.json()
        finally:
            for handle in opened:
                try:
                    handle.close()
                except Exception:  # pragma: no cover - closing cannot fail a job
                    pass

    async def _await_result(
        self,
        client: httpx.AsyncClient,
        job_id: str,
        is_cancelled: Optional[Callable[[], bool]],
    ) -> Optional[str]:
        """Poll until the service finishes, fails, or the ceiling is reached."""
        status_url = f"{self.base_url}/lipsync/{job_id}"

        for _ in range(DEFAULT_MAX_POLLS):
            if is_cancelled and is_cancelled():
                await self._cancel(client, job_id)
                return None

            resp = await client.get(status_url)
            resp.raise_for_status()
            body = resp.json() or {}
            status = str(body.get("status") or "").lower()

            if status == "completed":
                synced_url = self._absolute(body.get("video_url") or "")
                if not synced_url:
                    logger.warning(
                        "Local lip sync %s completed with no video URL: %s",
                        job_id,
                        body,
                    )
                    return None
                return synced_url

            if status == "failed":
                logger.warning(
                    "Local lip sync %s failed: %s",
                    job_id,
                    body.get("error") or "no reason given",
                )
                return None

            await asyncio.sleep(DEFAULT_POLL_INTERVAL)

        logger.warning("Local lip sync %s timed out", job_id)
        await self._cancel(client, job_id)
        return None

    async def _cancel(self, client: httpx.AsyncClient, job_id: str) -> None:
        """Best effort. A service that does not implement it is not an error:
        this runs on a box we own, and the run ends when the process does."""
        try:
            await client.post(f"{self.base_url}/lipsync/{job_id}/cancel")
        except Exception as exc:
            logger.warning("Local lip sync cancel failed (already finishing?): %s", exc)
