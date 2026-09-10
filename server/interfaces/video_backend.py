"""What one video endpoint can actually do, declared in a single place.

Until now this knowledge lived in five parallel dictionaries, all keyed by the
same endpoint slug and all maintained by hand:

    _ENDPOINT_FIELDS        which optional payload fields it accepts
    _NO_DURATION            whether it has a duration field at all
    FIXED_DURATION          whether that field is a single-value enum
    SUPPORTED_ASPECT_RATIOS which ratios its enum admits
    MUAPI_RATES             what it costs -- and this one lived in a TEST

Adding a model meant remembering five places, and forgetting one of them is
not an error anybody sees. Send a field an endpoint does not declare and MuAPI
answers 422; the fallback chain reads 422 as "this model does not exist here"
and quietly demotes the shot to Standard. A routed model would have been
configured, expected, planned for and billed for in advance, and never once
actually run -- with nothing in the log to say so. The maps existed precisely
to prevent that, which is why splitting them across five literals was the
wrong shape: they are five answers to one question.

They are also not the only question. Everything the pipeline wants to ask a
backend before it plans a scene -- how long a single generation can be, how it
quantises that length, how many reference elements it reads, whether it speaks
and in which languages, whether it can cut inside one generation -- had no
place to live at all, so the planner assumed a single envelope for every model
and the router could only correct the payload after the fact.

So a backend declares itself once, here, and everything else reads it.

ON THE NUMBERS BELOW. They describe *this vendor's* envelope for a model, not
the model's own. MuAPI's veo3.1-lite exposes a duration enum of exactly one
value; Google's own Veo 3.1 offers 4, 6 and 8. Both are true. A declaration is
a statement about an ENDPOINT, and the same model reached two ways is two
endpoints -- which is the entire reason this is data rather than a branch on a
model family name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional, Tuple

#: Billing shapes, which rank in the opposite order to how they read for the
#: short clips this pipeline makes. A three-second insert costs $0.336 on a
#: $0.112/s "turbo" endpoint and $0.30 on a flat $0.30 one -- a short clip does
#: not get a discount from a per-second rate, it gets a smaller bill from a
#: rate we are not paying at all. Declared so a planner can reason about it
#: instead of a comment warning the next person not to be fooled.
FLAT = "flat"
PER_SECOND = "per_second"


@dataclass(frozen=True)
class Duration:
    """How an endpoint quantises clip length.

    Three shapes, and the difference between them is the difference between a
    routed model running and a routed model silently never running:

    * a RANGE -- Kling v3.0 takes any integer 3..15.
    * an ENUM -- MuAPI's veo3.1 endpoints take 8 and nothing else. Sending a
      Kling-shaped 6 or 10 is a 422.
    * ABSENT -- the minimax hailuo endpoints have no duration field; the clip
      comes back at whatever length the model produces, which the second
      budget (interfaces/second_budget) then cannot honour.
    """

    minimum: int = 3
    maximum: int = 15
    #: Non-empty makes this an enum rather than a range.
    allowed: Tuple[int, ...] = ()
    #: True when the endpoint has no duration field at all.
    absent: bool = False

    def send(self, wanted) -> Optional[int]:
        """The duration to put in the payload, or None to omit the field.

        Never raises and never returns something the endpoint would reject:
        the whole point is that a caller can ask for six seconds without
        knowing whether six is a legal answer here.
        """
        if self.absent:
            return None
        try:
            value = int(round(float(wanted)))
        except (TypeError, ValueError):
            value = self.allowed[0] if self.allowed else self.minimum
        if self.allowed:
            # Nearest legal value. A scene budgeted at 6 against an enum of
            # (8,) is generated at 8 and trimmed by the caller -- which is
            # what `delivers` exists to tell it.
            return min(self.allowed, key=lambda option: abs(option - value))
        return max(self.minimum, min(self.maximum, value))

    def delivers(self, wanted) -> float:
        """How many seconds actually come back when ``wanted`` is asked for.

        Equal to what was asked for whenever the endpoint can honour it, and
        longer when an enum rounds up. A caller that budgets in seconds needs
        this to know whether it is about to receive footage it must trim; it
        returns 0.0 for an endpoint with no duration field, meaning "unknown",
        which every caller already treats as a reason to measure rather than
        assume.
        """
        if self.absent:
            return 0.0
        return float(self.send(wanted) or 0)

    def honours(self, wanted) -> bool:
        """Whether this endpoint can deliver exactly ``wanted`` seconds."""
        if self.absent:
            return False
        return abs(self.delivers(wanted) - float(wanted)) < 0.5


#: The Kling v3.0 envelope, which is also the shipped default and therefore
#: the shape every unknown endpoint is assumed to have.
KLING_DURATION = Duration(minimum=3, maximum=15)


@dataclass(frozen=True)
class VideoBackend:
    """One endpoint's declared capabilities.

    Every field is a statement that can be checked against the vendor's own
    API reference, and none of them is a preference. When a declaration and an
    endpoint disagree, the declaration is wrong -- which is worth saying
    because the failure mode is a quiet demotion rather than an error, and the
    router now says which of the two it thinks happened.
    """

    slug: str
    #: Optional payload fields beyond `prompt` and `image_url`.
    fields: FrozenSet[str] = frozenset({"duration"})
    duration: Duration = KLING_DURATION
    #: Aspect ratios the endpoint's enum admits. Empty means unrestricted --
    #: an endpoint with no declared restriction keeps the previous behaviour.
    aspect_ratios: FrozenSet[str] = frozenset()
    #: Language codes this endpoint speaks natively, empty when it is silent.
    #: A pipeline that lays its own dialogue over the picture needs to know
    #: the difference, and needs to know it per LANGUAGE: an endpoint that
    #: speaks English and not Turkish is not "an endpoint with native audio".
    native_audio: FrozenSet[str] = frozenset()
    #: Reference images / character elements it reads. 0 means image-to-video
    #: only: the start frame is the whole of its visual conditioning.
    max_elements: int = 0
    #: How many framings it can cut between inside ONE generation.
    #:
    #: 1 means a single continuous take, which is what every endpoint here did
    #: until now and is why a scene covered in three angles cost three
    #: generations. Above 1 the arithmetic of coverage inverts: the bill is for
    #: the scene's SECONDS, so a second and third angle are free, and the
    #: reason a delivered 30-second film only ever had six shots -- each extra
    #: angle being a whole extra generation -- stops applying.
    max_beats: int = 1
    billing: str = FLAT
    #: USD per generation when billing is FLAT, per second when PER_SECOND.
    rate: float = 0.0
    #: Free-text, for the log line an operator reads at 2am.
    note: str = ""

    @property
    def multishot(self) -> bool:
        """Whether a scene can be one request with cuts inside it."""
        return self.max_beats > 1

    def accepts_aspect_ratio(self, aspect_ratio: str) -> bool:
        if not self.aspect_ratios:
            return True
        return (aspect_ratio or "").strip() in self.aspect_ratios

    def speaks(self, language: str) -> bool:
        """Whether this endpoint can carry dialogue in ``language`` itself."""
        return (language or "").strip().lower()[:2] in self.native_audio

    def cost(self, seconds: float) -> float:
        """What one generation of ``seconds`` costs on this endpoint."""
        if self.billing == PER_SECOND:
            return self.rate * max(0.0, float(seconds))
        return self.rate


#: Everything this build knows how to route to.
#:
#: Read off each model's schema in the MuAPI playground. Keep it in step when
#: adding a model: being wrong in the permissive direction -- declaring a field
#: the endpoint rejects -- costs a silent demotion to Standard, which is
#: exactly what this registry exists to stop.
#:
#: Rates verified against muapi.ai/pricing on 2026-08-14. A stale number here
#: is worse than no number, because tests/test_pricing_coherence computes the
#: product's margins from it.
BACKENDS = {
    # -- Kling v3.0: the shipped default. The one family that takes both an
    # audio flag and an end frame, and the only one whose duration is a real
    # range, which is why the second budget's 6-12s scenes fit it untouched.
    "kling-v3.0-standard-image-to-video": VideoBackend(
        slug="kling-v3.0-standard-image-to-video",
        fields=frozenset({"duration", "generate_audio", "last_image"}),
        duration=KLING_DURATION,
        native_audio=frozenset({"en", "zh"}),
        max_elements=0,
        billing=FLAT,
        rate=0.72,
        note="flat to 15s; the safest link and always last in a chain",
    ),
    "kling-v3.0-pro-image-to-video": VideoBackend(
        slug="kling-v3.0-pro-image-to-video",
        fields=frozenset({"duration", "generate_audio", "last_image"}),
        duration=KLING_DURATION,
        native_audio=frozenset({"en", "zh"}),
        billing=FLAT,
        rate=0.72,
    ),
    "kling-v3.0-4k-image-to-video": VideoBackend(
        slug="kling-v3.0-4k-image-to-video",
        fields=frozenset({"duration", "generate_audio", "last_image"}),
        duration=KLING_DURATION,
        native_audio=frozenset({"en", "zh"}),
        billing=FLAT,
        rate=0.72,
    ),
    # -- Turbo drops both the audio flag and the end frame: prompt, image_url
    # and duration only. It also bills per second, which makes it the
    # expensive option for exactly the short clips its name suggests it suits.
    "kling-v3-turbo-standard-image-to-video": VideoBackend(
        slug="kling-v3-turbo-standard-image-to-video",
        fields=frozenset({"duration"}),
        duration=KLING_DURATION,
        billing=PER_SECOND,
        rate=0.112,
        note="no end frame, no audio flag; per-second",
    ),
    "kling-v3-turbo-pro-image-to-video": VideoBackend(
        slug="kling-v3-turbo-pro-image-to-video",
        fields=frozenset({"duration"}),
        duration=KLING_DURATION,
        billing=PER_SECOND,
        rate=0.14,
    ),
    # -- Veo takes an end frame and an aspect ratio, but no audio flag: its
    # audio is always on. Its duration here is a single-value enum, which is
    # this VENDOR's envelope -- Google's own API offers 4, 6 and 8.
    "veo3.1-image-to-video": VideoBackend(
        slug="veo3.1-image-to-video",
        fields=frozenset({"duration", "last_image", "aspect_ratio"}),
        duration=Duration(allowed=(8,)),
        aspect_ratios=frozenset({"16:9", "9:16"}),
        native_audio=frozenset({"en"}),
        max_elements=3,
        billing=FLAT,
        rate=0.30,
    ),
    "veo3.1-fast-image-to-video": VideoBackend(
        slug="veo3.1-fast-image-to-video",
        fields=frozenset({"duration", "last_image", "aspect_ratio"}),
        duration=Duration(allowed=(8,)),
        aspect_ratios=frozenset({"16:9", "9:16"}),
        native_audio=frozenset({"en"}),
        max_elements=3,
        billing=FLAT,
        rate=0.30,
    ),
    "veo3.1-lite-image-to-video": VideoBackend(
        slug="veo3.1-lite-image-to-video",
        fields=frozenset({"duration", "last_image", "aspect_ratio"}),
        duration=Duration(allowed=(8,)),
        aspect_ratios=frozenset({"16:9", "9:16"}),
        native_audio=frozenset({"en"}),
        max_elements=3,
        billing=FLAT,
        rate=0.30,
        note="flat, takes an end frame; the reaction profile's default",
    ),
    # -- Seedance takes an aspect ratio and a seed; no audio flag, no end
    # frame. Per-second, and dearer per second than it sounds.
    "seedance-2.5-image-to-video": VideoBackend(
        slug="seedance-2.5-image-to-video",
        fields=frozenset({"duration", "aspect_ratio"}),
        duration=Duration(minimum=4, maximum=30),
        billing=PER_SECOND,
        rate=0.34,
    ),
    "seedance-2.5-image-to-video-480p": VideoBackend(
        slug="seedance-2.5-image-to-video-480p",
        fields=frozenset({"duration", "aspect_ratio"}),
        duration=Duration(minimum=4, maximum=30),
        billing=PER_SECOND,
        rate=0.17,
    ),
    "seedance-2-image-to-video": VideoBackend(
        slug="seedance-2-image-to-video",
        fields=frozenset({"duration", "aspect_ratio"}),
        duration=Duration(minimum=4, maximum=30),
        billing=PER_SECOND,
        rate=0.17,
    ),
    # -- No duration field at all. Route here only if you are prepared for a
    # clip whose length the second budget cannot honour.
    "minimax-hailuo-2.3-pro-i2v": VideoBackend(
        slug="minimax-hailuo-2.3-pro-i2v",
        fields=frozenset(),
        duration=Duration(absent=True),
        note="fixed length decided by the model; the budget cannot hold it",
    ),
    "minimax-hailuo-2.3-standard-i2v": VideoBackend(
        slug="minimax-hailuo-2.3-standard-i2v",
        fields=frozenset(),
        duration=Duration(absent=True),
    ),
    "minimax-hailuo-2.3-fast": VideoBackend(
        slug="minimax-hailuo-2.3-fast",
        fields=frozenset(),
        duration=Duration(absent=True),
    ),
    # -- fal.ai's Kling v3, which is the same model family reached a different
    # way and a materially different ENDPOINT: it cuts inside one generation
    # (`multi_prompt`), binds characters as reusable elements, and bills per
    # second instead of flat.
    #
    # Schema read off fal's own API reference for
    # fal-ai/kling-video/v3/{standard,pro}/image-to-video:
    #
    #     start_image_url  required
    #     prompt | multi_prompt   one of the two
    #     duration         enum 3..15, default 5
    #     generate_audio   bool, default true
    #     elements         characters/objects, cited in prompts as @Element1
    #     end_image_url    optional
    #     shot_type        "customize" | "intelligent"
    #     negative_prompt  cfg_scale
    #
    # Aspect ratio is DERIVED FROM THE START IMAGE and is not a field, which is
    # why none is declared -- sending one is a 422.
    #
    # `max_beats` is 5 because five is the largest shot list fal's and Kling's
    # own documentation demonstrate. The real ceiling is not published, so this
    # is the largest number either vendor has shown working rather than a
    # measurement, and it is the conservative direction: asking for four cuts
    # where six were possible costs coverage, asking for eight where five were
    # possible could cost the take.
    "fal-ai/kling-video/v3/standard/image-to-video": VideoBackend(
        slug="fal-ai/kling-video/v3/standard/image-to-video",
        fields=frozenset(
            {"duration", "generate_audio", "end_image_url", "elements",
             "multi_prompt", "shot_type", "negative_prompt", "cfg_scale"}
        ),
        duration=KLING_DURATION,
        native_audio=frozenset({"en", "zh"}),
        max_elements=7,
        max_beats=5,
        billing=PER_SECOND,
        rate=0.126,
        note="per second with audio on; $0.084 silent, $0.154 with voice binding",
    ),
    "fal-ai/kling-video/v3/pro/image-to-video": VideoBackend(
        slug="fal-ai/kling-video/v3/pro/image-to-video",
        fields=frozenset(
            {"duration", "generate_audio", "end_image_url", "elements",
             "multi_prompt", "shot_type", "negative_prompt", "cfg_scale"}
        ),
        duration=KLING_DURATION,
        native_audio=frozenset({"en", "zh"}),
        max_elements=7,
        max_beats=5,
        billing=PER_SECOND,
        rate=0.168,
        note="per second with audio on; $0.112 silent, $0.196 with voice binding",
    ),
}


#: What an endpoint nobody has declared is assumed to be.
#:
#: `duration` alone, because nearly every image-to-video model in the
#: catalogue takes it and an unknown field is a 422 rather than something
#: politely ignored. Everything else is assumed absent, which is the direction
#: that degrades quietly instead of failing: an undeclared endpoint that would
#: have accepted an end frame simply animates from its start frame.
def unknown_backend(slug: str) -> VideoBackend:
    return VideoBackend(
        slug=slug,
        fields=frozenset({"duration"}),
        duration=KLING_DURATION,
        note="undeclared; assumed to take a prompt, an image and a duration",
    )


def backend_for(slug: str) -> VideoBackend:
    """The declaration for ``slug``, or a conservative stand-in."""
    key = (slug or "").strip()
    declared = BACKENDS.get(key)
    return declared if declared is not None else unknown_backend(key)


def is_declared(slug: str) -> bool:
    """Whether this build has a real declaration for ``slug``.

    The router uses it to tell two very different 422s apart: one from an
    endpoint we never described, and one from an endpoint we described wrongly.
    Only the second is a bug in this file.
    """
    return (slug or "").strip() in BACKENDS
