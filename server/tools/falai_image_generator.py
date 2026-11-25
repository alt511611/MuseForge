"""fal.ai FLUX image generation — optional alternative to MuAPIImageGenerator.

Selected via MUSEFORGE_IMAGE_PROVIDER=falai (default remains "muapi").

Schemas CONFIRMED against fal.ai's own docs:

1) Text-to-image (generate_image) — fal-ai/flux-pro/v1.1
   https://fal.ai/models/fal-ai/flux-pro/v1.1/api
   input:  prompt (str, required),
           image_size (enum square_hd|square|portrait_4_3|portrait_16_9|
                       landscape_4_3|landscape_16_9 OR {width,height}),
           num_images, output_format, ...
   output: {"images": [{"url": "...", ...}, ...], ...}

2) Image-to-image / character reference (generate_image_with_reference)
   — fal-ai/flux-pro/kontext
   https://fal.ai/models/fal-ai/flux-pro/kontext/api
   input:  prompt (str, required),
           image_url (str, required) — singular reference image,
           aspect_ratio (enum 21:9|16:9|4:3|3:2|1:1|2:3|3:4|9:16|9:21),
           guidance_scale, num_images, output_format, ...
   output: {"images": [{"url": "...", ...}, ...], ...}

3) Multi-reference image-to-image (generate_image_with_reference, multiref=True)
   — fal-ai/flux-2-pro/edit, selected via MUSEFORGE_IMAGE_PROVIDER=falai_multiref
   https://fal.ai/models/fal-ai/flux-2-pro/edit/api
   input:  prompt (str, required),
           image_urls (list[str], required) — the WHOLE ordered reference set,
           image_size (enum, same set as flux-pro/v1.1, or {width,height}),
           seed, output_format, ...
   output: {"images": [{"url": "...", ...}, ...], "seed": ...}

4) Nano Banana reference frames + FLUX.3 sheets
   — google/nano-banana-2.1/edit for reference frames and
   blackforestlabs/flux-3/text-to-image for text-to-image, selected via
   MUSEFORGE_IMAGE_PROVIDER=falai_nanobanana
   https://fal.ai/models/google/nano-banana-2.1/edit
   https://fal.ai/models/blackforestlabs/flux-3/text-to-image
   edit input: prompt (str, required), image_urls (list[str], up to 14, in
               "image 1 .. image N" order), aspect_ratio (enum, includes
               auto|21:9|16:9|3:2|4:3|5:4|1:1|4:5|3:4|2:3|9:16 and the
               extreme 4:1|1:4|8:1|1:8), resolution (1K|2K|4K),
               thinking_level (minimal|medium|high), output_format
   t2i input:  prompt (str, required), aspect_ratio (enum, same family as
               above, plus 2:1|7:5|5:7|1:2), resolution (768sq|1k|1.5k|2k|4k),
               output_format (jpeg|png)
   output: {"images": [{"url": "..."}]} on both.

   Why this provider exists, measured 2026-11-22 (blind, 18 frames, three
   shots built to split the candidates -- five people and a set, an 85 mm
   close-up, a reverse two-shot; scored 0-5 before the arm key was opened):
   Nano Banana 2.1 scored 4.6 against Kling O1 Image's 2.5, and every one of
   its frames beat every one of Kling's. ``thinking_level`` high scored the
   same as medium (4.67 vs 4.61), so medium is the default: faster (28 s vs 36 s
   on the same run) and cheaper. Against FLUX.2 Pro Edit, the model it
   replaces, FLUX.2 drew two men from three references once in two runs and
   dropped the headband in the other. flux-pro/v1.1, the text-to-image it
   replaces for portrait sheets, draws an illustration however firmly the
   prompt says PHOTOGRAPH; FLUX.3 drew photographs.

   Billing (the fal dashboard, per request at 1K): Nano Banana ~$0.0625 with
   thinking high -- token-billed, so thinking and resolution move it, not a
   flat per-image fee -- against $0.048 for FLUX.3 and roughly $0.08-0.10 for
   a 4-reference flux-2-pro/edit call, which bills its INPUT megapixels too.

NOTE: fal's Kontext uses singular ``image_url``; flux-2-pro/edit uses a
plural ``image_urls`` list (closer to MuAPI's ``images_list``); Nano Banana's
edit is ``image_urls`` too but addresses them by position in the PROMPT
("image 2 is ...") and has no ``image_size``. Do not confuse the schemas.

Errors raise (no silent MuAPI fallback).
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Callable, Optional

from tools.falai_common import (
    CONTENT_POLICY_RETRIES,
    ContentFlagged,
    fal_generate,
    make_fal_client,
)
from tools.muapi_image_generator import normalise_references

ASPECT_RATIO_MAP = {
    "1:1": {"width": 1024, "height": 1024},
    "16:9": {"width": 1344, "height": 768},
    "9:16": {"width": 768, "height": 1344},
    "4:3": {"width": 1152, "height": 896},
}

# fal-ai/flux-pro/v1.1 accepts named enums; map our ratios onto the closest.
IMAGE_SIZE_ENUM = {
    "1:1": "square_hd",
    "16:9": "landscape_16_9",
    "9:16": "portrait_16_9",
    "4:3": "landscape_4_3",
}

logger = logging.getLogger(__name__)

KONTEXT_ASPECT_RATIOS = {
    "21:9",
    "16:9",
    "4:3",
    "3:2",
    "1:1",
    "2:3",
    "3:4",
    "9:16",
    "9:21",
}


#: Nano Banana 2.1's ``aspect_ratio`` enum (edit) -- a superset of what the
#: pipeline asks for, so an unknown ratio is the only thing to guard.
NANOBANANA_ASPECT_RATIOS = {
    "21:9", "16:9", "3:2", "4:3", "5:4", "1:1", "4:5", "3:4", "2:3", "9:16",
}
NANOBANANA_MAX_REFERENCES = 14
NANOBANANA_RESOLUTIONS = ("1K", "2K", "4K")
NANOBANANA_THINKING_LEVELS = ("minimal", "medium", "high")

FLUX3_ENDPOINT = "blackforestlabs/flux-3/text-to-image"
FLUX3_ASPECT_RATIOS = {
    "21:9", "2:1", "16:9", "3:2", "7:5", "4:3", "5:4", "1:1", "4:5", "3:4", "5:7",
    "2:3", "9:16", "1:2",
}
FLUX3_RESOLUTIONS = ("768sq", "1k", "1.5k", "2k", "4k")


def _choice(env: str, allowed, default: str) -> str:
    """``env`` case-insensitively matched against ``allowed``, else ``default``.
    An unknown value falls back: fal validates, and a 422 here would fail
    every frame of every job."""
    raw = (os.environ.get(env, "") or "").strip()
    for known in allowed:
        if raw.lower() == known.lower():
            return known
    return default


def _ratio_or_default(aspect_ratio: str, allowed, endpoint: str) -> str:
    """``aspect_ratio`` if the endpoint's enum has it, else 16:9 -- out loud.

    The pipeline only ever asks for 16:9, 9:16 or 1:1 today (api.py validates
    it), so this should never fire. It is here for the day somebody adds a
    ratio: a silent 16:9 on a 9:16 project is a wrong-shaped frame that nothing
    downstream can get the sides back from.
    """
    if aspect_ratio in allowed:
        return aspect_ratio
    logger.warning(
        "%s has no %r aspect ratio; drawing 16:9 instead -- the frame will not "
        "be the shape the project asked for.", endpoint, aspect_ratio,
    )
    return "16:9"


def _demo_image_url(prompt: str, aspect_ratio: str) -> str:
    dims = ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"])
    seed = hashlib.sha1(f"{prompt}|{aspect_ratio}".encode()).hexdigest()[:12]
    return f"https://picsum.photos/seed/{seed}/{dims['width']}/{dims['height']}"


class FalAIImageGenerator:
    TEXT_ENDPOINT = os.environ.get("FALAI_IMAGE_MODEL", "fal-ai/flux-pro/v1.1")
    KONTEXT_ENDPOINT = os.environ.get(
        "FALAI_KONTEXT_MODEL", "fal-ai/flux-pro/kontext"
    )
    EDIT_ENDPOINT = os.environ.get(
        "FALAI_FLUX2_EDIT_MODEL", "fal-ai/flux-2-pro/edit"
    )
    NANOBANANA_ENDPOINT = os.environ.get(
        "FALAI_NANOBANANA_EDIT_MODEL", "google/nano-banana-2.1/edit"
    )

    def __init__(
        self,
        api_key: str,
        demo: bool = False,
        multiref: bool = False,
        nanobanana: bool = False,
    ):
        self.demo = demo
        #: True selects Nano Banana 2.1 for reference frames and FLUX.3 for
        #: text-to-image (portrait sheets and location plates). Implies the
        #: whole reference set is read, so it is a superset of ``multiref``.
        #: FALAI_IMAGE_MODEL, when set, still wins for text-to-image: an
        #: operator who named a model meant it.
        self.nanobanana = nanobanana
        if nanobanana:
            multiref = True
        #: True selects flux-2-pro/edit (the WHOLE reference list), false
        #: keeps the original Kontext/image_url behaviour. A constructor
        #: flag rather than a per-call one: which schema a deployment speaks
        #: is a provider decision (MUSEFORGE_IMAGE_PROVIDER), not something a
        #: caller re-litigates on every frame.
        self.multiref = multiref
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        self.client = make_fal_client(self.api_key, demo=demo)

    async def generate_image(
        self, prompt: str, aspect_ratio: str = "1:1", is_cancelled=None
    ) -> str:
        if self.demo:
            return _demo_image_url(prompt, aspect_ratio)

        endpoint = self.text_endpoint
        if "/flux-3" in endpoint:
            # Its own schema: an aspect_ratio and a resolution tier, no
            # image_size, no num_images.
            payload = {
                "prompt": prompt,
                "aspect_ratio": _ratio_or_default(aspect_ratio, FLUX3_ASPECT_RATIOS, endpoint),
                "resolution": _choice("FALAI_FLUX3_RESOLUTION", FLUX3_RESOLUTIONS, "1k"),
                "output_format": "jpeg",
            }
        else:
            payload = {
                "prompt": prompt,
                "image_size": IMAGE_SIZE_ENUM.get(aspect_ratio)
                or ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"]),
                "num_images": 1,
                "output_format": "jpeg",
            }
        result = await fal_generate(
            self.client,
            endpoint,
            payload,
            is_cancelled=is_cancelled,
        )
        return self._first_image_url(result)

    @property
    def accepts_reference_labels(self) -> bool:
        """Whether ``generate_image_with_reference`` takes ``reference_labels``.

        Nano Banana addresses its references by their position in the PROMPT
        ("image 2 is ..."), so a call that does not say who each picture is
        leaves the second face a stranger it was merely shown. The others read
        the references by order alone and are not sent the argument: the call
        site is duck-typed on this, as it is for the video backends.
        """
        return self.nanobanana

    @staticmethod
    def _labels_for_sent(references, labels, sent) -> list:
        """The labels that belong to ``sent``, or none at all.

        ``references`` goes through ``normalise_references`` (blank and repeated
        URLs vanish) before it is sent, so a label list indexed against the RAW
        list slides onto the wrong picture the moment one entry is dropped. The
        labels are therefore re-paired with their URLs first; if they cannot be
        paired one-to-one the legend is omitted, because a wrong name is worse
        than no name -- the model would put a face on the wrong person.
        """
        if not labels:
            return []
        raw = [references] if isinstance(references, str) else list(references or [])
        labels = list(labels)
        if len(labels) != len(raw):
            logger.warning(
                "reference_labels (%d) do not line up with the references (%d); "
                "sending no legend rather than a misaligned one.",
                len(labels), len(raw),
            )
            return []
        by_url = {}
        for url, label in zip(raw, labels):
            url = (url or "").strip() if isinstance(url, str) else ""
            if url:
                by_url.setdefault(url, label)
        return [by_url.get(url, "") for url in sent]

    @staticmethod
    def _legend(labels, count: int) -> str:
        """"Image 1 is Mara. Image 2 is the empty set." for the pictures that
        have a name, in order; "" when none does."""
        named = [
            f"Image {i} is {str(label).strip()}."
            for i, label in enumerate(list(labels or [])[:count], start=1)
            if str(label or "").strip()
        ]
        return " ".join(named)

    @property
    def text_endpoint(self) -> str:
        """The text-to-image endpoint: FALAI_IMAGE_MODEL if set, else FLUX.3
        for the nanobanana provider, else the original flux-pro/v1.1."""
        if os.environ.get("FALAI_IMAGE_MODEL", "").strip():
            return self.TEXT_ENDPOINT
        return FLUX3_ENDPOINT if self.nanobanana else self.TEXT_ENDPOINT

    async def generate_image_with_reference(
        self,
        prompt: str,
        references,
        aspect_ratio: str = "16:9",
        is_cancelled: Optional[Callable[[], bool]] = None,
        reference_labels=None,
    ) -> str:
        """Render a frame from one or more reference images.

        Same contract as the MuAPI backend: ``references`` is a URL or an
        ORDERED sequence, index 0 being the identity anchor.

        Non-multiref (default): reads exactly one. That is a property of
        fal's Kontext schema (singular ``image_url``), not a choice made
        here, so the rest of the set is reported rather than quietly
        discarded -- the caller assembled it for a reason and is entitled to
        know it did not arrive.

        multiref=True: flux-2-pro/edit takes the WHOLE ordered set as
        ``image_urls``, so nothing this method receives is ever held back.
        """
        if self.demo:
            return _demo_image_url(prompt + "|ref", aspect_ratio)

        ordered = normalise_references(references)
        if not ordered:
            return await self.generate_image(
                prompt, aspect_ratio, is_cancelled=is_cancelled
            )

        if self.nanobanana:
            held_back = len(ordered) - NANOBANANA_MAX_REFERENCES
            if held_back > 0:
                logger.warning(
                    "%s reads at most %d reference images; holding back the "
                    "last %d of %d.",
                    self.NANOBANANA_ENDPOINT, NANOBANANA_MAX_REFERENCES,
                    held_back, len(ordered),
                )
            sent = ordered[:NANOBANANA_MAX_REFERENCES]
            legend = self._legend(
                self._labels_for_sent(references, reference_labels, sent), len(sent)
            )
            payload = {
                "prompt": f"{legend} {prompt}" if legend else prompt,
                "image_urls": sent,
                "aspect_ratio": _ratio_or_default(
                    aspect_ratio, NANOBANANA_ASPECT_RATIOS, self.NANOBANANA_ENDPOINT
                ),
                "resolution": _choice("FALAI_NANOBANANA_RESOLUTION", NANOBANANA_RESOLUTIONS, "1K"),
                "thinking_level": _choice(
                    "FALAI_NANOBANANA_THINKING", NANOBANANA_THINKING_LEVELS, "medium"
                ),
                "output_format": "jpeg",
            }
            return await self._generate_nanobanana(payload, is_cancelled)

        if self.multiref:
            payload = {
                "prompt": prompt,
                "image_urls": ordered,
                "image_size": IMAGE_SIZE_ENUM.get(aspect_ratio)
                or ASPECT_RATIO_MAP.get(aspect_ratio, ASPECT_RATIO_MAP["16:9"]),
                "num_images": 1,
                "output_format": "jpeg",
            }
            result = await fal_generate(
                self.client,
                self.EDIT_ENDPOINT,
                payload,
                is_cancelled=is_cancelled,
            )
            return self._first_image_url(result)

        if len(ordered) > 1:
            logger.info(
                "%s takes a single reference image; using the anchor and "
                "holding back %d. Point MUSEFORGE_IMAGE_PROVIDER at "
                "falai_multiref to use the whole set.",
                self.KONTEXT_ENDPOINT,
                len(ordered) - 1,
            )

        # Confirmed: fal Kontext wants singular image_url, not a list.
        payload = {
            "prompt": prompt,
            "image_url": ordered[0],
            "aspect_ratio": (
                aspect_ratio if aspect_ratio in KONTEXT_ASPECT_RATIOS else "16:9"
            ),
            "num_images": 1,
            "output_format": "jpeg",
        }
        result = await fal_generate(
            self.client,
            self.KONTEXT_ENDPOINT,
            payload,
            is_cancelled=is_cancelled,
        )
        return self._first_image_url(result)

    async def edit_image(
        self,
        prompt: str,
        image_url: str,
        aspect_ratio: str = "16:9",
        is_cancelled=None,
        **_ignored,
    ) -> str:
        """Edit one existing image, keeping its composition.

        Every reference endpoint this class speaks IS an edit model (Kontext,
        FLUX.2 edit, Nano Banana edit), so a one-picture reference call is an
        edit. Without this method the acting end frame (interfaces/acting) had
        nothing to call on a fal deployment and silently never rendered.
        Raises on failure, like the MuAPI edit: a "fallback" would be a
        different picture, and an end frame from a different picture is a warp.
        """
        return await self.generate_image_with_reference(
            prompt, [image_url], aspect_ratio, is_cancelled=is_cancelled
        )

    @staticmethod
    def _first_image_url(result) -> str:
        images = (result or {}).get("images") or []
        if not images or not images[0].get("url"):
            raise RuntimeError(f"fal.ai image completed but no image URL: {result}")
        return images[0]["url"]

    async def _generate_nanobanana(self, payload, is_cancelled) -> str:
        """Nano Banana, with a text-only answer treated as the refusal it is.

        Gemini declines by answering 200 with an empty ``images`` and a
        ``description`` of why. That is not an error to fal, so
        ``fal_generate``'s one resubmit for a content flag (keyed on the
        policy-violation message) never saw it, and the frame failed the whole
        scene on the first refusal. A flag is not always deterministic, which is
        the whole reason that retry exists, so the same single resubmit applies.
        """
        for attempt in range(CONTENT_POLICY_RETRIES + 1):
            result = await fal_generate(
                self.client, self.NANOBANANA_ENDPOINT, payload,
                is_cancelled=is_cancelled,
            )
            images = (result or {}).get("images") or []
            if images and images[0].get("url"):
                return images[0]["url"]
            reason = str((result or {}).get("description") or "").strip()
            if attempt < CONTENT_POLICY_RETRIES:
                logger.warning(
                    "%s returned no image (%r); resubmitting once.",
                    self.NANOBANANA_ENDPOINT, reason[:300],
                )
                continue
            raise ContentFlagged(
                f"{self.NANOBANANA_ENDPOINT} declined to draw this frame"
                + (f": {reason[:300]}" if reason else " and said nothing")
                + f". Raw result: {result}"
            )
