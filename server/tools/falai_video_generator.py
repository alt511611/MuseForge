"""Alternative image-to-video provider: fal.ai's Kling O3 Pro model.

Selected via MUSEFORGE_VIDEO_PROVIDER=falai (default remains "muapi", the
existing MuAPIVideoGenerator path -- see _make_video_generator() in
pipelines/script2video.py). This module is only imported when that env
var is actually set to "falai", so the default path never needs fal-client
installed/importable.

Schema CONFIRMED against fal.ai's own docs
(https://fal.ai/models/fal-ai/kling-video/o3/pro/image-to-video/api):
    input:  prompt (str, optional), image_url (str, required),
            duration (str enum "3".."15", default "5" -- NOT the 5/10-only
            enum MuAPI's Kling O1 endpoint uses)
    output: {"video": {"url": "...", "file_name": ..., "file_size": ...,
             "content_type": ...}}

Polling follows the same submit -> poll status -> fetch result pattern (and
is_cancelled check between poll iterations) as tools/muapi_client.py, using
fal_client's AsyncClient directly (rather than its module-level
convenience functions) so the API key is scoped to this instance instead
of mutating process-wide environment state.
"""

import asyncio
import logging
import os
from typing import Callable, Optional

import fal_client

from tools.muapi_client import MuAPICancelled

logger = logging.getLogger(__name__)

# `or` (not a get() default): deployment files declare MUSEFORGE_DEMO_VIDEO
# as an optional passthrough, so it commonly arrives as an EMPTY string
# rather than unset -- and an empty demo URL breaks demo mode outright.
DEMO_VIDEO_URL = os.environ.get("MUSEFORGE_DEMO_VIDEO", "").strip() or (
    # The former default (Google's gtv-videos-bucket sample) started
    # returning 403 when that bucket was made private, which silently
    # broke demo mode: jobs completed but the "finished" video would not
    # play. Any third-party fixture can go the same way -- set
    # MUSEFORGE_DEMO_VIDEO in the deployment env to override without a
    # code change (deploy/coolify.env and docker-compose.yml both declare it).
    "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4"
)

MIN_DURATION_SECONDS = 3
MAX_DURATION_SECONDS = 15
DEFAULT_POLL_INTERVAL = 3.0
DEFAULT_MAX_POLLS = 200


def _duration_str(seconds) -> str:
    """Clamp to fal's supported 3-15s integer-string enum (unlike MuAPI's
    Kling O1 endpoint, this is NOT restricted to just 5 or 10)."""
    try:
        value = int(round(float(seconds)))
    except (TypeError, ValueError):
        value = 5
    value = max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, value))
    return str(value)


#: How one character/object element is written into the payload.
#:
#: Read off the endpoint's own 422, which is the only source that was ever
#: going to settle it. This first went out as `{"image_urls": [...], "name":
#: ...}` -- a guess, and flagged as one -- and came back:
#:
#:     Either frontal_image_url and reference_image_urls or video_url
#:     must be provided.
#:
#: So the real shape is a MAIN view plus up to three additional angles, or a
#: video instead of both. There is no `name` field at all, which is why the
#: cast clause in the prompt is not decoration: it is the only place the model
#: learns that @Element1 is Vera Kessler.
#:
#: And the voice is a `voice_id` -- an id from the backend's own voice library
#: -- not an uploaded sample. That is a real correction to the plan this was
#: built from, which assumed a 5-30 second clip could be attached: keeping a
#: film's cast through a native-audio take means MAPPING each character to one
#: of the backend's voices, which is a different job from generating speech
#: and is not done here yet. Without it the take still speaks; the model
#: chooses the voice.
def _element_payload(element) -> dict:
    frontal = (getattr(element, "frontal", "") or "").strip()
    if not frontal:
        # No main view: the endpoint rejects the whole request rather than
        # ignoring the element, so an empty one must never be sent.
        return {}
    references = [url for url in (getattr(element, "reference_images", []) or []) if url]
    # The two fields are not independent. A main view on its own is a 422 per
    # element -- "Either frontal_image_url and reference_image_urls or
    # video_url must be provided" -- so `reference_image_urls` is REQUIRED
    # alongside a frontal, and a cast holding one picture each (which is what
    # the portrait lock produces, sheet or not: one URL per character) failed
    # the whole take on it.
    #
    # With no second angle to offer, the frontal is its own reference. That is
    # not a trick played on a validator: the field means "further evidence
    # about this subject", and the one picture there is remains true evidence
    # about them. With MUSEFORGE_CHARACTER_SHEET on, that picture is a
    # four-view grid, so the angles are handed over anyway -- inside a single
    # image rather than across a list.
    payload = {
        "frontal_image_url": frontal,
        "reference_image_urls": references or [frontal],
    }
    voice_id = (getattr(element, "voice_id", "") or "").strip()
    if voice_id:
        payload["voice_id"] = voice_id
    return payload


class FalAIVideoGenerator:
    # Endpoint ID confirmed against fal.ai's own model page/API docs.
    ENDPOINT = os.environ.get(
        "FALAI_VIDEO_MODEL", "fal-ai/kling-video/o3/pro/image-to-video"
    )

    def __init__(self, api_key: str, demo: bool = False, multishot: bool = False):
        self.demo = demo
        #: Whether this instance renders a scene per generation rather than a
        #: shot per generation. Set from MUSEFORGE_VIDEO_PROVIDER, never
        #: inferred: see script2video.scene_take_backend.
        self.multishot = multishot
        # .strip() guards against a stray trailing newline/whitespace in the
        # env var value (easy to introduce when pasting into Coolify's
        # dashboard) which httpx/fal_client would otherwise send verbatim
        # in a request header, causing an opaque "Illegal header value".
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        if not self.api_key and not demo:
            # Found during a deep audit: constructing fal_client.AsyncClient
            # with key=None silently falls through to the SDK's own env-var
            # lookup, producing unpredictable (slow/unclear) failures deep
            # inside the first real network call instead of an immediate,
            # obvious error here -- exactly the invisible-failure pattern
            # this project has been bitten by repeatedly. Demo mode is
            # exempt since it never makes a real network call.
            raise RuntimeError(
                "FAL_KEY is not set (or is empty) -- cannot use "
                "MUSEFORGE_VIDEO_PROVIDER=falai without it. Set FAL_KEY in "
                "Coolify's environment, or switch back to \"muapi\"."
            )
        self.client = fal_client.AsyncClient(key=self.api_key or None)

    async def generate_video_from_image(
        self,
        prompt: str,
        image_url: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        plan: str = "free",
        is_cancelled: Optional[Callable[[], bool]] = None,
        shot_profile: Optional[str] = None,
        last_image: Optional[str] = None,
    ) -> str:
        # shot_profile is MuAPI-only routing (tools/video_model_router); this
        # backend exposes a single endpoint, so it is accepted and ignored
        # rather than left out, which would TypeError the shared call site.
        _ = shot_profile
        # aspect_ratio/plan kept in the signature for interchangeability
        # with MuAPIVideoGenerator; this model derives aspect ratio from
        # the source image and has no HD/standard mode split (yet).
        _ = aspect_ratio, plan
        if self.demo:
            return DEMO_VIDEO_URL

        payload = {
            "prompt": prompt,
            "image_url": image_url,
            "duration": _duration_str(duration),
        }
        # The acted peak (interfaces/acting), when the caller rendered one.
        # This endpoint's own docs describe exactly this use -- "taking a start
        # frame and an end frame, animating the transition between them" --
        # under `end_image_url`. Sent only when present, so the default payload
        # stays byte-identical to what this endpoint has always received.
        if last_image:
            payload["end_image_url"] = last_image

        return await self._run(payload, self.ENDPOINT, is_cancelled=is_cancelled)

    async def _run(
        self,
        payload: dict,
        endpoint: str,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> str:
        """Submit, poll and fetch one fal job. Shared by every render path here.

        Extracted when the multi-shot path arrived: the difference between
        animating one still and rendering a whole scene with cuts in it is
        entirely in the PAYLOAD, and duplicating ninety lines of polling to
        express that would have meant two places to fix the next time a
        cancellation or a content-policy error needed handling.
        """
        handle = await self.client.submit(endpoint, arguments=payload)
        request_id = handle.request_id

        for _ in range(DEFAULT_MAX_POLLS):
            if is_cancelled and is_cancelled():
                raise await self._cancel(request_id, endpoint)

            status = await self.client.status(endpoint, request_id, with_logs=False)
            logger.info(
                "fal.ai poll for %s: type=%s repr=%.300s",
                request_id,
                type(status).__name__,
                repr(status),
            )
            if isinstance(status, fal_client.Completed):
                if status.error:
                    raise RuntimeError(
                        f"fal.ai job {request_id} failed: {status.error}"
                    )
                break

            if is_cancelled and is_cancelled():
                raise await self._cancel(request_id, endpoint)
            await asyncio.sleep(DEFAULT_POLL_INTERVAL)
        else:
            raise TimeoutError(
                f"fal.ai job {request_id} timed out after "
                f"{DEFAULT_MAX_POLLS * DEFAULT_POLL_INTERVAL}s"
            )

        try:
            result = await self.client.result(endpoint, request_id)
        except Exception as exc:
            if "content_policy_violation" in str(exc):
                raise RuntimeError(
                    "fal.ai flagged this scene's content automatically "
                    "(often a false positive on fantasy/forest imagery). "
                    "Try regenerating -- a new character portrait may not "
                    "trigger the same flag."
                ) from exc
            raise

        video_url = ((result or {}).get("video") or {}).get("url")
        if not video_url:
            raise RuntimeError(f"fal.ai completed but no video URL in result: {result}")
        return video_url

    #: The endpoint that renders a whole scene in one generation.
    #:
    #: Deliberately a SECOND constant rather than a mode on ENDPOINT above:
    #: the two take different payloads (`image_url` against `start_image_url`,
    #: one prompt against a list) and a single slug with a branch inside it is
    #: how a caller ends up sending the wrong shape to the right URL.
    MULTISHOT_ENDPOINT = os.environ.get(
        "FALAI_MULTISHOT_VIDEO_MODEL",
        "fal-ai/kling-video/v3/standard/image-to-video",
    )

    async def host_image(self, path: str) -> str:
        """A local still, uploaded, as a URL this endpoint can read.

        The frame this pipeline hands the video model is normally a provider
        CDN link and needs no hosting. It needs it when the frame had to be
        CORRECTED first -- see script2video's conform of an opening frame
        that came back in the wrong shape -- because a corrected frame only
        exists on disk, and `start_image_url` is a URL.
        """
        if self.demo:
            return ""
        return await self.client.upload_file(path)

    async def generate_scene_take(
        self,
        take,
        is_cancelled: Optional[Callable[[], bool]] = None,
        generate_audio: bool = True,
        negative_prompt: str = "",
    ) -> str:
        """Render a whole scene -- its cuts included -- in ONE generation.

        ``take`` is an interfaces.scene_take.SceneTake: the beats in cut
        order, the elements the whole scene is locked to, and the length the
        backend has already agreed it can deliver.

        What this replaces, per scene, is one image generation and one video
        generation PER ANGLE, the concat that joined them, the timescale
        repair that concat needs, and -- when the take carries its own audio
        in the film's language -- the lip-sync pass over the result.
        """
        if self.demo:
            return DEMO_VIDEO_URL

        beats = take.multi_prompt()
        cast = take.cast_clause()
        if cast and beats:
            # Said once, at the top of the first beat: which token is whom.
            # The element object has NO name field, so this is the only place
            # the model learns that @Element1 is Vera Kessler -- and a model
            # handed `@Element1` beside a beat that reads "she deals" has to
            # guess which of two people that is.
            beats = [{**beats[0], "prompt": cast + beats[0]["prompt"]}] + list(beats[1:])

        payload = {
            "start_image_url": take.start_image,
            # Same integer-string enum as the sibling endpoint above; see
            # _duration_str.
            "duration": _duration_str(take.seconds),
            "generate_audio": bool(generate_audio),
        }
        if len(beats) > 1:
            payload["multi_prompt"] = beats
            # "customize" is what makes the shot list binding rather than a
            # suggestion; "intelligent" lets the model choose its own cuts,
            # which throws away the storyboard.
            payload["shot_type"] = "customize"
        else:
            # One beat is not a multi-shot request. Sending a one-item list
            # asks a multi-shot planner to plan nothing -- and `prompt` here is
            # a plain string, not the object `multi_prompt` takes.
            payload["prompt"] = beats[0]["prompt"] if beats else ""
        if take.end_image:
            payload["end_image_url"] = take.end_image
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        elements = [_element_payload(e) for e in take.elements]
        elements = [e for e in elements if e]
        if elements:
            payload["elements"] = elements

        logger.info(
            "fal multi-shot take: %ss, %d beat(s), %d element(s) on %s",
            payload["duration"],
            len(beats),
            len(elements),
            self.MULTISHOT_ENDPOINT,
        )
        return await self._run(
            payload, self.MULTISHOT_ENDPOINT, is_cancelled=is_cancelled
        )

    async def _cancel(
        self, request_id: str, endpoint: Optional[str] = None
    ) -> MuAPICancelled:
        """Best-effort remote cancel, then return (not raise) the exception
        the caller should raise -- lets the caller keep a single `raise`
        call site regardless of which cancellation check triggered it.
        Reuses MuAPICancelled (rather than a new exception type) so
        script2video.py's existing cancellation handling -- which already
        catches MuAPICancelled and translates it into PipelineCancelled --
        works unchanged for this provider too.
        """
        try:
            await self.client.cancel(endpoint or self.ENDPOINT, request_id)
        except Exception as exc:
            logger.warning("fal.ai cancel request failed (already finishing?): %s", exc)
        return MuAPICancelled(f"Job cancelled while polling fal.ai request {request_id}")
