"""Where the subject is standing, so the crop can stop guessing.

A vertical delivery cut out of a wider frame is a CROP, and a crop is a
composition decision. The one this pipeline made was "the middle", every time,
on the grounds that the middle is where subjects usually are. They are not.

Job a66acd59 is the case worth naming, and it is already named in
script2video.build_geometry_filters: its takes came back 960x960 on a 9:16
order, so every scene was conformed by discarding 44% of its width -- and what
lived in that 44% was the second character. The raw takes are properly staged
over-the-shoulder two-shots; the delivered film is one woman with a stray hand
at the edge of frame. It read as a storyboard that never covered him. It was a
centre crop.

THE PIPELINE ALREADY KNOWS WHERE THE FACES ARE. Not approximately, and not by
looking at pixels: it PUT them there. Every frame prompt in a two-hander
carries the same locked axis (script2video.build_screen_direction_clause, and
the storyboard artist's own 180-degree rule):

    first visible character  -> frame-LEFT, looking screen-right
    second visible character -> frame-RIGHT, looking screen-left
    ...in every scene, INCLUDING singles and over-the-shoulder shots.

That rule exists so shots of one conversation do not flip sides between
scenes. It is deterministic, it is derived from character ORDER rather than
from anything a model decides per scene, and it is stated in the prompt of
every frame the film is built out of. So by the time a crop runs, the side of
frame each character occupies is a fact the pipeline wrote down -- and the
crop step was the only stage that never asked.

WHAT THIS MODULE IS NOT. It is not face detection: nothing here opens an
image, and no provider is called. It converts what the film already decided
(who is in this beat, which side the axis put them on, how tight the framing
is) into a crop offset, and it weights that offset by how sure it is -- a
model that ignored the eyeline rule leaves a subject somewhere this module did
not predict, and a HALF-applied correction still keeps them in frame where a
confident wrong one would cut them out. At zero confidence the offset is the
centre crop this pipeline has always done, exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

#: The two positions the locked axis puts a two-hander in, as a fraction of
#: frame width. Thirds rather than halves: that is where the rule of thirds
#: puts a subject with lookroom, and it is what "frame-left" means to the
#: image models being prompted with it.
FRAME_LEFT = 1.0 / 3.0
FRAME_RIGHT = 2.0 / 3.0

#: How far off centre a SINGLE sits, by framing scale. A close-up fills the
#: frame with a face and can only lean; a wide has room to place a body a
#: third of the way in. Applied in the direction the axis gives the character,
#: so a single of the frame-left player sits left of centre with their
#: lookroom on the right -- which is exactly what the frame prompt asked the
#: image model for.
LOOKROOM_BY_SCALE: Dict[str, float] = {
    "extreme close-up": 0.05,
    "close-up": 0.08,
    "medium": 0.12,
    "wide": 0.17,
}

#: Framing scales, and the words that name them. Read off ``shot_type``, which
#: is written in English by our own storyboard prompt (it is an instruction to
#: an image model, not prose for a viewer) and therefore does not move when the
#: drama is written in another language.
_SCALE_WORDS: Sequence[Tuple[str, Tuple[str, ...]]] = (
    ("extreme close-up", ("extreme close", "ecu", "macro")),
    ("close-up", ("close", "cu", "portrait")),
    ("wide", ("wide", "establishing", "long shot", "master", "full shot")),
    ("medium", ("medium", "mid", "cowboy", "waist")),
)

#: Framings that hold BOTH players. A crop cannot favour one without losing
#: the other, so these stay centred however confident the cast reading is --
#: the loss is real and is reported by the caller, not hidden by a lean.
_TWO_HANDER_WORDS = ("two shot", "two-shot", "2 shot", "over the shoulder", "over-the-shoulder", "ots")

#: How sure the reading is, by where it came from. These are the weights the
#: offset is scaled by, so they are not decoration: at 0.0 the crop is the
#: centre crop this pipeline shipped before this module existed.
#:
#: Nothing here reaches 1.0. The axis is a prompt instruction, and a delivered
#: job (21e3d767-bce) lost that instruction to the prompt budget in every
#: single frame and swapped its players across three of four two-shots. A
#: correction that assumes perfect compliance turns that job's every scene
#: into a crop of the wrong person; a half-applied one still has them in
#: frame.
CONFIDENCE_SPEAKER = 0.75  # one named speaker, axis known, single framing
CONFIDENCE_CAST = 0.5  # one character in the scene, no line in this beat
CONFIDENCE_HEADROOM = 0.45  # the vertical rule, which is about faces in general
CONFIDENCE_NONE = 0.0

#: Vertical anchor for a crop that takes from the top and bottom. Faces do not
#: sit at the vertical centre of a frame: headroom puts eyes at about the upper
#: third, which is why a centre crop of a square take into 16:9 slices the top
#: of a head off and leaves the chest.
HEADROOM_Y = 0.42


@dataclass(frozen=True)
class Anchor:
    """Where the picture's subject is, as a fraction of the frame.

    ``confidence`` is how much of the resulting offset is actually applied.
    See the module docstring: a wrong crop that is fully applied loses the
    subject, and one that is half applied does not.
    """

    x: float = 0.5
    y: float = 0.5
    confidence: float = CONFIDENCE_NONE
    #: Why. Carried for the log and for the shot record, so a reframed film
    #: can be argued with after the fact instead of only looked at.
    reason: str = "centre"

    def with_headroom(self) -> "Anchor":
        """The same anchor, told where faces are vertically.

        Only the axis with slack in it is ever used, so this costs nothing on
        the horizontal crops that are the common case.
        """
        return Anchor(
            x=self.x,
            y=HEADROOM_Y,
            confidence=max(self.confidence, CONFIDENCE_HEADROOM),
            reason=f"{self.reason}+headroom",
        )


CENTRE = Anchor()


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def scale_of(shot_type: str) -> str:
    """``"tight close-up"`` as ``"close-up"``. "" when nothing names a scale."""
    text = _text(shot_type).replace("_", " ")
    for scale, words in _SCALE_WORDS:
        if any(word in text for word in words):
            return scale
    return ""


def is_two_hander_framing(shot_type: str) -> bool:
    """Whether this framing is holding two people on purpose."""
    text = _text(shot_type).replace("_", " ")
    return any(word in text for word in _TWO_HANDER_WORDS)


def sides_from_characters(characters: Sequence[Any]) -> Dict[str, float]:
    """The film's locked axis, as ``name -> x``.

    The SAME rule and the same guard as
    script2video.build_screen_direction_clause, deliberately: that function
    decides what the frame prompts say, this one decides what the crop
    believes, and if the two ever disagree the crop is cutting to a staging
    nobody asked for. Exactly two visible characters, or no axis at all --
    a single has no axis to hold and an ensemble needs real blocking.
    """
    visible = [
        c
        for c in (characters or [])
        if _visible(c) and _name_of(c)
    ]
    if len(visible) != 2:
        return {}
    return {
        _name_of(visible[0]).casefold(): FRAME_LEFT,
        _name_of(visible[1]).casefold(): FRAME_RIGHT,
    }


def _name_of(character: Any) -> str:
    if isinstance(character, Mapping):
        return str(character.get("name") or "").strip()
    return str(getattr(character, "name", "") or "").strip()


def _visible(character: Any) -> bool:
    if isinstance(character, Mapping):
        return bool(character.get("is_visible", True))
    return bool(getattr(character, "is_visible", True))


def speaker_of(line: Any) -> str:
    """Who says this line, from either shape the pipeline stores.

    Dialogue reaches this module as ``{"character": ..., "line": ...}`` from
    the script and as ``"Vera: you're quick"`` from a take's beat, and both
    shapes are on the result of a finished job.
    """
    if isinstance(line, Mapping):
        return str(line.get("character") or "").strip()
    text = str(line or "")
    name, separator, said = text.partition(":")
    if separator and said.strip():
        return name.strip()
    return ""


def anchor_for_speakers(
    speakers: Sequence[str],
    sides: Mapping[str, float],
    shot_type: str = "",
) -> Anchor:
    """Where to point the crop, given who is talking in this beat.

    Centre -- i.e. exactly today's behaviour -- whenever the frame is not
    unambiguously about one person: no axis (a single-hander or an ensemble),
    nobody speaking, both players speaking, or a framing that exists to hold
    them both.
    """
    if not sides:
        return CENTRE
    named = [name.casefold() for name in speakers if str(name or "").strip()]
    on_axis = [name for name in named if name in sides]
    if len(set(on_axis)) != 1:
        return CENTRE
    if is_two_hander_framing(shot_type):
        # Both faces are in this frame by design. Leaning towards the speaker
        # would crop the listener out of a shot whose whole point is the two
        # of them -- and in a micro-drama the listener IS the shot.
        return Anchor(reason="two-hander held whole")
    side = sides[on_axis[0]]
    scale = scale_of(shot_type) or "medium"
    lookroom = LOOKROOM_BY_SCALE.get(scale, LOOKROOM_BY_SCALE["medium"])
    x = 0.5 - lookroom if side < 0.5 else 0.5 + lookroom
    return Anchor(
        x=x,
        confidence=CONFIDENCE_SPEAKER,
        reason=f"{on_axis[0]} {'frame-left' if side < 0.5 else 'frame-right'} ({scale})",
    )


def beat_line_counts(shots: Sequence[Mapping[str, Any]]) -> List[int]:
    """How many of the scene's lines each beat says, in beat order.

    Written by the take planner (scene_take._spread_dialogue) into shot_meta
    as ``line_count``; a scene rendered the old way (one generation per shot)
    has no such split and reports nothing.
    """
    return [int(shot.get("line_count") or 0) for shot in shots or []]


def anchor_for_shot(
    shot: Mapping[str, Any],
    lines: Sequence[Any],
    sides: Mapping[str, float],
) -> Anchor:
    """The anchor for ONE beat, from the lines that beat says."""
    speakers = [speaker_of(line) for line in lines or []]
    return anchor_for_speakers(speakers, sides, str(shot.get("shot_type") or ""))


def anchors_for_scene(
    scene: Mapping[str, Any],
    sides: Mapping[str, float],
) -> List[Tuple[float, Anchor]]:
    """``(seconds, anchor)`` per beat of one scene, in cut order.

    The scene's dialogue is dealt out to its beats in the order the take
    planner dealt it -- ``line_count`` per beat, lines in script order -- so a
    beat gets the speaker it actually shows. A scene with no beat-level split
    comes back as one span covering the whole scene.
    """
    shots = list(scene.get("shots") or [])
    script = scene.get("script") or {}
    dialogue = list(script.get("dialogue") or []) if isinstance(script, Mapping) else []
    if not shots:
        return [(0.0, anchor_for_speakers([speaker_of(l) for l in dialogue], sides))]

    # Who the SCENE is about, for the beats that say nothing themselves. A
    # reaction beat has no line of its own and is still a shot of somebody;
    # leaving it at the centre would drag the scene's average back there and
    # undo the reading its spoken beats paid for. Held at a lower confidence
    # than a beat with a name in it, because it is an inference about this
    # beat rather than a fact about it.
    spoken = [speaker_of(line) for line in dialogue]
    fallback = anchor_for_speakers(spoken, sides)
    if fallback.confidence:
        fallback = Anchor(
            x=fallback.x,
            confidence=min(fallback.confidence, CONFIDENCE_CAST),
            reason=f"{fallback.reason}, scene",
        )

    spans: List[Tuple[float, Anchor]] = []
    cursor = 0
    for shot in shots:
        count = int(shot.get("line_count") or 0)
        lines = dialogue[cursor : cursor + count] if count else []
        cursor += count
        seconds = float(shot.get("seconds") or 0.0)
        anchor = anchor_for_shot(shot, lines, sides) if lines else fallback
        if lines and not anchor.confidence and not is_two_hander_framing(
            str(shot.get("shot_type") or "")
        ):
            # Both players speak in this beat: it is a two-hander whether or
            # not its shot_type says so.
            anchor = CENTRE
        spans.append((seconds, anchor))
    return spans


def scene_anchor(scene: Mapping[str, Any], sides: Mapping[str, float]) -> Anchor:
    """One anchor for a whole scene: the beat anchors, weighted by screen time.

    Used where a crop cannot change inside a scene. Beats that disagree
    average towards the centre, which is the right answer -- a scene that
    cuts between two singles has no single place to point a fixed crop.
    """
    spans = anchors_for_scene(scene, sides)
    if not spans:
        return CENTRE
    total = sum(max(0.0, seconds) for seconds, _ in spans)
    if total <= 0:
        # No durations recorded: weight every beat the same.
        spans = [(1.0, anchor) for _, anchor in spans]
        total = float(len(spans))
    x = sum(anchor.x * seconds for seconds, anchor in spans) / total
    confidence = sum(anchor.confidence * seconds for seconds, anchor in spans) / total
    reasons = {anchor.reason for _, anchor in spans if anchor.confidence > 0}
    return Anchor(
        x=x,
        confidence=confidence,
        reason="; ".join(sorted(reasons)) or "centre",
    )


def anchors_in_cut_order(
    scenes: Sequence[Mapping[str, Any]],
    characters: Sequence[Any],
) -> List[Anchor]:
    """One anchor per scene, in the order the scenes are joined.

    Cut order rather than script order, and positional rather than keyed by
    ``clip_index``: a re-cut reorders the film and rewrites those indices as
    it goes, so the position in the list the caller is holding is the only
    thing that is reliably true of every path.

    An empty list when the film has no locked axis (a single-hander, an
    ensemble): there is then nothing to point a crop at and the caller should
    keep the centre crop.
    """
    sides = sides_from_characters(characters)
    if not sides:
        return []
    return [scene_anchor(scene, sides) for scene in scenes or []]


# --- turning an anchor into a crop -----------------------------------------


def crop_geometry(
    source_width: int,
    source_height: int,
    out_width: int,
    out_height: int,
) -> Optional[Tuple[bool, float, float]]:
    """``(vertical, frame, window)`` for the axis the crop actually takes from.

    The conform scales to COVER and then crops, so exactly one axis has slack
    in it: a landscape master conformed to 9:16 is cropped left/right, a square
    one conformed to 16:9 top/bottom. ``frame`` is that axis's length after the
    scale, ``window`` is the delivered length. None when nothing is being
    cropped at all, which is the normal case -- the frames were generated in
    the ordered shape.
    """
    if min(source_width, source_height, out_width, out_height) <= 0:
        return None
    scale = max(out_width / source_width, out_height / source_height)
    frame_width = source_width * scale
    frame_height = source_height * scale
    slack_x = frame_width - out_width
    slack_y = frame_height - out_height
    if slack_x <= 1 and slack_y <= 1:
        return None
    if slack_x >= slack_y:
        return False, frame_width, float(out_width)
    return True, frame_height, float(out_height)


def crop_fraction(
    anchor_value: float,
    confidence: float,
    frame: float,
    window: float,
) -> float:
    """Where the crop window sits in the slack, as a fraction in [0, 1].

    0 is hard against the left (or top) edge, 1 against the right (bottom),
    and 0.5 is the centre crop this pipeline has always done. The window is
    placed so the subject lands in the MIDDLE of it -- pointing the camera at
    them, which is what a crop that knows where they are should do -- and then
    blended back towards the centre by ``confidence``.

    Expressed as a fraction of the slack rather than in pixels because ffmpeg
    evaluates it against the scaled frame, and a pixel count computed here
    would have to predict that scaler's rounding exactly.
    """
    slack = max(0.0, frame - window)
    if slack <= 0:
        return 0.5
    ideal = (min(1.0, max(0.0, float(anchor_value))) * frame - window / 2.0) / slack
    ideal = min(1.0, max(0.0, ideal))
    weight = min(1.0, max(0.0, float(confidence)))
    return 0.5 + (ideal - 0.5) * weight


def _fraction_expression(axis: str, fraction: float) -> str:
    """``(in_w-out_w)*0.31`` -- the crop offset, in ffmpeg's own terms."""
    dimension = "w" if axis == "x" else "h"
    return f"(in_{dimension}-out_{dimension})*{fraction:.4f}"


def _switch_expression(axis: str, spans: Sequence[Tuple[float, float, float]]) -> str:
    """One offset expression that changes at scene boundaries.

    ``spans`` is ``(start, end, fraction)`` in seconds of the assembled
    master. ffmpeg evaluates a crop's x/y per frame with ``t`` in scope, so a
    film whose scenes want different framings is still ONE crop in ONE encode
    -- the offset simply jumps at the cut, which is where a change of framing
    belongs anyway.
    """
    expression = _fraction_expression(axis, spans[-1][2])
    for _start, end, fraction in reversed(spans[:-1]):
        expression = (
            f"if(lt(t,{end:.3f}),{_fraction_expression(axis, fraction)},{expression})"
        )
    return expression


#: Below this the offset is not worth an expression: half a percent of the
#: slack is well under a pixel on any crop this pipeline performs, and a
#: centre crop written as ``(in_w-out_w)*0.5000`` is the same picture with a
#: less readable filter graph.
MIN_OFFSET = 0.005


def crop_filter(
    source_width: int,
    source_height: int,
    out_width: int,
    out_height: int,
    anchor: Anchor = CENTRE,
    spans: Optional[Sequence[Tuple[float, float, Anchor]]] = None,
) -> str:
    """The ``crop=`` filter for a conform, pointed at the subject.

    Returns the plain centre crop -- character for character what this
    pipeline emitted before this module existed -- whenever there is nothing
    better to say: no axis, no dialogue, no anchors, or no slack on either
    axis. Everything here is an improvement on the centre crop or it is the
    centre crop.
    """
    plain = f"crop={out_width}:{out_height}"
    geometry = crop_geometry(source_width, source_height, out_width, out_height)
    if not geometry:
        return plain
    vertical, frame, window = geometry
    axis = "y" if vertical else "x"

    resolved = [
        (
            start,
            end,
            crop_fraction(
                span_anchor.y if vertical else span_anchor.x,
                span_anchor.confidence,
                frame,
                window,
            ),
        )
        for start, end, span_anchor in (spans or [])
    ]
    if resolved and any(abs(f - 0.5) > MIN_OFFSET for _s, _e, f in resolved):
        offset = _switch_expression(axis, resolved)
    else:
        fraction = crop_fraction(
            anchor.y if vertical else anchor.x, anchor.confidence, frame, window
        )
        if abs(fraction - 0.5) <= MIN_OFFSET:
            return plain
        offset = _fraction_expression(axis, fraction)

    # The axis with no slack is left to ffmpeg's own centring rather than
    # written out as an expression that says the same thing.
    if axis == "x":
        return f"crop={out_width}:{out_height}:{offset}:(in_h-out_h)/2"
    return f"crop={out_width}:{out_height}:(in_w-out_w)/2:{offset}"


def spans_from_durations(
    durations: Sequence[float],
    anchors: Mapping[int, Anchor],
    vertical: bool = False,
) -> List[Tuple[float, float, Anchor]]:
    """``(start, end, anchor)`` per clip, from clip lengths in cut order.

    Clips with no anchor of their own get the centre, so a film where only
    some scenes can be read still reframes the ones that can. ``vertical``
    adds the headroom rule to every span, because a crop that takes from the
    top and bottom is a question about faces rather than about who is
    speaking.
    """
    spans: List[Tuple[float, float, Anchor]] = []
    elapsed = 0.0
    for index, duration in enumerate(durations or []):
        length = max(0.0, float(duration or 0.0))
        anchor = anchors.get(index, CENTRE)
        spans.append((elapsed, elapsed + length, anchor.with_headroom() if vertical else anchor))
        elapsed += length
    return spans


def describe(spans: Sequence[Tuple[float, float, Anchor]]) -> str:
    """One line for the log: which scenes were reframed and why."""
    moved = [
        f"{index + 1}:{anchor.reason}"
        for index, (_start, _end, anchor) in enumerate(spans or [])
        if anchor.confidence > 0
    ]
    if not moved:
        return "centre crop (nothing to point it at)"
    return f"{len(moved)}/{len(spans)} scenes reframed -- " + ", ".join(moved)
