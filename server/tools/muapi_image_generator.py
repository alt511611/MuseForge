"""MuAPI image generation with reference support for character consistency."""

import hashlib
import logging
import os
import re

from tools.muapi_client import (
    MuAPIClient,
    MuAPIError,
    is_reference_rejection,
    is_transient_inference_error,
)

logger = logging.getLogger(__name__)

# Pixel sizes for flux-2-pro / flux-dev-image style "size" payloads
# (e.g. "1024*1024"). Also used for demo placeholder URLs.
#
# These frames are the conditioning image for Kling image-to-video, which
# renders at its own (higher) output resolution -- so anything we hand it
# below that gets upscaled, and the softness is baked into every frame of the
# finished shot. The video ratios are therefore ~1.3MP rather than the old
# ~1.0MP, which buys real detail while staying inside the range FLUX renders
# reliably; pushing to a full 1920x1080 (2.07MP) sits at the edge of that
# range and is left to MUSEFORGE_IMAGE_WIDTH/HEIGHT for anyone whose endpoint
# handles it. 1:1 is only ever the character portrait (a reference, never
# shown), so it stays at 1024 and costs nothing extra.
ASPECT_RATIO_MAP = {
    "1:1": {"width": 1024, "height": 1024},
    "16:9": {"width": 1536, "height": 864},
    "9:16": {"width": 864, "height": 1536},
    "4:3": {"width": 1344, "height": 1008},
}


def resolve_dimensions(aspect_ratio: str) -> dict:
    """Pixel size for an aspect ratio, with an explicit env override.

    MUSEFORGE_IMAGE_WIDTH/HEIGHT override every ratio -- an escape hatch for
    endpoints that comfortably render above the default ~1.3MP. Both must be
    set and valid, otherwise the mapped default stands (a half-configured or
    typo'd override must not silently produce a broken payload).
    """
    dims = ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"])
    raw_w = os.environ.get("MUSEFORGE_IMAGE_WIDTH", "").strip()
    raw_h = os.environ.get("MUSEFORGE_IMAGE_HEIGHT", "").strip()
    if not (raw_w and raw_h):
        return dims
    try:
        width, height = int(raw_w), int(raw_h)
    except ValueError:
        logger.warning(
            "Invalid MUSEFORGE_IMAGE_WIDTH/HEIGHT (%r x %r), using %s default",
            raw_w,
            raw_h,
            aspect_ratio,
        )
        return dims
    if width <= 0 or height <= 0:
        logger.warning(
            "Non-positive MUSEFORGE_IMAGE_WIDTH/HEIGHT (%s x %s), using %s default",
            width,
            height,
            aspect_ratio,
        )
        return dims
    return {"width": width, "height": height}


#: How many reference images each endpoint actually USES, by endpoint slug.
#:
#: This is a capability, not a preference, and being wrong about it is silent
#: in both directions. Send four images to flux-pulid and three are ignored
#: with no error and no log line -- the frame is drawn from a quarter of its
#: evidence and looks like a model failure. Send one to an endpoint that
#: wanted the whole set and the other faces in the frame are invented from the
#: prompt's text description, which is the delivered failure this map exists
#: to end (job 4c7bbe85-e5c: two characters, six frames, six locks, and the
#: unlocked half of every frame came back as a different person).
#:
#: PuLID is 1 by construction: it is an IDENTITY model and its payload field
#: is the singular `image_url`. That number is certain.
#:
#: The Kontext family's field is `images_list`, a LIST -- confirmed against
#: MuAPI's own 422 ({"loc": ["body", "images_list"]}). What is NOT confirmed
#: is where its ceiling sits, so the number below is a starting point to be
#: checked in the playground, not a measurement. Raise or lower it per
#: endpoint with MUAPI_REFERENCE_CAPACITY_<SLUG> without a deploy; the slug is
#: upper-cased with non-alphanumerics turned into underscores, so
#: `flux-kontext-pro-i2i` reads MUAPI_REFERENCE_CAPACITY_FLUX_KONTEXT_PRO_I2I.
REFERENCE_CAPACITY = {
    "flux-pulid": 1,
    "flux-kontext-pro-i2i": 4,
    "flux-kontext-dev-i2i": 4,
    "flux-kontext-max-i2i": 4,
}

#: What an endpoint nobody has measured is assumed to take. One, because the
#: conservative direction here is the one that cannot invent a face: a model
#: that would have accepted four gets its anchor and draws the rest from the
#: prompt, which is exactly today's behaviour.
DEFAULT_REFERENCE_CAPACITY = 1


def reference_capacity(endpoint: str) -> int:
    """How many references this endpoint will actually read."""
    slug = (endpoint or "").strip()
    env_key = "MUAPI_REFERENCE_CAPACITY_" + re.sub(r"[^A-Za-z0-9]", "_", slug).upper()
    override = (os.environ.get(env_key, "") or "").strip()
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            logger.warning(
                "%s=%r is not a number; using the built-in capacity for %r.",
                env_key, override, slug,
            )
    return REFERENCE_CAPACITY.get(slug, DEFAULT_REFERENCE_CAPACITY)


def normalise_references(references) -> list:
    """A clean, ordered, de-duplicated reference list from str | sequence | None.

    Order is meaning, not presentation: index 0 is the identity ANCHOR, and a
    single-reference endpoint gets exactly that one. Everything after it is
    supporting evidence -- the other faces in the frame, then the set.
    """
    if not references:
        return []
    if isinstance(references, str):
        references = [references]
    seen, ordered = set(), []
    for item in references:
        url = (item or "").strip() if isinstance(item, str) else ""
        if url and url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


#: MuAPI's documented bound on `positivePrompt`: a non-empty, non-whitespace
#: string of 2..3000 characters. Violating it is a 400 raised at GENERATION
#: time rather than on submit, so the job pays for the round trip and then
#: dies with a provider error the user cannot act on.
MAX_PROMPT_CHARS = 3000
MIN_PROMPT_CHARS = 2


def clamp_prompt(prompt: str) -> str:
    """Enforce the provider's prompt contract at the last possible moment.

    Callers are expected to build prompts that already fit (see
    pipelines/script2video.fit_image_prompt, which drops whole clauses by
    priority instead of cutting mid-sentence). This is the backstop for every
    OTHER caller -- character portraits, retakes, repair passes -- so that no
    code path can put a job in front of a 400 it could have prevented.
    """
    text = (prompt or "").strip()
    if len(text) < MIN_PROMPT_CHARS:
        # An empty prompt is a bug upstream, but failing the render on it
        # helps nobody: name the problem and render something.
        logger.error(
            "Image prompt was empty or too short (%d chars) — substituting a "
            "neutral prompt. Check the caller.", len(text),
        )
        return "a cinematic film still"
    if len(text) > MAX_PROMPT_CHARS:
        logger.warning(
            "Image prompt is %d chars, over MuAPI's %d limit — truncating. "
            "The caller should be trimming by priority instead.",
            len(text), MAX_PROMPT_CHARS,
        )
        text = text[:MAX_PROMPT_CHARS].rsplit(" ", 1)[0]
    return text


def _demo_image_url(prompt: str, aspect_ratio: str) -> str:
    """Deterministic placeholder image so the pipeline works with no API key."""
    dims = ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"])
    seed = hashlib.sha1(f"{prompt}|{aspect_ratio}".encode()).hexdigest()[:12]
    return f"https://picsum.photos/seed/{seed}/{dims['width']}/{dims['height']}"


class MuAPIImageGenerator:
    # Referanssız text-to-image: flux-2-pro (size "W*H" schema).
    # flux-3-text-to-image currently 404s on MuAPI (not live yet).
    IMAGE_ENDPOINT = os.environ.get("MUAPI_IMAGE_MODEL", "flux-2-pro")
    # Legacy size-based endpoint kept only as PuLID fail-open fallback.
    LEGACY_SIZE_ENDPOINT = os.environ.get(
        "MUAPI_IMAGE_FALLBACK_MODEL", "flux-dev-image"
    )
    # Default stays flux-pulid -- confirmed working against real videos, do
    # not change. Override via MUAPI_KONTEXT_MODEL (e.g. to the cheaper
    # "flux-kontext-dev-i2i" tier) to try a different reference-image model;
    # generate_image_with_reference() below picks the correct payload shape
    # for whichever endpoint is configured (PuLID vs. the Kontext family use
    # different reference-image field names).
    KONTEXT_ENDPOINT = os.environ.get(
        "MUAPI_KONTEXT_MODEL", "flux-pulid"
    )

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)

    def _size_payload(
        self, prompt: str, aspect_ratio: str, reference_url: str = None
    ) -> dict:
        """flux-2-pro / flux-dev-image style payload (combined size string)."""
        dims = resolve_dimensions(aspect_ratio)
        payload = {
            "prompt": clamp_prompt(prompt),
            "size": f"{dims['width']}*{dims['height']}",
            "num_inference_steps": 28,
            "seed": -1,
            "guidance_scale": 3.5,
            "num_images": 1,
        }
        if reference_url:
            payload["image"] = reference_url
        return payload

    # Aliases kept for call sites / tests.
    def _text_to_image_payload(self, prompt: str, aspect_ratio: str) -> dict:
        return self._size_payload(prompt, aspect_ratio)

    def _legacy_size_payload(
        self, prompt: str, aspect_ratio: str, reference_url: str = None
    ) -> dict:
        return self._size_payload(prompt, aspect_ratio, reference_url)

    def _build_payload(self, prompt: str, aspect_ratio: str, reference_url: str = None) -> dict:
        return self._size_payload(prompt, aspect_ratio, reference_url)

    async def generate_image(
        self, prompt: str, aspect_ratio: str = "1:1", is_cancelled=None
    ) -> str:
        if self.demo:
            return _demo_image_url(prompt, aspect_ratio)
        payload = self._text_to_image_payload(prompt, aspect_ratio)
        logger.info(
            "Sending %s request WITHOUT reference (prompt starts: %.80s)",
            self.IMAGE_ENDPOINT,
            prompt,
        )
        try:
            return await self.client.generate(
                self.IMAGE_ENDPOINT, payload, is_cancelled=is_cancelled
            )
        except MuAPIError as exc:
            message = str(exc).lower()
            is_schema_rejection = "404" in message or "422" in message
            # Shared with the video path via the client, because the shape of
            # a provider-side failure is the same whatever is being generated
            # -- and because this check had already missed one: a delivered
            # job died on `HTTP 400: Inference error occurred ... Please try
            # again`, which matched neither of the two strings that used to be
            # listed here and so was re-raised instead of falling back.
            is_runtime_failure = is_transient_inference_error(exc)
            if not (is_schema_rejection or is_runtime_failure):
                raise

            logger.warning(
                "%s failed (schema_rejection=%s, runtime_failure=%s): %s; "
                "falling back to %s",
                self.IMAGE_ENDPOINT,
                is_schema_rejection,
                is_runtime_failure,
                exc,
                self.LEGACY_SIZE_ENDPOINT,
            )
            fallback_payload = self._legacy_size_payload(prompt, aspect_ratio)
            return await self.client.generate(
                self.LEGACY_SIZE_ENDPOINT, fallback_payload, is_cancelled=is_cancelled
            )

    #: Image-to-image EDIT model, used only by :meth:`edit_image`.
    #:
    #: Deliberately NOT the same knob as KONTEXT_ENDPOINT. That one defaults to
    #: flux-pulid, which is an IDENTITY model: give it a photograph and a
    #: prompt and it returns the same face in a picture of its own choosing --
    #: new framing, new background, new light. That is exactly right for
    #: rendering a scene from a locked portrait, and exactly wrong for the end
    #: frame of an interpolation, where everything except the face must survive
    #: byte-for-byte or the video model morphs the whole image instead of the
    #: performance.
    EDIT_ENDPOINT = os.environ.get("MUSEFORGE_EDIT_MODEL", "flux-kontext-pro-i2i")

    async def edit_image(
        self,
        prompt: str,
        image_url: str,
        aspect_ratio: str = "16:9",
        is_cancelled=None,
    ) -> str:
        """Edit an existing image, keeping its composition.

        Raises on failure rather than falling back to a text-to-image or
        identity model: a "fallback" here would return a DIFFERENT picture of
        the same person, and handing that to Kling as an end frame produces a
        five-second warp between two unrelated compositions -- visibly worse
        than not having an end frame at all. The caller fails open by dropping
        the end frame entirely (see pipelines/script2video).
        """
        if self.demo:
            return _demo_image_url(prompt + "|edit", aspect_ratio)

        payload = {
            "prompt": clamp_prompt(prompt),
            # The Kontext family takes a LIST -- confirmed against MuAPI's own
            # 422 ({"loc": ["body", "images_list"]}), same as the reference
            # path below.
            "images_list": [image_url],
            "aspect_ratio": aspect_ratio,
        }
        logger.info(
            "Sending %s EDIT request (prompt starts: %.80s)",
            self.EDIT_ENDPOINT,
            prompt,
        )
        return await self.client.generate(
            self.EDIT_ENDPOINT, payload, is_cancelled=is_cancelled
        )

    async def generate_image_with_reference(
        self,
        prompt: str,
        references,
        aspect_ratio: str = "16:9",
        is_cancelled=None,
    ) -> str:
        """Render a frame from one or more reference images.

        ``references`` is a URL or an ORDERED sequence of them. Index 0 is the
        identity anchor and is the one a single-reference endpoint receives;
        everything after it is the rest of the evidence the frame is entitled
        to -- the other faces in the shot, then the set plate.

        It used to be a single string, and that was the shape of a real
        defect rather than a simplification: a two-hander gets one anchor, so
        exactly half of the faces in every frame of a two-character drama were
        drawn from a prose description instead of a picture. The list is
        trimmed to what the configured endpoint can actually read, and what
        was dropped is logged -- a reference that is silently ignored is
        indistinguishable from a model that ignored it.
        """
        if self.demo:
            return _demo_image_url(prompt + "|ref", aspect_ratio)

        endpoint = self.KONTEXT_ENDPOINT
        ordered = normalise_references(references)
        if not ordered:
            # No usable reference: this is the unreferenced path, and taking
            # it here beats sending `null` to a model that requires one.
            return await self.generate_image(
                prompt, aspect_ratio, is_cancelled=is_cancelled
            )

        capacity = reference_capacity(endpoint)
        used, dropped = ordered[:capacity], ordered[capacity:]
        if dropped:
            # The remedy differs by WHY the set was trimmed, and telling an
            # operator to raise a number that cannot be raised is worse than
            # saying nothing: flux-pulid takes one image because it is an
            # identity model, not because nobody has measured it.
            if "pulid" in endpoint.lower():
                remedy = (
                    "%s locks a single identity by construction; point "
                    "MUAPI_KONTEXT_MODEL at a multi-reference endpoint to use "
                    "the whole set." % endpoint
                )
            else:
                remedy = (
                    "Raise MUAPI_REFERENCE_CAPACITY_%s once the playground "
                    "confirms this endpoint takes more."
                    % re.sub(r"[^A-Za-z0-9]", "_", endpoint).upper()
                )
            logger.info(
                "%s reads %d reference(s); sent the anchor and %d more, held "
                "back %d. The held-back subjects are described in the prompt "
                "instead, which is what lets a second face in the frame come "
                "back as a different person. %s",
                endpoint,
                capacity,
                max(0, len(used) - 1),
                len(dropped),
                remedy,
            )

        # Reference-model payloads are built here rather than in
        # _size_payload, so they need the same clamp -- this is the path a
        # character-locked frame actually takes.
        prompt = clamp_prompt(prompt)
        if "pulid" in endpoint.lower():
            # PuLID is identity-focused and uses a singular reference URL.
            payload = {
                "prompt": prompt,
                "image_url": used[0],
                "aspect_ratio": aspect_ratio,
            }
        else:
            # Kontext family (e.g. flux-kontext-dev-i2i, flux-kontext-pro-i2i)
            # expects a LIST of reference images under "images_list" --
            # confirmed against MuAPI's own 422 validation error during an
            # earlier attempt ({"loc": ["body", "images_list"]}).
            payload = {
                "prompt": prompt,
                "images_list": list(used),
                "aspect_ratio": aspect_ratio,
            }
        logger.info(
            "Sending %s request with %d reference(s) (prompt starts: %.80s)",
            endpoint,
            len(used),
            prompt,
        )
        try:
            return await self.client.generate(
                endpoint,
                payload,
                is_cancelled=is_cancelled,
            )
        except MuAPIError as exc:
            message = str(exc).lower()
            is_schema_rejection = "404" in message or "422" in message
            # Shared with the video path via the client, because the shape of
            # a provider-side failure is the same whatever is being generated
            # -- and because this check had already missed one: a delivered
            # job died on `HTTP 400: Inference error occurred ... Please try
            # again`, which matched neither of the two strings that used to be
            # listed here and so was re-raised instead of falling back.
            is_runtime_failure = is_transient_inference_error(exc)
            # The provider read the portrait and refused it. Carrying the same
            # reference into the fallback endpoint would carry the refusal with
            # it, so this is the one case where the fallback drops it: the
            # scene renders unlocked rather than not at all.
            is_ref_rejected = is_reference_rejection(exc)
            if not (is_schema_rejection or is_runtime_failure or is_ref_rejected):
                raise

            logger.warning(
                "%s failed (schema_rejection=%s, runtime_failure=%s, "
                "reference_rejected=%s): %s; falling back to %s %s",
                endpoint,
                is_schema_rejection,
                is_runtime_failure,
                is_ref_rejected,
                exc,
                self.LEGACY_SIZE_ENDPOINT,
                "WITHOUT the reference" if is_ref_rejected else "reference payload",
            )
            fallback_payload = self._legacy_size_payload(
                prompt,
                aspect_ratio,
                # The legacy endpoint takes ONE reference; the anchor is the
                # one worth keeping when the set has to be given up.
                None if is_ref_rejected else used[0],
            )
            return await self.client.generate(
                self.LEGACY_SIZE_ENDPOINT,
                fallback_payload,
                is_cancelled=is_cancelled,
            )
