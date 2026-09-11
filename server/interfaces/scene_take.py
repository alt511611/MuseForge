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

import json
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


def _as_spoken(line: str) -> str:
    """``Vera: you're quick`` as ``Vera says: "you're quick"``.

    The quotes are the point. Without them the words sit in the prompt
    looking like more description of the shot, and a model reading "Vera:
    you're quick" as staging notes performs the sense of it rather than
    saying it.
    """
    name, separator, said = line.partition(":")
    if not separator or not said.strip():
        return f'"{line.strip()}"'
    return f'{name.strip()} says: "{said.strip()}"'


#: What a beat's own description may never fall below. Under this it has
#: stopped describing a shot, and a beat with no picture in it is a cut to
#: nowhere -- the model fills the seconds with whatever the last frame implied.
MIN_BEAT_DESCRIPTION = 140

#: Held back from every declared prompt budget. See _fit_beat_prompt.
#:
#: This is not a rounding allowance. It is the margin for the fact that
#: NOBODY HERE KNOWS WHAT THE VALIDATOR COUNTS, and three refusals now say so:
#:
#:   530 `len`, refused by a 512 limit -- the cast clause was prepended after
#:        the fitting, so the budget was measured against the wrong string.
#:   510 `len` / 514 escaped, refused -- which is where wire_length came from.
#:   501 `len` / 503 escaped, refused at a reserve of 8, i.e. measured at 503
#:        against a budget of 504 and refused anyway. Job 49512158's opening
#:        beat; it rebuilds byte for byte out of _fit_beat_prompt.
#:
#: The third one falsifies the second's explanation. For 501 characters to
#: reach 512 the count has to be at least twelve above `len`, and escaping
#: two double quotes buys two. Both structural theories that fit all three
#: land near thirty: the entry as the wire actually carries it,
#: `{"prompt": "...", "duration": "3"}`, is thirty characters of JSON around
#: the string, and the negative prompt this pipeline sends -- "blur, distort,
#: and low quality" -- is thirty characters that a validator summing the two
#: prompts would add. Neither is checkable from here without spending a
#: generation to find out.
#:
#: So the reserve is twice the largest candidate rather than equal to it,
#: because the candidate is still a guess. It leaves 448 characters -- more
#: than three times MIN_BEAT_DESCRIPTION -- and it costs about ten words of a
#: description that routinely has hundreds. The alternative costs the scene:
#: a 422 on a multi-shot endpoint is not a poorer picture, it is no picture.
PROMPT_BUDGET_RESERVE = 64


def wire_length(text: str) -> int:
    """How long this string is to the validator on the other side.

    Not ``len``. A beat measured at 510 characters was refused by an endpoint
    whose limit is 512: the prompt carried four double quotes around its
    spoken lines, and JSON escapes each of them, so what arrived on the wire
    was 514. Curly quotes and any non-ASCII a screenwriter model produces cost
    more again.

    Read this as a FLOOR on the real count rather than as the count itself.
    It is inferred from a refusal, and a later refusal proved it too small: a
    beat measuring 503 here was refused by the same 512 limit. What the extra
    characters are is not known -- see PROMPT_BUDGET_RESERVE, which is the
    margin that stands in for not knowing, and which is why being slightly
    wrong here is survivable.
    """
    return len(json.dumps(text or "")) - 2


#: Words that cannot be the last word of a sentence: they open the clause that
#: follows them, so a cut landing after one leaves the reader -- here, the
#: video model -- holding an unfinished thought. A possessive is the same
#: shape ("the paperback's."), and is caught by the apostrophe rather than by
#: this list, which no list could enumerate.
_DANGLING = frozenset(
    """a an the of in on at to for from with without into onto over under by
    as and or but so nor its his her their our your my this that these those
    is are was were be been being has have had"""
    .split()
)


def _trim(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` on a word boundary, never mid-token.

    A cut sentence is closed with a full stop, and the stop is paid for out
    of the same budget -- otherwise the clause comes back one character over
    and the caller's last-resort truncation lands on the speech instead,
    which is the one part of a beat that must never be cut mid-sentence.

    The last word goes on giving until the sentence can end on it. Before the
    reserve widened, this mattered rarely -- the fitting fired only on a beat
    that overran a budget almost nothing overran. It fires on most beats now,
    and the first one it was measured on came back "The envelope tumbles from
    the paperback's.", which is not a shorter description of the shot, it is
    a sentence about a paperback that stops before saying anything. Dropping
    the dangling word costs two words and buys a clause that closes.
    """
    if limit <= 0:
        return ""
    if wire_length(text) <= limit:
        return text
    # Walk back from the character count, because an escaped character costs
    # more than one and the difference is only knowable by measuring.
    cut = text
    while cut and wire_length(cut) + 1 > limit:
        cut = cut[: len(cut) - max(1, (wire_length(cut) + 1 - limit))]
    cut = cut.rsplit(" ", 1)[0].rstrip(" ,;:-") if " " in cut else cut
    while " " in cut:
        last = cut.rsplit(" ", 1)[1].strip("\"'([").casefold()
        if last not in _DANGLING and not last.endswith(("'s", "\u2019s", "'")):
            break
        cut = cut.rsplit(" ", 1)[0].rstrip(" ,;:-")
    if not cut:
        return text[:limit]
    return cut if cut.endswith(".") else cut + "."


def _spoken_clause(lines: Sequence[str]) -> str:
    """The lines this beat says, as one clause, or "" for a silent beat."""
    said = " ".join(_as_spoken(line) for line in lines if str(line).strip())
    if not said:
        return ""
    return f" Spoken aloud in this shot, exactly as written: {said}"


def _fit_beat_prompt(
    cast: str, framing: str, description: str, lines: Sequence[str], limit: int
) -> str:
    """One beat's prompt, inside the endpoint's per-beat character budget.

    Unlike the frame prompt's ladder, an overrun here is not a degraded
    picture: the endpoint answers 422 and the whole scene fails. A delivered
    take went over by eighteen characters and returned nothing.

    What gives, in order, and why.

    The DESCRIPTION gives first, down to a floor. It is the one part with
    slack -- a storyboard's visual and motion lines are written to be read by
    a text model, not to fit a budget -- and a shorter description still
    describes the shot.

    The SPOKEN LINES give last, and by whole lines. They are the audio: a
    line cut out of the prompt is a line the take does not say, while the
    subtitle burned into the same frame still shows it, which is the exact
    mismatch this prompt exists to prevent. Cutting one mid-sentence would be
    worse than cutting it, so the trim lands on line boundaries.

    The CAST CLAUSE never gives. It is short, and it is the only place the
    model learns that @Element1 is Vera Kessler; without it the tokens in the
    description point at nothing.
    """
    said = list(lines or [])
    spoken = _spoken_clause(said)
    if limit > 0:
        # The wire count above is INFERRED from a refusal, not read off a
        # documented rule, and the reserve is what absorbs the inference being
        # wrong. It was wrong: a beat measured at 503 against a budget of 504
        # was refused all the same, which is why the reserve is now wide
        # enough to cover a rule nobody here has identified. The trade is not
        # close. It costs a few words of a description that has hundreds; the
        # alternative costs the scene.
        limit = max(MIN_BEAT_DESCRIPTION, limit - PROMPT_BUDGET_RESERVE)

    whole = f"{cast}{framing}{description}{spoken}"
    if limit <= 0 or wire_length(whole) <= limit:
        return whole.strip()

    head = f"{cast}{framing}"
    room = max(0, limit - wire_length(head))
    # The description, cut to whatever the speech leaves it, floored -- and
    # closed with a full stop, because a sentence that stops mid-clause runs
    # straight into "Spoken aloud in this shot" and reads as one sentence.
    kept = _trim(description, max(MIN_BEAT_DESCRIPTION, room - wire_length(spoken)))

    # Still over with the description at its floor: whole lines come off the
    # end of the speech until it fits.
    dropped_a_line = False
    while said and wire_length(kept) + wire_length(spoken) > room:
        said.pop()
        spoken = _spoken_clause(said)
        dropped_a_line = True
    if dropped_a_line:
        # Dropping by whole lines overshoots -- it has to, a half sentence is
        # worse than a missing one -- so the description takes back what the
        # speech gave up rather than leaving the budget unspent.
        kept = _trim(description, room - wire_length(spoken))

    assembled = f"{head}{kept}{spoken}".strip()
    return assembled if wire_length(assembled) <= limit else _trim(assembled, limit)


@dataclass(frozen=True)
class Beat:
    """One framing inside a take, and how long it holds."""

    seconds: int
    description: str
    shot_type: str = ""
    #: The lines SAID during this beat, already written "Name: line". Only
    #: filled when the take carries its own audio -- see plan_scene_take.
    dialogue: Tuple[str, ...] = ()

    def as_prompt(self, cast: str = "", limit: int = 0) -> str:
        """What this beat SHOWS, inside ``limit`` characters.

        The seconds used to be written into the text as "Shot 1 (3s): ...",
        which is the syntax Kling's own interface documents and which this
        endpoint rejects outright: it takes an object per beat with its own
        `duration`, so the timing belongs there and repeating it in the prose
        only spends prompt on something the model is already being told.

        ``cast`` is the scene's cast clause, carried on the first beat only,
        and it is assembled HERE rather than by the caller because a caller
        that prepends it afterwards has already spent a budget it did not
        know about -- which is exactly how a 530-character beat reached an
        endpoint that takes 512.
        """
        # The words go in verbatim and in quotes, because on a native-audio
        # backend this is the SCRIPT: the model says what it is given and
        # invents the rest. A take told only what the shot looks like speaks
        # lines nobody wrote -- while the subtitle burned into the same frame
        # comes from the script and says something else, so the viewer both
        # hears and reads the scene, differently.
        framing = f"{self.shot_type}. " if self.shot_type else ""
        return _fit_beat_prompt(
            cast, framing, self.description, self.dialogue, limit
        )

    def as_payload(self, cast: str = "", limit: int = 0) -> dict:
        """One entry of `multi_prompt`.

        `duration` is a STRING enum ("1".."15"), not an integer -- sending the
        number is a 422, and a 422 on this endpoint is the whole take.
        """
        return {
            "prompt": self.as_prompt(cast=cast, limit=limit),
            "duration": str(self.seconds),
        }


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
    #: The endpoint's per-beat prompt budget, copied off the backend at plan
    #: time (interfaces/video_backend.max_prompt_chars). 0 is "unmeasured",
    #: read as no limit, which is what every backend was until one answered
    #: 422 over eighteen characters.
    max_prompt_chars: int = 0

    @property
    def beat_count(self) -> int:
        return len(self.beats)

    def multi_prompt(self) -> List[dict]:
        """The beat list, in cut order, as the endpoint's own objects.

        A list of STRINGS is what this sent first, and the endpoint answered
        with one error per entry: "Input should be a valid dictionary or
        object to extract fields from". Each beat is `{prompt, duration}`.

        The cast clause is applied HERE, on the first beat, rather than by the
        caller afterwards. Prepending it afterwards is how a beat reached the
        endpoint 18 characters over its 512-character budget: the fitting had
        already happened, against a length that was about to change.
        """
        cast = self.cast_clause()
        return [
            beat.as_payload(
                cast=cast if index == 0 else "",
                limit=self.max_prompt_chars,
            )
            for index, beat in enumerate(self.beats)
        ]

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


#: Words per second of delivered speech. Deliberately unhurried: this is used
#: to decide WHICH beat a line falls in, and putting a line one beat early
#: (the model holds it a moment) is a smaller error than putting it one beat
#: late, where it lands over a cut it was never written for.
WORDS_PER_SECOND = 2.5


def _spread_dialogue(
    dialogue: Sequence[str], beats: Sequence[Beat]
) -> List[Tuple[str, ...]]:
    """Which beat each line is said in, laid end to end from the scene's start.

    The scene's speech begins with the scene and runs continuously -- that is
    how the mixer anchors it (idea2video.plan_scene_speech_anchors) and how
    the subtitle rows are timed -- so a line's place in the take is decided by
    when it falls, not by which shot the storyboard happened to describe it
    in. A line whose start lands past the end of the last beat still goes
    somewhere: the last beat, said quickly, rather than nowhere at all.
    """
    per_beat: List[List[str]] = [[] for _ in beats]
    if not per_beat:
        return []
    edges: List[float] = []
    running = 0.0
    for beat in beats:
        running += float(beat.seconds)
        edges.append(running)

    at = 0.0
    for line in dialogue:
        _, _, said = line.partition(":")
        words = len((said or line).split())
        index = next(
            (i for i, edge in enumerate(edges) if at < edge), len(per_beat) - 1
        )
        per_beat[index].append(line)
        at += max(1.0, words / WORDS_PER_SECOND)
    return [tuple(lines) for lines in per_beat]


def plan_scene_take(
    scene_seconds: float,
    shots: Sequence[Any],
    backend,
    elements: Sequence[Element] = (),
    start_image: str = "",
    end_image: str = "",
    dialogue: Sequence[str] = (),
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
    # The words, given to the beats they are said in. Passed only when the
    # take carries its own audio: a scene rendered mute is voiced by the TTS
    # pass and lip-synced afterwards, and telling the video model to speak
    # lines it will not be heard saying only spends prompt.
    spoken = [line for line in (dialogue or []) if str(line).strip()]
    if spoken:
        beats = tuple(
            Beat(
                seconds=beat.seconds,
                description=beat.description,
                shot_type=beat.shot_type,
                dialogue=lines,
            )
            for beat, lines in zip(beats, _spread_dialogue(spoken, beats))
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
        max_prompt_chars=int(getattr(backend, "max_prompt_chars", 0) or 0),
    )
