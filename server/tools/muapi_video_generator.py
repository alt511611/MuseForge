"""MuAPI image-to-video generation (Kling v3.0 Pro / Standard)."""

import logging
import os
from typing import Any, Dict, Optional

from tools.muapi_client import MuAPIClient, MuAPIError

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
    # code change (render.yaml / docker-compose.yml both declare it).
    "https://test-videos.co.uk/vids/bigbuckbunny/mp4/h264/360/Big_Buck_Bunny_360_10s_1MB.mp4"
)

# Confirmed MuAPI playground endpoints: Pro vs Standard is the endpoint
# itself, not a `mode` field inside one shared payload.
PRO_ENDPOINT = os.environ.get(
    "MUAPI_VIDEO_MODEL_PRO", "kling-v3.0-pro-image-to-video"
)
STANDARD_ENDPOINT = os.environ.get(
    "MUAPI_VIDEO_MODEL_STANDARD", "kling-v3.0-standard-image-to-video"
)


def endpoint_for_plan(plan: str) -> str:
    return PRO_ENDPOINT if (plan or "").lower() == "pro" else STANDARD_ENDPOINT


def is_native_audio_enabled() -> bool:
    """Whether to ask Kling to generate its own audio track.

    OFF by default, because that audio is unconditionally DISCARDED further
    down the pipeline: concatenate_videos() passes ``-an`` (and the moviepy
    fallback writes ``audio=False``), then add_background_music() lays the
    real score and dialogue over a silent picture. Requesting it only spent
    generation time and credits on a track no viewer could ever hear.

    Kept behind a flag rather than deleted so native Kling audio can be
    switched on the day the assembly step is taught to keep it.
    """
    return os.environ.get("MUSEFORGE_KLING_NATIVE_AUDIO", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _is_endpoint_rejected(exc: Exception) -> bool:
    """True when MuAPI likely rejected the endpoint (404/422)."""
    msg = str(exc).lower()
    if "404" in msg or "422" in msg:
        return True
    if "status_code=404" in msg or "status_code=422" in msg:
        return True
    return False


# Kept for any legacy callers / older Kling enums (5 or 10 only).
# New v3.0 path uses clamp_duration() instead.
VALID_DURATIONS = (5, 10)


def nearest_valid_duration(seconds) -> int:
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return VALID_DURATIONS[0]
    return min(VALID_DURATIONS, key=lambda d: abs(d - seconds))


def clamp_duration(seconds) -> int:
    """Kling v3.0 accepts integer duration 3–15 (default 5)."""
    try:
        value = int(round(float(seconds)))
    except (TypeError, ValueError):
        return 5
    return max(3, min(15, value))


class MuAPIVideoGenerator:
    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)

    def _payload(
        self,
        prompt: str,
        image_url: str,
        duration: int,
        generate_audio: bool = True,
        last_image: Optional[str] = None,
        endpoint: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the payload for ONE endpoint, carrying only fields it accepts.

        Every model used to get the kling-v3.0 payload verbatim. MuAPI
        validates, so `generate_audio` — which only the Kling v3.0 family
        declares — comes back from a Seedance or Veo endpoint as a 422, which
        the fallback chain reads as "this endpoint does not exist" and demotes
        to Standard. A routed model would have been configured, charged for in
        expectation, and never once actually run.
        """
        from tools.video_model_router import (
            accepts_aspect_ratio,
            optional_fields,
            send_duration,
        )

        target = endpoint or endpoint_for_plan("free")
        allowed = optional_fields(target)

        payload: Dict[str, Any] = {"prompt": prompt, "image_url": image_url}
        if "duration" in allowed:
            # The endpoint's own declaration decides both halves: whether
            # there is a field (`allowed`) and what may go in it
            # (`send_duration`). Endpoints do not agree about the second --
            # Kling takes any integer 3..15, MuAPI's veo3.1 takes 8 and
            # nothing else -- and sending a Kling-shaped 6 or 10 to Veo is a
            # 422 the fallback chain misreads as a missing endpoint.
            sent = send_duration(target, duration)
            if sent is not None:
                payload["duration"] = sent
        if "generate_audio" in allowed:
            payload["generate_audio"] = generate_audio
        if "last_image" in allowed and last_image:
            payload["last_image"] = last_image
        # Kling i2v derives aspect from the source image and has no such field;
        # Seedance and Veo do take one, and left unset they can letterbox a
        # vertical frame back to 16:9.
        # ...and an endpoint that takes the field may still not take THIS
        # value: Veo's enum is 16:9 and 9:16, while this product also sells
        # 1:1. Omitting it lets the model fall back to its own default rather
        # than rejecting the call.
        if "aspect_ratio" in allowed and aspect_ratio:
            if accepts_aspect_ratio(target, aspect_ratio):
                payload["aspect_ratio"] = aspect_ratio
        return payload

    async def generate_video_from_image(
        self,
        prompt: str,
        image_url: str,
        duration: int = 5,
        aspect_ratio: str = "16:9",
        plan: str = "free",
        is_cancelled=None,
        shot_profile: Optional[str] = None,
        last_image: Optional[str] = None,
    ) -> str:
        """Animate ``image_url``; land on ``last_image`` when one is given.

        ``last_image`` is the acted PEAK of the shot (see interfaces/acting).
        Given both ends, the Kling v3.0 family interpolates between them, so
        the expression change is something the model must physically perform
        rather than something the prompt merely asks for.

        It is passed to every endpoint in the chain and dropped by ``_payload``
        for the ones whose schema has no such field -- the turbo variants take
        prompt/image_url/duration and nothing else, so a shot that demotes to
        turbo simply animates from its start frame. That is a silent quality
        loss, not a failure, and it is the right trade: a 422 here would cost
        the whole shot.
        """
        if self.demo:
            return DEMO_VIDEO_URL

        from tools.video_model_router import STANDARD as STANDARD_PROFILE
        from tools.video_model_router import is_routing_active, model_chain
        from interfaces.video_backend import is_declared

        profile = shot_profile or STANDARD_PROFILE
        chain = model_chain(profile, plan)
        # Without this, a chain of [plan endpoint, standard] is indistinguishable
        # in the logs from "an operator pinned a specialist and it resolved to
        # the same place" -- which is the first question asked when a routed
        # model appears not to be running.
        logger.info(
            "Shot profile=%r routed to %s (routing %s)",
            profile,
            chain,
            "configured" if is_routing_active() else "not configured",
        )

        # Walk the chain: a routed specialist first, the plan's endpoint next,
        # Standard last. Only endpoint-level rejections (404/422 -- "this model
        # does not exist here" / "it does not take this payload") are worth
        # trying the next link for; a cancellation or a genuine generation
        # failure would fail identically on every model and re-running it would
        # just spend the customer's time and credits three times over.
        last_exc: Optional[MuAPIError] = None
        for position, endpoint in enumerate(chain):
            # Built per endpoint, not once for the chain: the links do not share
            # a schema, which is the whole reason a demotion has to change the
            # payload as well as the URL.
            payload = self._payload(
                prompt,
                image_url,
                duration,
                generate_audio=is_native_audio_enabled(),
                last_image=last_image,
                endpoint=endpoint,
                aspect_ratio=aspect_ratio,
            )
            try:
                return await self.client.generate(
                    endpoint,
                    payload,
                    poll_interval=3.0,
                    max_polls=200,
                    is_cancelled=is_cancelled,
                )
            except MuAPIError as exc:
                last_exc = exc
                is_last = position == len(chain) - 1
                if is_last or not _is_endpoint_rejected(exc):
                    raise
                # A 404 and a 422 both demote, and they mean opposite things.
                # 404 is "this build knows a slug this vendor does not have",
                # which is a configuration question. 422 from an endpoint we
                # DECLARED is "the payload we built from our own declaration
                # was refused", which is a bug in
                # interfaces/video_backend.BACKENDS -- and it is the failure
                # this whole registry exists to prevent, so it must not read
                # like routine fallback noise.
                #
                # Still fail-open: a shot is worth more than a correct log.
                if is_declared(endpoint) and "422" in str(exc):
                    logger.error(
                        "%r refused a payload built from its own declaration "
                        "(fields sent: %s). interfaces/video_backend.BACKENDS "
                        "is wrong about this endpoint -- check its schema in "
                        "the playground. Demoting to %r so the shot survives, "
                        "but the routed model is not running: %s",
                        endpoint,
                        sorted(payload),
                        chain[position + 1],
                        exc,
                    )
                else:
                    logger.warning(
                        "MuAPI rejected endpoint=%r for profile=%r (%s); falling back to %r",
                        endpoint,
                        profile,
                        exc,
                        chain[position + 1],
                    )
        # Unreachable: the loop either returns or raises on its last link.
        raise last_exc or MuAPIError("No video endpoint configured")
