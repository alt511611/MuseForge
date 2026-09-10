"""One scene as a single generation, with its cuts inside it.

Every scene this pipeline has ever made was assembled: each angle was its own
image, its own video generation and its own file, joined afterwards by ffmpeg.
That was not a design, it was the only thing 2024's models could do -- one
still in, five silent seconds out -- and four stages exist purely to put the
pieces back together (frames, assembly, the timescale repair the concat needs,
and the lip sync that had to be applied because the picture arrived mute).

Backends that cut inside one generation make the assembly unnecessary, and
they change the ARITHMETIC OF COVERAGE, which is the part that matters more.
Today a second angle is a second whole generation, so a delivered 30-second
drama had six shots -- an average of 5.04 seconds of unbroken picture, which
sits at the bottom of the band short-form retention research recommends (a new
visual beat every 5-7 seconds for story content, 6-12 shots per 20-30 second
piece). The framing count was not a directing decision. It was what the price
list allowed.

Billed per second of SCENE, extra cuts cost nothing. The same 30 seconds can
carry nine to twelve beats for the same money.

WHAT THIS MODULE DOES NOT DO. It does not invent beats. The storyboard artist
already designs however many shots a scene is covered in
(MUSEFORGE_SHOTS_PER_SCENE) and `shot_plan.split_scene_seconds` already divides
the scene's budget between them. This takes those same shots and expresses them
as ONE request instead of N. Raising coverage is what buys the extra cuts; this
is what makes them affordable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Element:
    """A character (or object) the whole take is locked to.

    An element is cited from the beat prompts by its token -- ``@Element1`` --
    and the CAST CLAUSE is the only place its name appears, because the
    endpoint's element object has no name field. A model handed `@Element1`
    with nothing to attach it to has to guess which subject that is.

    ``images`` is an ordered set of views of one subject: the first is the
    frontal (main) view and the rest are additional angles, which is exactly
    the shape MUSEFORGE_CHARACTER_SHEET produces. The split into
    `frontal_image_url` and `reference_image_urls` happens at the payload,
    because it is that endpoint's spelling rather than a fact about the film.

    ``voice_id`` is the other half of the lock: an id from the backend's own
    voice library, bound to this element, so a take with native audio speaks
    this character in a chosen voice rather than one the model picked.
    """

    name: str
    images: Tuple[str, ...] = ()
    #: A VOICE ID, not an audio file. The endpoint's element takes
    #: `voice_id`; there is nowhere to upload a sample. See the note on
    #: MUSEFORGE_VOICE_PROVIDER in .env.example -- keeping the film's cast
    #: through a native-audio take means mapping each character to one of the
    #: backend's voices, which is a different job from generating speech.
    voice_id: str = ""

    #: The endpoint takes 1-3 additional angles beside the frontal view.
    MAX_REFERENCE_IMAGES = 3

    @property
    def frontal(self) -> str:
        """The main view. First, because order is how the caller ranks them."""
        return self.images[0] if self.images else ""

    @property
    def reference_images(self) -> List[str]:
        """The other angles, trimmed to what the endpoint accepts."""
        return list(self.images[1 : 1 + self.MAX_REFERENCE_IMAGES])

    def token(self, index: int) -> str:
        """``@Element1`` for the first element, and so on. One-based."""
        return f"@Element{index + 1}"


@dataclass(frozen=True)
class Beat:
    """One framing inside a take, and how long it holds."""

    seconds: int
    description: str
    shot_type: str = ""

    def as_prompt(self) -> str:
        """What this beat SHOWS. Its length is a field, not prose.

        The seconds used to be written into the text as "Shot 1 (3s): ...",
        which is the syntax Kling's own interface documents and which this
        endpoint rejects outright: it takes an object per beat with its own
        `duration`, so the timing belongs there and repeating it in the prose
        only spends prompt on something the model is already being told.
        """
        framing = f"{self.shot_type}. " if self.shot_type else ""
        return f"{framing}{self.description}".strip()

    def as_payload(self) -> dict:
        """One entry of `multi_prompt`.

        `duration` is a STRING enum ("1".."15"), not an integer -- sending the
        number is a 422, and a 422 on this endpoint is the whole take.
        """
        return {"prompt": self.as_prompt(), "duration": str(self.seconds)}


@dataclass(frozen=True)
class SceneTake:
    """A whole scene as one request.

    ``seconds`` is what the backend will be ASKED for, already snapped to
    whatever its duration field accepts, and the beats sum to exactly that --
    a take whose parts do not add up to its whole is a scene that comes back
    the wrong length, which is the failure the second budget exists to prevent.
    """

    seconds: int
    beats: Tuple[Beat, ...]
    elements: Tuple[Element, ...] = ()
    start_image: str = ""
    end_image: str = ""

    @property
    def beat_count(self) -> int:
        return len(self.beats)

    def multi_prompt(self) -> List[dict]:
        """The beat list, in cut order, as the endpoint's own objects.

        A list of STRINGS is what this sent first, and the endpoint answered
        with one error per entry: "Input should be a valid dictionary or
        object to extract fields from". Each beat is `{prompt, duration}`.
        """
        return [beat.as_payload() for beat in self.beats]

    def cast_clause(self) -> str:
        """Which token is whom, said once at the top of the take.

        Without it the tokens are unexplained: a model handed ``@Element1``
        and a beat that says "she deals" has to guess which of the two people
        in front of it that is, and guessing is how the wrong face gets the
        line.
        """
        if not self.elements:
            return ""
        parts = [
            f"{element.token(i)} is {element.name}"
            for i, element in enumerate(self.elements)
        ]
        return "; ".join(parts) + ". "


#: A beat shorter than this is a flash rather than a shot, and no retention
#: guidance asks for one: the tightest recommended cadence for dynamic content
#: is a visual shift every 2-3 seconds.
MIN_BEAT_SECONDS = 2


def _seconds_of(shot: Any, fallback: float = 0.0) -> float:
    for field in ("deliver_seconds", "duration_seconds"):
        try:
            value = float(getattr(shot, field, 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return fallback


def _describe(shot: Any) -> str:
    visual = (getattr(shot, "visual_desc", "") or "").strip()
    motion = (getattr(shot, "motion_desc", "") or "").strip()
    if visual and motion:
        return f"{visual} {motion}"
    return visual or motion


def _merge_to_fit(shots: Sequence[Any], limit: int) -> List[List[Any]]:
    """Group ``shots`` into at most ``limit`` runs, merging the shortest first.

    A scene covered in more angles than the backend can cut between has to
    lose some of them, and there are two ways to do that: drop the surplus or
    merge it. Dropping throws away coverage the storyboard designed and
    silently shortens the scene; merging keeps every description and only
    costs the cut between two of them. So adjacent runs are merged, shortest
    pair first, until the list fits.
    """
    runs: List[List[Any]] = [[shot] for shot in shots]
    if limit <= 0:
        return runs
    while len(runs) > limit:
        # The cheapest join is between the two adjacent runs that together
        # hold the least screen time -- losing a cut between two brief beats
        # is less visible than losing one between two long ones.
        pairs = [
            (sum(_seconds_of(s) for s in runs[i] + runs[i + 1]), i)
            for i in range(len(runs) - 1)
        ]
        _, at = min(pairs)
        runs[at] = runs[at] + runs[at + 1]
        del runs[at + 1]
    return runs


def _apportion(total: int, weights: Sequence[float]) -> List[int]:
    """Whole seconds per beat, summing to exactly ``total``.

    Proportional to ``weights`` where it can be, and floored at
    MIN_BEAT_SECONDS. The remainder goes to the longest beats rather than the
    first, so rounding never turns the scene's principal framing into its
    shortest one.
    """
    count = len(weights)
    if count <= 0:
        return []
    if total <= count * MIN_BEAT_SECONDS:
        # No room to differentiate: divide as evenly as whole seconds allow.
        base, extra = divmod(max(total, count), count)
        return [base + 1] * extra + [base] * (count - extra)

    spendable = total - count * MIN_BEAT_SECONDS
    weight_total = sum(w for w in weights if w > 0) or float(count)
    shares = [
        MIN_BEAT_SECONDS + int(spendable * (max(w, 0.0) / weight_total))
        for w in weights
    ]
    # Whatever integer division left behind, given to the biggest beats first.
    remainder = total - sum(shares)
    order = sorted(range(count), key=lambda i: (-weights[i], i))
    position = 0
    while remainder > 0 and order:
        shares[order[position % count]] += 1
        remainder -= 1
        position += 1
    while remainder < 0:
        # Only reachable if the floor pushed the total over; take it back off
        # the biggest beat, which is the one that can afford it.
        biggest = max(range(count), key=lambda i: shares[i])
        if shares[biggest] <= MIN_BEAT_SECONDS:
            break
        shares[biggest] -= 1
        remainder += 1
    return shares


def plan_scene_take(
    scene_seconds: float,
    shots: Sequence[Any],
    backend,
    elements: Sequence[Element] = (),
    start_image: str = "",
    end_image: str = "",
) -> Optional[SceneTake]:
    """This scene as ONE request, or None when the backend cannot cut.

    Returning None is the answer for every endpoint that has always been used
    here, and the caller's per-shot path is unchanged by it -- a backend
    declaring ``max_beats`` of 1 is saying "a scene is a take, and a second
    angle is a second generation", which is true and was the only option.
    """
    if backend is None or not getattr(backend, "multishot", False):
        return None
    usable = [shot for shot in shots or [] if _describe(shot)]
    if not usable:
        return None

    # The length the backend will actually accept, which is not always the
    # length the budget asked for -- see interfaces/video_backend.Duration.
    seconds = backend.duration.send(scene_seconds)
    if not seconds or seconds <= 0:
        return None

    # A scene cannot hold more beats than it has whole seconds to give them.
    room = max(1, int(seconds) // MIN_BEAT_SECONDS)
    limit = min(int(getattr(backend, "max_beats", 1) or 1), room)
    runs = _merge_to_fit(usable, limit)

    weights = [sum(_seconds_of(s, 1.0) for s in run) for run in runs]
    shares = _apportion(int(seconds), weights)

    beats = tuple(
        Beat(
            seconds=share,
            description=" ".join(_describe(s) for s in run).strip(),
            shot_type=(getattr(run[0], "shot_type", "") or "").strip(),
        )
        for run, share in zip(runs, shares)
    )
    trimmed = tuple(
        element
        for element in list(elements)[: max(0, int(getattr(backend, "max_elements", 0)))]
    )
    return SceneTake(
        seconds=int(seconds),
        beats=beats,
        elements=trimmed,
        start_image=start_image,
        end_image=end_image,
    )
