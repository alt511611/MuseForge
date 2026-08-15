"""Acting beats: the micro-expression a scene's emotion actually looks like.

The script gives every scene a two-to-four word emotional tag ("cold
resentment", "tearful reconciliation"). That tag is enough for a human actor
and nowhere near enough for a diffusion model, which draws "resentment" as a
face doing nothing in particular -- the flat, uncanny stare that reads as
generated the moment a viewer sees it.

This module turns the tag into two CONCRETE, anatomically specific beats:

* ``onset`` -- what the face is holding at the top of the shot: the restraint,
  the thing being kept down.
* ``peak``  -- what it breaks into by the end: the tear that finally goes over
  the lid, the jaw that sets, the smirk that escapes.

Why two and not one. Kling's image-to-video takes an optional ``last_image``
(see tools/video_model_router._ENDPOINT_FIELDS), and given a start frame and
an end frame it has to physically INTERPOLATE between them. So a performance
can be staged rather than described: render the onset as the start frame, edit
that same frame into the peak, and the model is obliged to play the change --
the tear travelling, the chin going. Asking one prompt for "she is sad" gets a
still face that drifts; asking for a journey between two faces gets acting.

The map is deterministic on purpose. An LLM asked for the micro-expression
gives a different answer every run, which is fine for one shot and wrong for a
product: the same scene emotion must produce the same performance vocabulary
every time, or a re-render silently re-acts the film. The storyboard agent
still writes ``expression_desc`` in its own words; this only guarantees the
floor beneath it, and supplies the peak the agent is never asked for.

``voice_tag`` comes from the same table because it is the same decision.
ElevenLabs v3 reads bracketed audio tags inline in the text ("[whispers]",
"[sighs]"), so the emotion that picks the face may as well pick the delivery;
splitting them across two tables is how a scene ends up with a crying face and
a cheerful line reading.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

TRUTHY = {"1", "true", "yes", "on"}
FALSY = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class ActingBeat:
    """One emotion's performance, in the three places it has to land."""

    label: str
    #: Held-back face for the START frame. Restraint, not the emotion itself.
    onset: str
    #: Where it breaks by the END frame. This is the thing the video model
    #: interpolates toward, so it must be physically observable -- a muscle,
    #: a tear, a breath -- never an abstraction like "she feels betrayed".
    peak: str
    #: ElevenLabs v3 audio tag for the line delivery, without brackets.
    #: Empty means "say it straight"; a tag on every line is worse than none,
    #: because the delivery stops meaning anything.
    voice_tag: str = ""
    #: ElevenLabs `stability` for this beat, in [0, 1]. Lower is more
    #: expressive and less predictable; the provider's default is 0.5.
    stability: float = 0.5


#: Matched against the scene's emotion tag, first hit wins, so the more
#: specific keys must come first within each beat's tuple. Keys are matched as
#: substrings of a casefolded tag -- "tearful reconciliation" hits "tear".
#:
#: Turkish keys sit alongside the English ones because the screenwriter writes
#: the whole script in the drama's language (see ScreenwriterAgent.
#: LANGUAGE_CLAUSE), and the emotion tag is prose like everything else -- an
#: English-only table silently degrades every non-English drama to the neutral
#: fallback, which is precisely the flat face this module exists to prevent.
_BEATS: Tuple[Tuple[Tuple[str, ...], ActingBeat], ...] = (
    (
        ("tear", "grief", "sorrow", "mourn", "heartbreak", "weep", "cry",
         "gözyaş", "keder", "hüzün", "yas", "ağla"),
        ActingBeat(
            label="grief",
            onset=(
                "holding it in: jaw tight, lips pressed thin, eyes glassy but "
                "dry, breath held high in the chest"
            ),
            peak=(
                "the hold breaks: a single tear spilling over the lower lid and "
                "running, chin dimpling and trembling, eyebrows pulled up and "
                "together at the inner corners, shoulders dropping on a "
                "released breath"
            ),
            voice_tag="voice breaking",
            stability=0.3,
        ),
    ),
    (
        ("rage", "fury", "anger", "angry", "wrath", "seething",
         "öfke", "hiddet", "kızgın"),
        ActingBeat(
            label="rage",
            onset=(
                "contained: jaw set, nostrils flared, a muscle ticking at the "
                "temple, gaze locked and unblinking"
            ),
            peak=(
                "it comes through: jaw clenched hard enough to show the masseter, "
                "brows driven down and together, nostrils wide, colour rising in "
                "the face, tendons standing in the neck"
            ),
            voice_tag="furious",
            stability=0.25,
        ),
    ),
    (
        ("contempt", "scorn", "disdain", "smirk", "mock", "sneer", "condescend",
         "küçümse", "alay", "hor gör"),
        ActingBeat(
            label="contempt",
            onset="unreadable: face still, eyes half-lidded, mouth relaxed",
            peak=(
                "one corner of the mouth pulling up and back into a smirk, a "
                "single eyebrow lifting, chin tipping up so the look comes down "
                "the nose, eyes narrowing"
            ),
            voice_tag="mockingly",
            stability=0.4,
        ),
    ),
    (
        ("fear", "terror", "dread", "afraid", "panic", "scared",
         "korku", "dehşet", "panik"),
        ActingBeat(
            label="fear",
            onset="alert and still: eyes wide, lips slightly parted, body frozen",
            peak=(
                "eyes flaring white above the iris, upper eyelids straining, brows "
                "raised and drawn together, mouth pulled wide and open, a visible "
                "swallow moving the throat"
            ),
            voice_tag="fearfully",
            stability=0.3,
        ),
    ),
    (
        ("shock", "disbelief", "stunned", "reveal", "betray", "caught",
         "şok", "inanamama", "ifşa", "ihanet"),
        ActingBeat(
            label="shock",
            onset="mid-thought, unguarded: expression still settled on the last moment",
            peak=(
                "the face catching up all at once: eyes snapping wide, eyebrows "
                "shooting up, jaw dropping slightly open, head drawing back a "
                "fraction, blood leaving the cheeks"
            ),
            voice_tag="breathless",
            stability=0.3,
        ),
    ),
    (
        ("resolve", "resolute", "determin", "decision", "steel", "commit", "defiance",
         "kararlı", "azim", "meydan"),
        ActingBeat(
            label="resolve",
            onset="uncertain: eyes moving, weight shifting, mouth unsettled",
            peak=(
                "everything settling: gaze fixing on one point and stopping, chin "
                "lowering slightly, lips compressing into a firm line, shoulders "
                "squaring and dropping back"
            ),
            voice_tag="firmly",
            stability=0.55,
        ),
    ),
    (
        ("shame", "guilt", "regret", "remorse", "humiliat",
         "utan", "suçluluk", "pişman", "mahcup"),
        ActingBeat(
            label="shame",
            onset="composed, gaze level, holding the other's eyes",
            peak=(
                "the eyes going first: gaze dropping away and down, head turning "
                "slightly aside, chin tucking, a hand rising toward the face, "
                "colour flooding the cheeks and ears"
            ),
            voice_tag="quietly",
            stability=0.45,
        ),
    ),
    (
        ("longing", "yearn", "love", "tender", "affection", "reconcil", "forgive",
         "özlem", "sevgi", "şefkat", "barış", "affet"),
        ActingBeat(
            label="tenderness",
            onset="guarded: face carefully neutral, eyes doing the looking alone",
            peak=(
                "the guard coming down: eyes softening and brimming, the corners "
                "of the mouth lifting into a small helpless smile, head tilting, "
                "the whole face opening toward the other person"
            ),
            voice_tag="softly",
            stability=0.4,
        ),
    ),
    (
        ("relief", "release", "release", "exhale", "resignation", "resigned", "acceptance",
         "rahatla", "teslim", "kabullen"),
        ActingBeat(
            label="release",
            onset="braced: shoulders high, breath held, eyes fixed",
            peak=(
                "the brace letting go: eyes closing for a beat, a long breath "
                "leaving through parted lips, shoulders dropping several "
                "centimetres, the whole face slackening"
            ),
            voice_tag="exhales",
            stability=0.5,
        ),
    ),
    (
        ("suspicion", "doubt", "mistrust", "wary", "guarded", "tense", "confront",
         "şüphe", "güvensiz", "temkinli", "gergin", "yüzleş"),
        ActingBeat(
            label="suspicion",
            onset="pleasant and blank: the social face, giving nothing",
            peak=(
                "the read beginning: eyes narrowing and flicking across the other's "
                "face, one brow drawing down, head angling, the smile staying on "
                "the mouth and leaving the eyes"
            ),
            voice_tag="warily",
            stability=0.45,
        ),
    ),
    (
        ("joy", "triumph", "elation", "delight", "happy",
         "sevinç", "zafer", "mutlu", "neşe"),
        ActingBeat(
            label="joy",
            onset="containing it: mouth pressed, eyes bright and moving",
            peak=(
                "it escaping: cheeks lifting so the eyes crease at the outer "
                "corners, teeth showing, head going back a little, shoulders "
                "rising on a caught breath"
            ),
            voice_tag="laughs",
            stability=0.35,
        ),
    ),
)


#: What a scene with no usable emotion tag still gets. Deliberately not blank:
#: a face that is merely "present" is the failure mode, so even the fallback
#: names a shift the camera can watch happen.
NEUTRAL = ActingBeat(
    label="neutral",
    onset="settled, thinking, eyes on the other person",
    peak=(
        "a small involuntary shift: a blink held a half-beat too long, a swallow, "
        "the mouth tightening at one corner"
    ),
    voice_tag="",
    stability=0.5,
)


#: An ``expression_desc`` at least this long is treated as the agent having
#: done the job itself, and is left alone rather than padded from the map.
ALREADY_SPECIFIC_CHARS = 120


def resolve(emotion: str) -> ActingBeat:
    """The acting beat for a scene's emotion tag. Never raises, never empty."""
    text = (emotion or "").strip().casefold()
    if not text:
        return NEUTRAL
    for keys, beat in _BEATS:
        if any(key in text for key in keys):
            return beat
    return NEUTRAL


def onset_expression(emotion: str, written: str = "") -> str:
    """Start-frame expression: the agent's own words, with the beat behind them.

    The storyboard agent's ``expression_desc`` is kept FIRST when it wrote one
    -- it saw the scene and this table did not -- and the mapped onset follows
    as the anatomical floor. A blank or neutral value falls through to the map
    alone (see StoryboardArtist._ensure_expression for what counts as blank).
    """
    beat = resolve(emotion)
    written = (written or "").strip().rstrip(".")
    if not written:
        return beat.onset
    # The frame prompt runs well over the provider's character budget on a
    # normal two-character scene, and the expression clause is one of the
    # things that gets dropped when it does (see fit_image_prompt's priority
    # ladder). An agent that already wrote a specific, anatomical beat needs
    # no floor under it -- appending one would only make the clause more
    # likely to be cut, which is the opposite of the point.
    if len(written) >= ALREADY_SPECIFIC_CHARS:
        return written
    return f"{written}; {beat.onset}"


def peak_expression(emotion: str) -> str:
    """End-frame expression: where the shot's performance lands."""
    return resolve(emotion).peak


def voice_tag(emotion: str) -> str:
    """ElevenLabs v3 audio tag for this emotion, brackets included.

    Empty string when the beat prescribes no tag, so callers can concatenate
    without checking.
    """
    tag = resolve(emotion).voice_tag
    return f"[{tag}] " if tag else ""


def voice_stability(emotion: str) -> float:
    """ElevenLabs `stability` for this emotion.

    Lower widens the emotional range and loosens the delivery; higher makes it
    predictable and, past about 0.7, monotone. The map keeps every value in
    0.25-0.55 -- far enough from 1.0 that lines are acted, far enough from 0.0
    that a two-word micro-drama line does not come back as a performance of
    something else entirely.
    """
    return resolve(emotion).stability


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in TRUTHY:
        return True
    if raw in FALSY:
        return False
    return default


def is_end_frame_enabled() -> bool:
    """Whether to render the peak as a real END FRAME for interpolation.

    OFF by default, and the reason is a price, not a doubt: it adds one image
    generation per shot (~$0.04 against a scene's ~$0.79, so roughly half a
    point of margin), and it needs an EDIT model configured that MuAPI has not
    been verified to serve on every account -- see
    MuAPIImageGenerator.edit_image and MUSEFORGE_EDIT_MODEL. Everything else in
    this module (onset expressions, voice tags, stability) is free and on.

    Turning it on is safe in the sense that matters: every failure in the
    end-frame path is caught and the shot animates from the start frame alone,
    exactly as it does today.
    """
    return _flag("MUSEFORGE_ACTING_END_FRAME", False)


def end_frame_edit_prompt(
    peak: str,
    shot_visual: str = "",
    character_desc: str = "",
) -> str:
    """Instruction for the image EDIT that turns a start frame into its peak.

    Written as an edit, not as a description of a picture, because that is what
    the model is being asked for: the frame it is given must survive. Anything
    that moves other than the face turns the interpolation into a warp of the
    whole image, which reads as a glitch rather than as a performance -- so the
    prompt spends most of its words forbidding change.
    """
    parts = [
        "Keep this exact photograph: identical framing, identical camera angle "
        "and distance, identical lighting, identical background, identical "
        "clothing, identical hair, identical pose and hand positions.",
        f"Change ONLY the facial expression to: {peak}.",
        "The person must remain the same person, in the same place, at the same "
        "moment -- this is the same frame a fraction of a second later.",
        "Do not re-frame, do not zoom, do not move the camera, do not change "
        "what is in the background.",
    ]
    if character_desc.strip():
        parts.append(f"The person is {character_desc.strip()}.")
    if shot_visual.strip():
        parts.append(f"Scene, for reference only: {shot_visual.strip()}")
    return " ".join(parts)


def describe(emotion: str) -> Dict[str, Optional[str]]:
    """Everything this module decides for one emotion, for logs and job meta."""
    beat = resolve(emotion)
    return {
        "beat": beat.label,
        "onset": beat.onset,
        "peak": beat.peak,
        "voice_tag": beat.voice_tag or None,
        "stability": beat.stability,
    }
