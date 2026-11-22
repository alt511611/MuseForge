"""fal.ai MiniMax H3 Max reference-to-video.

Selected via MUSEFORGE_VIDEO_PROVIDER=falai_minimax.

Why it exists: a candidate to measure against Kling v3 and Vidu Q4 on the same
two-character script. It is the only one of the three whose schema takes BOTH a
first frame and a last frame AND a set of references in one call, which is the
shape this pipeline already builds -- an opening frame, an acted-peak end frame
(``_render_end_frame``) and the ordered references (``resolve_frame_references``).
Vidu takes references but no end frame; Kling v4 takes frames but no references.
On the catalogue's numbers it costs $0.08/s at 768p and $0.16/s at 1080p, about
what Vidu costs once its promotion ends.

Measured on 2026-11-22 against Vidu Q4 and Kling v3, one shot per arm, low
resolution, identity judged by eye (no face-ID score): in ``reference`` mode it
held three men in a wide shot from frame 0 and one face in an 85 mm close-up
across two seeds, as well as Vidu did; it kept the empty-set plate (raft, rocky
coast, warm dusk) in both close-ups where Vidu dropped it for a cold blue sea;
and it returned in ~8 s against Vidu's 112-125 s. ``frame`` mode inherits the
frame step's mistakes (the flux-2-pro/edit frame lost one of three men, and the
video had to invent him), so ``reference`` is the mode worth trying first. It
runs ~0.46 s longer than asked and its soundtrack is near-silent.

Schema CONFIRMED against fal's OpenAPI
(/api/openapi/queue/openapi.json?endpoint_id=minimax/h3-max/reference-to-video):
    input:
      prompt (str, REQUIRED) -- refer to references by position:
          "Image 1", "Image 2" ...
      prompt_expansion_mode (str, REQUIRED) -- "disabled" | "balanced" | "quality"
      reference_image_urls (list[str], at most 9)
      image_url (str)       -- the FIRST frame; the video opens exactly on it
      end_image_url (str)   -- the LAST frame; the video ends exactly on it
      duration (float 0.92..15, default 5) -- the output may run ~0.7 s longer
      resolution ("480P"|"768P"|"1080P", default "768P")
      aspect_ratio ("adaptive"|"21:9"|"16:9"|"4:3"|"1:1"|"3:4"|"9:16")
      enable_safety_checker (bool, default true), seed (int)
    output: {"video": {"url": ...}, "expanded_prompt": str|null, "seed": int}

Two modes, because the schema allows both and it is not known which holds a
face better:
* ``frame`` (default): the pipeline renders the opening frame first, exactly as
  for Kling, and this animates it. The frame is ``image_url``; the references
  keep the cast and the set consistent around it; ``last_image`` is the end
  frame when one was rendered.
* ``reference``: the frame step is skipped, as for Vidu, and the portrait set
  alone defines the shot.
Pick with FALAI_MINIMAX_MODE.

Two things this module decides on purpose:
* ``prompt_expansion_mode`` is sent as "disabled". The prompt is already built
  clause by clause (identity, wardrobe, screen direction, what the shot must
  not do), and a model rewriting it is a model free to drop the clause that
  was there to hold a face. The field is required, so it is always sent.
* ``audio`` has no switch on this schema. Dialogue is voiced by the TTS pass
  and mixed afterwards, so nothing here asks for a soundtrack.

No prompt length limit was read from the schema. If fal enforces one it
surfaces as a 422 on the first long shot, not as a silent truncation.
"""

from __future__ import annotations

import os
from typing import Callable, Optional, Sequence

from tools.falai_common import fal_generate, make_fal_client
from tools.falai_reference_video_generator import DEMO_VIDEO_URL

ENDPOINT_DEFAULT = "minimax/h3-max/reference-to-video"

MIN_DURATION_SECONDS = 0.92
MAX_DURATION_SECONDS = 15.0
#: The schema's cap on ``reference_image_urls``. fal's prose says 12, but that
#: is the total across images, videos and audio; the image list alone stops at 9.
MAX_REFERENCE_IMAGES = 9
VALID_ASPECT_RATIOS = {"21:9", "16:9", "4:3", "1:1", "3:4", "9:16"}
VALID_RESOLUTIONS = ("480P", "768P", "1080P")
DEFAULT_RESOLUTION = "768P"
VALID_EXPANSION_MODES = ("disabled", "balanced", "quality")
MODES = ("frame", "reference")
DEFAULT_MODE = "frame"


def _duration(seconds) -> float:
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        value = 5.0
    return max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, value))


def _aspect_ratio(ratio: str) -> str:
    # Not "adaptive": that follows the first frame, and a reference-only call
    # has none, so the canvas would be the model's choice.
    return ratio if ratio in VALID_ASPECT_RATIOS else "16:9"


def _resolution() -> str:
    """FALAI_MINIMAX_RESOLUTION, case-insensitively, or 768P.

    An unknown value is a 422 from fal on every shot of every job, so it falls
    back rather than being passed through.
    """
    raw = (os.environ.get("FALAI_MINIMAX_RESOLUTION", "") or "").strip()
    for known in VALID_RESOLUTIONS:
        if raw.lower() == known.lower():
            return known
    return DEFAULT_RESOLUTION


def _expansion_mode() -> str:
    raw = (os.environ.get("FALAI_MINIMAX_PROMPT_EXPANSION", "") or "").strip().lower()
    return raw if raw in VALID_EXPANSION_MODES else "disabled"


def mode() -> str:
    """FALAI_MINIMAX_MODE, or ``frame``. An unknown value is the default, not a 422."""
    raw = (os.environ.get("FALAI_MINIMAX_MODE", "") or "").strip().lower()
    return raw if raw in MODES else DEFAULT_MODE


def _reference_set(
    image_url: str, reference_images: Optional[Sequence[str]], anchor_first: bool
) -> list:
    """The references, de-duplicated and capped at what the endpoint reads.

    ``anchor_first`` puts ``image_url`` at the head, for the reference-only
    mode where it IS the resolved portrait. In frame mode ``image_url`` is the
    opening frame, passed separately, and is not a reference.
    """
    ordered = ([image_url] if anchor_first else []) + list(reference_images or [])
    return list(dict.fromkeys(u for u in ordered if u))[:MAX_REFERENCE_IMAGES]


def _prompt(prompt: str, labels: Sequence[str], fallback_anchor: bool) -> str:
    """The prompt, with each reference named by the position this endpoint
    addresses it by ("Image 1 is Mara."). With no labels, a reference-only
    call still says what its one picture is; a frame-mode call has the frame
    to speak for itself and is left as it was."""
    named = [
        f"Image {i} is {label.strip()}."
        for i, label in enumerate(labels, start=1)
        if (label or "").strip()
    ]
    if named:
        return f"{' '.join(named)} {prompt}"
    if fallback_anchor:
        return f"Image 1 is the character. {prompt}"
    return prompt


class FalAIMiniMaxVideoGenerator:
    """Drop-in for MuAPIVideoGenerator.generate_video_from_image.

    ``uses_character_reference_to_video`` is True only in ``reference`` mode:
    it is what tells script2video to skip the separate frame step and treat
    ``image_url`` as the character reference. In ``frame`` mode the frame step
    runs and ``image_url`` is its result.

    ``accepts_reference_set`` tells it this backend can be handed the WHOLE
    ordered set (the anchor's portrait, the other faces in the shot, the empty
    set) in either mode. Declared, not assumed: the call site is duck-typed.
    """

    accepts_reference_set = True

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.api_key = (api_key or os.environ.get("FAL_KEY", "")).strip()
        self.client = make_fal_client(self.api_key, demo=demo)

    @property
    def uses_character_reference_to_video(self) -> bool:
        return mode() == "reference"

    @property
    def endpoint(self) -> str:
        return os.environ.get("FALAI_MINIMAX_VIDEO_MODEL", "").strip() or ENDPOINT_DEFAULT

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
        reference_images: Optional[Sequence[str]] = None,
        reference_labels: Optional[Sequence[str]] = None,
    ) -> str:
        """``reference_images`` is the ordered set to bind; ``reference_labels``
        says who or what each one is, in the same order.

        In ``frame`` mode ``image_url`` is the first frame and ``last_image``
        the last, when there is one. In ``reference`` mode ``image_url`` is the
        anchor portrait and leads the reference list.
        """
        # plan and shot_profile: signature parity only -- no HD mode and no
        # MuAPI-style routing on this endpoint.
        _ = (plan, shot_profile)
        if self.demo:
            return DEMO_VIDEO_URL

        by_reference = mode() == "reference"
        references = _reference_set(image_url, reference_images, anchor_first=by_reference)
        # Labels travel with their picture, not their position: de-duplicating
        # or capping the set must not hand one face another face's name.
        label_of = dict(zip(reference_images or [], reference_labels or []))
        aligned = [label_of.get(u, "") for u in references]

        payload = {
            "prompt": _prompt(prompt, aligned, fallback_anchor=by_reference),
            "prompt_expansion_mode": _expansion_mode(),
            "duration": _duration(duration),
            "resolution": _resolution(),
            "aspect_ratio": _aspect_ratio(aspect_ratio),
        }
        if references:
            payload["reference_image_urls"] = references
        if not by_reference and image_url:
            payload["image_url"] = image_url
        if last_image:
            payload["end_image_url"] = last_image

        result = await fal_generate(
            self.client,
            self.endpoint,
            payload,
            is_cancelled=is_cancelled,
        )
        video_url = ((result or {}).get("video") or {}).get("url")
        if not video_url:
            raise RuntimeError(
                f"fal.ai MiniMax H3 Max completed but no video URL: {result}"
            )
        return video_url
