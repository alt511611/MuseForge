"""MuAPI image generation with reference support for character consistency."""

import hashlib
import logging
import os
import re
from typing import Callable, Optional

from tools.muapi_client import (
    MuAPIClient,
    MuAPIError,
    is_reference_rejection,
    is_transient_inference_error,
    reference_count_ceiling,
)

logger = logging.getLogger(__name__)

# Pixel sizes for the PIXEL-shaped endpoints (flux-dev-image: `width` and
# `height`, two separate ints). Also used for demo placeholder URLs.
#
# These frames are the conditioning image for Kling image-to-video, which has
# no aspect ratio of its own -- fal's v3 schema has no such field -- so it
# reads its canvas off this picture. Anything handed to it below its own
# output resolution is upscaled and the softness is baked into every frame of
# the finished shot, so the video ratios sit at ~1.4MP.
#
# EVERY VALUE HERE MUST BE DIVISIBLE BY 64. That is flux-dev-image's own
# constraint, read off MuAPI's schema service: "The value must be divisible by
# 64, eg: 128...512, 576, 640...2048." The previous map was not: 864 is 13.5
# sixty-fourths, so the 16:9 and 9:16 rows were unusable on the one endpoint
# that reads pixels at all. Exact ratios that are also multiples of 64 exist
# but cost either detail (1024x768) or 2-3MP (2048x1152), so the video rows
# are within 0.5% of their ratio instead of exact; the opening frame is
# centre-cropped to the exact ratio downstream anyway.
#
# 1:1 is only ever the character portrait (a reference, never shown), so it
# stays at 1024 and costs nothing extra.
ASPECT_RATIO_MAP = {
    "1:1": {"width": 1024, "height": 1024},
    "16:9": {"width": 1600, "height": 896},
    "9:16": {"width": 896, "height": 1600},
    "4:3": {"width": 1536, "height": 1152},
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
    if width % 64 or height % 64:
        # Honoured anyway -- this is the escape hatch for endpoints that take
        # sizes flux-dev-image will not -- but said out loud, because the
        # failure mode is the quiet one: flux-dev-image does not refuse an
        # off-grid size, it renders its 1024x1024 default instead.
        logger.warning(
            "MUSEFORGE_IMAGE_WIDTH/HEIGHT %sx%s is not divisible by 64; "
            "flux-dev-image requires that and will fall back to its own "
            "1024x1024 default rather than refusing the request.",
            width,
            height,
        )
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
#: The Kontext family's field is `images_list`, a LIST. The numbers below are
#: that field's `maxItems`, read off MuAPI's own schema service
#: (GET /api/app/get-task-data?name=<endpoint> -- the document the playground
#: builds its form from), not inferred from behaviour.
#:
#: They used to be a guess of 4, and the guess was wrong in the expensive
#: direction: a three-reference frame is not trimmed, it is REFUSED outright
#: ("You must provide 1 or 2 image URLs"), and the whole scene then fell
#: through to a text-only fallback. Job a8d0766b-421 lost the set on all
#: three scenes that way.
#:
#: Override per endpoint with MUAPI_REFERENCE_CAPACITY_<SLUG> without a
#: deploy; the slug is upper-cased with non-alphanumerics turned into
#: underscores, so `flux-kontext-pro-i2i` reads
#: MUAPI_REFERENCE_CAPACITY_FLUX_KONTEXT_PRO_I2I.
REFERENCE_CAPACITY = {
    "flux-pulid": 1,
    # images_list.maxItems, read off MuAPI's schema service. They are NOT the
    # same across the family, which is why this is a table and not a constant:
    # the dev tier takes five times what the pro tier does.
    "flux-kontext-pro-i2i": 2,
    "flux-kontext-max-i2i": 2,
    "flux-kontext-dev-i2i": 10,
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


#: How an endpoint asks for its canvas. Read off MuAPI's schema service
#: (GET /api/app/get-task-data?name=<endpoint>), not guessed from names.
#:
#:   RATIO_SHAPE  {prompt, aspect_ratio, resolution}   flux-2-pro, flux-2-flex
#:   PIXEL_SHAPE  {prompt, width, height, num_images}  flux-dev-image
#:
#: Sending the wrong one is not an error you can see. flux-2-pro rejects the
#: request outright (400 at generation time); flux-dev-image accepts it,
#: ignores every field it does not recognise, and renders its 1024x1024
#: default -- a square frame on a 9:16 order that nothing downstream can get
#: the sides back for.
RATIO_SHAPE = "ratio"
PIXEL_SHAPE = "pixels"

ENDPOINT_SHAPES = {
    "flux-2-pro": RATIO_SHAPE,
    "flux-2-flex": RATIO_SHAPE,
    "flux-dev-image": PIXEL_SHAPE,
    "flux-2-dev": PIXEL_SHAPE,
}

#: What an endpoint nobody has recorded is assumed to be. PIXEL_SHAPE,
#: because it is the forgiving one: an endpoint that wanted a ratio and got
#: width/height fails loudly on the first call, where the reverse renders a
#: silently wrong canvas for as long as nobody measures a delivered frame.
DEFAULT_ENDPOINT_SHAPE = PIXEL_SHAPE


def endpoint_shape(endpoint: str) -> str:
    """Which payload shape this endpoint's schema declares.

    Overridable per endpoint with MUAPI_ENDPOINT_SHAPE_<SLUG>=ratio|pixels,
    for the same reason the endpoints themselves are env-swappable: a model
    can be pointed somewhere new without a deploy, and its shape has to be
    able to follow it.
    """
    slug = (endpoint or "").strip()
    env_key = "MUAPI_ENDPOINT_SHAPE_" + re.sub(r"[^A-Za-z0-9]", "_", slug).upper()
    override = (os.environ.get(env_key, "") or "").strip().lower()
    if override in (RATIO_SHAPE, PIXEL_SHAPE):
        return override
    if override:
        logger.warning(
            "%s=%r is not %r or %r; using the recorded shape for %r.",
            env_key, override, RATIO_SHAPE, PIXEL_SHAPE, slug,
        )
    return ENDPOINT_SHAPES.get(slug, DEFAULT_ENDPOINT_SHAPE)


#: The `aspect_ratio` enums, per endpoint, as the schema service lists them.
#: Every ratio this pipeline orders (1:1, 16:9, 9:16, 4:3) is in all of them;
#: the table exists so that pointing an endpoint somewhere new cannot send a
#: ratio the target has never heard of.
SUPPORTED_RATIOS = {
    "flux-2-pro": ("16:9", "9:16", "1:1", "4:3", "3:4", "2:3", "3:2"),
    "flux-2-flex": ("16:9", "9:16", "1:1", "4:3", "3:4", "2:3", "3:2"),
    "flux-kontext-pro-i2i": ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "16:21"),
    "flux-kontext-max-i2i": ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "16:21"),
    "flux-kontext-dev-i2i": ("16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "16:21"),
    "flux-pulid": ("16:9", "9:16", "1:1", "4:3", "3:4"),
}


def supported_ratio(endpoint: str, aspect_ratio: str) -> str:
    """``aspect_ratio`` if the endpoint takes it, else its own default.

    Falls back to "1:1" -- which every one of these endpoints declares as its
    default -- rather than passing a value through to be rejected. A wrong
    shape is recoverable downstream (the opening frame is conformed before the
    take is ordered); a refused request is not.
    """
    wanted = (aspect_ratio or "").strip()
    allowed = SUPPORTED_RATIOS.get((endpoint or "").strip())
    if not allowed or wanted in allowed:
        return wanted or "1:1"
    logger.warning(
        "%s does not take aspect_ratio %r (it takes %s); ordering 1:1 and "
        "letting the frame be conformed downstream.",
        endpoint, wanted, ", ".join(allowed),
    )
    return "1:1"


#: The `resolution` rung ordered from a RATIO_SHAPE endpoint.
#:
#: "1k" is the provider's own default and the cheaper rung ($0.032 vs $0.045
#: on flux-2-pro). "2k" is the quality knob, and it is a real one here: this
#: frame is the conditioning image Kling reads its canvas and its detail off,
#: so softness bought at this step is baked into every frame of the take.
DEFAULT_IMAGE_RESOLUTION = "1k"
IMAGE_RESOLUTIONS = ("1k", "2k")


def image_resolution() -> str:
    """Which resolution rung to order. MUSEFORGE_IMAGE_RESOLUTION=2k raises it."""
    value = (os.environ.get("MUSEFORGE_IMAGE_RESOLUTION", "") or "").strip().lower()
    if value in IMAGE_RESOLUTIONS:
        return value
    if value:
        logger.warning(
            "MUSEFORGE_IMAGE_RESOLUTION=%r is not one of %s; using %s.",
            value, ", ".join(IMAGE_RESOLUTIONS), DEFAULT_IMAGE_RESOLUTION,
        )
    return DEFAULT_IMAGE_RESOLUTION


#: MuAPI's documented bound on `positivePrompt`: a non-empty, non-whitespace
#: string of 2..3000 characters. Violating it is a 400 raised at GENERATION
#: time rather than on submit, so the job pays for the round trip and then
#: dies with a provider error the user cannot act on.
MAX_PROMPT_CHARS = 3000
MIN_PROMPT_CHARS = 2

#: Endpoints whose own schema declares a SHORTER prompt than the 3000 above.
#: flux-pulid's reads "Text prompt describing the image (max 1500
#: characters)", which is half the budget every caller here is written
#: against -- and PuLID is the default reference endpoint, so the frames most
#: likely to carry a long locked-character prompt are exactly the ones with
#: the smallest allowance.
ENDPOINT_PROMPT_LIMITS = {
    "flux-pulid": 1500,
}


def prompt_limit(endpoint: str = "") -> int:
    """The prompt ceiling for one endpoint, defaulting to MuAPI's 3000."""
    return ENDPOINT_PROMPT_LIMITS.get((endpoint or "").strip(), MAX_PROMPT_CHARS)


def clamp_prompt(prompt: str, endpoint: str = "") -> str:
    """Enforce the provider's prompt contract at the last possible moment.

    Callers are expected to build prompts that already fit (see
    pipelines/script2video.fit_image_prompt, which drops whole clauses by
    priority instead of cutting mid-sentence). This is the backstop for every
    OTHER caller -- character portraits, retakes, repair passes -- so that no
    code path can put a job in front of a 400 it could have prevented.

    ``endpoint`` selects the ceiling, because it is not the same everywhere.
    """
    limit = prompt_limit(endpoint)
    text = (prompt or "").strip()
    if len(text) < MIN_PROMPT_CHARS:
        # An empty prompt is a bug upstream, but failing the render on it
        # helps nobody: name the problem and render something.
        logger.error(
            "Image prompt was empty or too short (%d chars) — substituting a "
            "neutral prompt. Check the caller.", len(text),
        )
        return "a cinematic film still"
    if len(text) > limit:
        logger.warning(
            "Image prompt is %d chars, over %s's %d limit — truncating. "
            "The caller should be trimming by priority instead.",
            len(text), endpoint or "MuAPI", limit,
        )
        text = text[:limit].rsplit(" ", 1)[0]
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
        self, prompt: str, aspect_ratio: str, reference_url: str = None, *,
        endpoint: str = "",
    ) -> dict:
        """The text-to-image payload THIS endpoint's schema actually declares.

        There is no single shape. MuAPI's two text-to-image families disagree
        on how you ask for a canvas, and this method used to send a third
        shape that neither of them has:

        * ratio-shaped (flux-2-pro, flux-2-flex) -- `aspect_ratio` from a
          fixed enum, plus `resolution` of "1k" or "2k".
        * pixel-shaped (flux-dev-image) -- `width` and `height`, ints,
          divisible by 64, plus `num_images`.

        What went out instead was `size: "864*1536"` with
        `num_inference_steps`, `seed` and `guidance_scale`, none of which
        exists on either. flux-2-pro answered every single call with
        ``HTTP 400: Internal Error`` -- job a8d0766b-421 burned three
        portraits x three attempts before falling back -- and flux-dev-image
        quietly ignored the lot and rendered its 1024x1024 default, which is
        why a 9:16 order kept coming back square and losing 44% of its width
        to the correcting crop.

        ``reference_url`` is accepted and DROPPED for a pixel-shaped endpoint:
        flux-dev-image has no image input at all. Passing one used to set an
        `image` key that the endpoint discarded, so a fallback logged as
        carrying the reference was in fact a text-only render.
        """
        endpoint = (endpoint or self.IMAGE_ENDPOINT or "").strip()
        text = clamp_prompt(prompt, endpoint=endpoint)
        if endpoint_shape(endpoint) == RATIO_SHAPE:
            if reference_url:
                logger.warning(
                    "%s takes no reference image; rendering %r from the "
                    "prompt alone.", endpoint, reference_url,
                )
            return {
                "prompt": text,
                "aspect_ratio": supported_ratio(endpoint, aspect_ratio),
                "resolution": image_resolution(),
            }
        dims = resolve_dimensions(aspect_ratio)
        if reference_url:
            logger.warning(
                "%s is a text-to-image endpoint with no image input; the "
                "reference %r is being dropped and this frame will not be "
                "character-locked.", endpoint, reference_url,
            )
        return {
            "prompt": text,
            "width": dims["width"],
            "height": dims["height"],
            "num_images": 1,
        }

    # Aliases kept for call sites / tests.
    def _text_to_image_payload(self, prompt: str, aspect_ratio: str) -> dict:
        return self._size_payload(
            prompt, aspect_ratio, endpoint=self.IMAGE_ENDPOINT
        )

    def _legacy_size_payload(
        self, prompt: str, aspect_ratio: str, reference_url: str = None
    ) -> dict:
        return self._size_payload(
            prompt, aspect_ratio, reference_url,
            endpoint=self.LEGACY_SIZE_ENDPOINT,
        )

    def _build_payload(self, prompt: str, aspect_ratio: str, reference_url: str = None) -> dict:
        return self._legacy_size_payload(prompt, aspect_ratio, reference_url)

    async def generate_image(
        self,
        prompt: str,
        aspect_ratio: str = "1:1",
        is_cancelled=None,
        on_submitted: Optional[Callable[[str, str], None]] = None,
    ) -> str:
        if self.demo:
            return _demo_image_url(prompt, aspect_ratio)
        payload = self._text_to_image_payload(prompt, aspect_ratio)
        logger.info(
            "Sending %s request WITHOUT reference (prompt starts: %.80s)",
            self.IMAGE_ENDPOINT,
            prompt,
        )
        # Passed only when wired -- some tests substitute a fake
        # `client.generate` with no slot for this kwarg at all.
        primary_kwargs = (
            {"on_submitted": lambda rid: on_submitted(rid, self.IMAGE_ENDPOINT)}
            if on_submitted
            else {}
        )
        try:
            return await self.client.generate(
                self.IMAGE_ENDPOINT, payload, is_cancelled=is_cancelled, **primary_kwargs
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
            fallback_kwargs = (
                {"on_submitted": lambda rid: on_submitted(rid, self.LEGACY_SIZE_ENDPOINT)}
                if on_submitted
                else {}
            )
            return await self.client.generate(
                self.LEGACY_SIZE_ENDPOINT,
                fallback_payload,
                is_cancelled=is_cancelled,
                **fallback_kwargs,
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
        on_submitted: Optional[Callable[[str, str], None]] = None,
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
        edit_kwargs = (
            {"on_submitted": lambda rid: on_submitted(rid, self.EDIT_ENDPOINT)}
            if on_submitted
            else {}
        )
        return await self.client.generate(
            self.EDIT_ENDPOINT, payload, is_cancelled=is_cancelled, **edit_kwargs
        )

    async def generate_image_with_reference(
        self,
        prompt: str,
        references,
        aspect_ratio: str = "16:9",
        is_cancelled=None,
        on_submitted: Optional[Callable[[str, str], None]] = None,
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
                prompt, aspect_ratio, is_cancelled=is_cancelled, on_submitted=on_submitted
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
        prompt = clamp_prompt(prompt, endpoint=endpoint)
        if "pulid" in endpoint.lower():
            # PuLID is identity-focused and uses a singular reference URL.
            payload = {
                "prompt": prompt,
                "image_url": used[0],
                "aspect_ratio": supported_ratio(endpoint, aspect_ratio),
            }
        else:
            # Kontext family (e.g. flux-kontext-dev-i2i, flux-kontext-pro-i2i)
            # expects a LIST of reference images under "images_list", capped
            # at that endpoint's own maxItems (see REFERENCE_CAPACITY).
            payload = {
                "prompt": prompt,
                "images_list": list(used),
                "aspect_ratio": supported_ratio(endpoint, aspect_ratio),
            }
        logger.info(
            "Sending %s request with %d reference(s) (prompt starts: %.80s)",
            endpoint,
            len(used),
            prompt,
        )
        ref_kwargs = (
            {"on_submitted": lambda rid, _ep=endpoint: on_submitted(rid, _ep)}
            if on_submitted
            else {}
        )
        try:
            return await self.client.generate(
                endpoint, payload, is_cancelled=is_cancelled, **ref_kwargs
            )
        except MuAPIError as exc:
            # The provider counted the images and said how many it takes. That
            # number beats our capacity table, which is the thing that was
            # wrong: obey it here and the frame keeps the references it is
            # allowed, instead of dropping to an endpoint that reads one.
            ceiling = reference_count_ceiling(exc)
            if (
                ceiling is not None
                and ceiling < len(used)
                and "images_list" in payload
            ):
                logger.warning(
                    "%s refused %d reference(s) and named a ceiling of %d; "
                    "resending with the first %d. Set "
                    "MUAPI_REFERENCE_CAPACITY_%s=%d to stop paying for this "
                    "round trip on every frame.",
                    endpoint,
                    len(used),
                    ceiling,
                    ceiling,
                    re.sub(r"[^A-Za-z0-9]", "_", endpoint).upper(),
                    ceiling,
                )
                payload["images_list"] = list(used[:ceiling])
                return await self.client.generate(
                    endpoint, payload, is_cancelled=is_cancelled, **ref_kwargs
                )
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

            # There is no reference to keep here, whatever the reason was.
            # The fallback endpoint is a TEXT-to-image model -- flux-dev-image
            # declares {prompt, width, height, num_images} and has no image
            # input at all -- so the old "falling back to ... reference
            # payload" log line was describing a key the provider discarded.
            # The frame comes back unlocked either way; the honest thing is to
            # say so, because "the reference survived the fallback" is the
            # belief that stops anyone investigating why the faces drifted.
            logger.warning(
                "%s failed (schema_rejection=%s, runtime_failure=%s, "
                "reference_rejected=%s): %s; falling back to %s, which takes "
                "no reference — this frame will NOT be character-locked.",
                endpoint,
                is_schema_rejection,
                is_runtime_failure,
                is_ref_rejected,
                exc,
                self.LEGACY_SIZE_ENDPOINT,
            )
            fallback_payload = self._legacy_size_payload(prompt, aspect_ratio)
            unlocked_kwargs = (
                {"on_submitted": lambda rid: on_submitted(rid, self.LEGACY_SIZE_ENDPOINT)}
                if on_submitted
                else {}
            )
            return await self.client.generate(
                self.LEGACY_SIZE_ENDPOINT,
                fallback_payload,
                is_cancelled=is_cancelled,
                **unlocked_kwargs,
            )
