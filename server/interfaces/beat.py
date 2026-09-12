"""One beat of a scene, and what it takes to shoot it again.

A retake is a roll of the dice, and the roll being replaced is usually 90%
right -- that sentence is already in this codebase, on the endpoint that
restores an earlier take, and it is just as true one level down. A scene is
covered in several framings (the storyboard designs them, and a native-audio
take carries them as beats inside one generation), and the thing a director
actually says is "the second one, again". What the product could do was
re-roll the whole scene: the two framings that were right went back in the bin
with the one that was not, and came back different.

The information needed to do better was already being written down. Every
scene's record carries one entry per BEAT -- its length, its framing, how many
of the scene's lines it says -- because the pacing, subtitle and lip-sync
passes all need it. This module reads the same record as a TIMELINE: beat two
of this scene occupies seconds 4.0 to 9.0 of its clip. That is the whole
mechanism. The head and the tail of the existing clip are kept, one beat is
re-shot, and the three are joined -- which is an edit, not a re-render, and it
is what closes the gap between "retake the scene" and writing a full NLE.

WHAT A BEAT RETAKE IS NOT. It replaces PICTURE. Two kinds of scene therefore
cannot have one, and both refuse loudly rather than delivering something
subtly broken:

* a scene that SPEAKS FOR ITSELF (the take came back with its own audio) --
  the beat's voice is inside the picture being replaced, and a re-shot beat
  would either go silent or say something else in a different voice;
* a scene whose mouths were LIP SYNCED -- the sync drove the mouth across the
  clip it was given, and the new beat was never in that clip.

Both are answered by the scene retake that already exists, which is why the
refusal names it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

#: A beat shorter than this is not a beat, it is a seam. Below it the head and
#: tail trims would be measuring a window narrower than the join that replaces
#: it, and the arithmetic stops meaning anything.
MIN_BEAT_SECONDS = 1.0


@dataclass(frozen=True)
class BeatWindow:
    """Where one beat sits inside its scene's clip, and what it was shot from."""

    index: int
    start: float
    seconds: float
    shot_type: str = ""
    description: str = ""
    line_count: int = 0

    @property
    def end(self) -> float:
        return self.start + self.seconds


def _seconds_of(shot: Mapping[str, Any]) -> float:
    """How long this beat holds.

    Two spellings, because two renderers wrote these records: a take's beats
    carry ``seconds``, and a scene assembled from separate generations carries
    the storyboard shot's own ``duration_seconds`` (and ``deliver_seconds``
    when the two differ -- see interfaces/shot_plan, where a master is
    generated long and delivered short).
    """
    for key in ("deliver_seconds", "seconds", "duration_seconds"):
        try:
            value = float(shot.get(key) or 0.0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0.0


def windows_of(shots: Sequence[Mapping[str, Any]]) -> List[BeatWindow]:
    """Every beat of one scene, as a window into that scene's clip.

    Laid end to end in cut order, which is how the clip was assembled in both
    renderers: beats of a take are cut inside one generation in the order they
    were asked for, and separate shots are concatenated in the order they were
    designed.
    """
    windows: List[BeatWindow] = []
    start = 0.0
    for index, shot in enumerate(shots or []):
        seconds = _seconds_of(shot)
        windows.append(
            BeatWindow(
                index=index,
                start=start,
                seconds=seconds,
                shot_type=str(shot.get("shot_type") or ""),
                # Two spellings again: a take's beat records the prose it was
                # shot from as `description`, a designed shot as `visual_desc`.
                description=str(
                    shot.get("description") or shot.get("visual_desc") or ""
                ),
                line_count=int(shot.get("line_count") or 0),
            )
        )
        start += seconds
    return windows


def refusal(
    scene: Mapping[str, Any],
    beat_index: int,
    lipsynced_scenes: Optional[Sequence[int]] = None,
) -> Optional[str]:
    """Why this beat cannot be re-shot on its own, or None when it can.

    Written as a sentence for the user, because every one of these is a case
    where the scene retake IS the answer and they need to be told that rather
    than told "400".
    """
    shots = list(scene.get("shots") or [])
    number = beat_index + 1
    scene_number = int(scene.get("index", 0)) + 1

    if not shots:
        return (
            f"Scene {scene_number} was made before shot-by-shot records "
            "existed, so its beats cannot be told apart. Re-shoot the scene "
            "instead."
        )
    if not 0 <= beat_index < len(shots):
        return (
            f"Scene {scene_number} has {len(shots)} shot"
            f"{'s' if len(shots) != 1 else ''}, so there is no shot {number}."
        )
    if len(shots) == 1:
        return (
            f"Scene {scene_number} is a single shot, so re-shooting that shot "
            "IS re-shooting the scene. Use the scene retake, which keeps your "
            "earlier take restorable."
        )
    if scene.get("speaks_for_itself"):
        return (
            f"Scene {scene_number} speaks for itself -- its dialogue was "
            "recorded inside the picture. A single beat cannot be replaced "
            "without losing the voice that is in it, so this one needs a "
            "scene retake."
        )
    clip_index = scene.get("clip_index")
    if clip_index is not None and int(clip_index) in set(lipsynced_scenes or []):
        return (
            f"Scene {scene_number} had its mouths driven from the voice track. "
            "A newly shot beat was never part of that sync and would speak "
            "with a still mouth, so this one needs a scene retake."
        )

    window = windows_of(shots)[beat_index]
    if window.seconds < MIN_BEAT_SECONDS:
        return (
            f"Shot {number} of scene {scene_number} is too short to replace on "
            "its own."
        )
    if not window.description.strip():
        return (
            f"Shot {number} of scene {scene_number} did not keep what it was "
            "shot from, so it can only be re-designed rather than re-shot. "
            "Use the scene retake."
        )
    if not (scene.get("clip_url") or scene.get("clip_path")):
        return (
            f"Scene {scene_number}'s clip is no longer stored, and a beat "
            "retake keeps the rest of that clip. Re-shoot the scene instead."
        )
    return None


def replace(
    shots: Sequence[Mapping[str, Any]],
    beat_index: int,
    rendered: Optional[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """The scene's shot records with one beat replaced by its new take.

    The new record inherits the beat's PLACE in the scene -- its index, its
    length, and how many of the scene's lines it says -- from the record it
    replaces, because none of those changed: the same beat was shot again,
    into the same window, and the subtitle and reframing passes downstream
    read exactly those fields to work out which second of the film belongs to
    whom.
    """
    updated: List[Dict[str, Any]] = [dict(shot) for shot in shots or []]
    if not 0 <= beat_index < len(updated):
        return updated
    previous = updated[beat_index]
    fresh = dict(rendered or {})
    fresh.update(
        {
            "index": previous.get("index", beat_index),
            "seconds": previous.get("seconds"),
            "line_count": previous.get("line_count", 0),
            "shot_type": previous.get("shot_type") or fresh.get("shot_type") or "",
            "description": previous.get("description")
            or fresh.get("visual_desc")
            or "",
            # Kept truthful: the scene is no longer one unbroken generation,
            # whatever it started as. The passes that ask this are deciding
            # whether the picture can be cut into again, and now it has been.
            "one_take": False,
            "retaken": int(previous.get("retaken", 0) or 0) + 1,
        }
    )
    fresh = {key: value for key, value in fresh.items() if value is not None}
    updated[beat_index] = fresh
    return updated
