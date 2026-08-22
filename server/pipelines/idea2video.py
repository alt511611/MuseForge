"""Full idea-to-video orchestration pipeline."""

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from agents.screenwriter import ScreenwriterAgent, ScriptGenerationFailed
from interfaces import ass_captions
from interfaces import subtitles
from interfaces.character import CharacterInScene, DramaScript
from interfaces.film_look import build_film_look_filters
from interfaces import micro_drama
from interfaces.language import DEFAULT_LANGUAGE
from interfaces.second_budget import (
    billable_seconds,
    distribute_budget,
    total_budget_seconds,
)
from interfaces.shot_plan import REACTION as REACTION_ROLE
from interfaces.shot_plan import plan_shot_scales
from interfaces.transitions import plan_transitions
from interfaces.visual_style import resolve as resolve_visual_style
from pipelines.script2video import (
    PipelineCancelled,
    Script2VideoPipeline,
    _make_image_generator,
    apply_color_grade,
    concatenate_videos,
    concatenate_videos_with_transitions,
    download_video,
    trim_to_duration,
    is_scene_transitions_enabled,
    moviepy_encode_kwargs,
    video_encode_args,
)
from tools.muapi_lipsync import is_lipsync_enabled, make_lipsync
from tools.muapi_sfx_generator import MuAPISFXGenerator, is_foley_enabled
from tools.muapi_voice_generator import MuAPIVoiceGenerator, is_dialogue_enabled

logger = logging.getLogger(__name__)


class SceneRegenerationUnavailable(Exception):
    """A single scene cannot be re-rendered for this job.

    Separate from a generation failure because nothing was attempted and
    nothing should be charged: the job predates scene archiving, or its clips
    have already been cleaned up. The API turns this into a 4xx explaining
    which, rather than a 500.
    """


def _make_voice_generator(api_key: str, demo: bool, working_dir: str = ""):
    """Pick the dialogue backend. Defaults to MuAPI, unchanged.

    ``MUSEFORGE_VOICE_PROVIDER=elevenlabs`` goes to ElevenLabs directly, which
    exists because MuAPI's wrapper of that same model rejects the voices its
    own model page publishes -- delivered logs show its id, its published
    label and its bare name all refused for one catalogue voice. Going direct
    also returns per-line timings, so captions on that path are measured
    rather than estimated. Lazy-imported so a deployment that never sets the
    variable does not import httpx clients it will not use.
    """
    if os.environ.get("MUSEFORGE_VOICE_PROVIDER", "muapi").strip().lower() == "elevenlabs":
        from tools.elevenlabs_voice_generator import ElevenLabsVoiceGenerator

        return ElevenLabsVoiceGenerator(
            os.environ.get("ELEVENLABS_API_KEY", ""),
            demo=demo,
            working_dir=working_dir,
        )
    return MuAPIVoiceGenerator(api_key, demo=demo)


def _make_music_generator(api_key: str, demo: bool):
    """Pick the music-generation backend. Defaults to MuAPI unchanged.
    MUSEFORGE_MUSIC_PROVIDER=falai opts into fal.ai Beatoven
    (endpoint ``beatoven/music-generation``). Lazy-imported.
    """
    provider = os.environ.get("MUSEFORGE_MUSIC_PROVIDER", "muapi")
    if provider == "falai":
        from tools.falai_music_generator import FalAIMusicGenerator

        return FalAIMusicGenerator(os.environ.get("FAL_KEY", ""), demo=demo)
    from tools.muapi_music_generator import MuAPIMusicGenerator

    return MuAPIMusicGenerator(api_key, demo=demo)


# Watermark applies to the Free plan only — Creator and Pro are watermark-free.
# This is the ONE real, enforced differentiator behind the "No watermark" /
# "Watermarked" pricing copy (see client/lib/i18n plan_*_features).
WATERMARK_PLANS = {"free"}
WATERMARK_TEXT = "MuseForge"

# moviepy's TextClip requires an explicit OpenType/TrueType font path (it has
# no built-in default). We probe a handful of common install locations
# instead of bundling a font file — the Dockerfile installs fonts-dejavu-core
# for exactly this purpose. If none are found, add_watermark() fails open.
_WATERMARK_FONT_CANDIDATES = [
    os.environ.get("MUSEFORGE_WATERMARK_FONT", ""),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]


def _scene_action(scene: Any) -> str:
    if isinstance(scene, str):
        return scene
    if isinstance(scene, dict):
        return str(scene.get("action", ""))
    return str(getattr(scene, "action", ""))


def _scene_dialogue(scene: Any) -> List[Any]:
    if isinstance(scene, str):
        return []
    if isinstance(scene, dict):
        return list(scene.get("dialogue") or [])
    return list(getattr(scene, "dialogue", None) or [])


def caption_only_tracks(dialogue: List[Any], scene_index: int) -> List[Dict[str, Any]]:
    """Subtitle rows for a scene whose voice generation failed.

    The lines are in the script either way -- losing them costs nothing but a
    dead TTS provider. Silence plus no captions turns a written drama into a
    mime show, and the viewer cannot even tell there WAS dialogue; silence
    plus captions is a subtitled film, which is a thing people watch on
    purpose. Deliberately carries no ``audio_url``: the mixer already skips
    rows without one (that is how a scene's second and later lines have always
    reached the SRT), so these can never make it into the audio, and the SRT
    builder already estimates a duration from the words when there is no
    recording to measure.
    """
    tracks: List[Dict[str, Any]] = []
    for item in dialogue or []:
        if isinstance(item, dict):
            character = str(item.get("character", "") or "")
            line = str(item.get("line", "") or "")
        else:
            character = str(getattr(item, "character", "") or "")
            line = str(getattr(item, "line", "") or "")
        if not line.strip():
            continue
        tracks.append(
            {
                "character": character,
                "line": line.strip(),
                "scene_index": scene_index,
                "caption_only": True,
            }
        )
    return tracks


def has_voiced_track(dialogue_tracks: Optional[List[Dict[str, Any]]]) -> bool:
    """Whether any track carries actual speech, as opposed to caption text.

    The two are mixed in one list, so "are there tracks?" stopped being the
    same question as "is anything audible?" the moment captions could outlive
    a failed voice provider.
    """
    return any((t or {}).get("audio_url") for t in dialogue_tracks or [])


def _scene_field(scene: Any, field: str) -> str:
    """Read one director-level field off a scene, whatever shape it is in.

    Legacy/demo scripts store scenes as bare strings and carry none of these
    fields — those degrade to "" and keep the previous behavior.
    """
    if isinstance(scene, str):
        return ""
    if isinstance(scene, dict):
        value = scene.get(field)
    else:
        value = getattr(scene, field, None)
    return "" if value is None else str(value)


def _scene_emotion(scene: Any) -> str:
    """The scene's emotional beat, when the script carries one."""
    return _scene_field(scene, "emotion")


#: Below this a tail is not a cutaway, it is a rounding error, and splitting a
#: clip to protect it costs more than it saves.
MIN_REACTION_TAIL_SECONDS = 0.6


def _reaction_tail_seconds(shots: Optional[List[Dict[str, Any]]]) -> float:
    """How many seconds at the END of a scene clip belong to the cutaway.

    A scene that bought a second angle is delivered as master-then-reaction,
    concatenated into one clip (see interfaces/shot_plan). The lip-sync pass
    drives a mouth across whatever clip it is given and cannot see the cut in
    the middle, so it used to be handed the whole thing -- and the product's
    answer was to refuse the second angle whenever lip sync was on.

    That answer cost the wrong thing. A reaction shot is the OTHER character
    listening; there is no mouth in it to drive. Only the master needs syncing,
    so the tail is measured here, held back from the sync, and concatenated
    again afterwards untouched.

    Returns 0.0 when the scene has no cutaway, which is the overwhelming
    majority of scenes and the path that must stay byte-for-byte unchanged.
    """
    tail = 0.0
    for shot in reversed(shots or []):
        if str(shot.get("role") or "").strip().lower() != REACTION_ROLE:
            break
        seconds = float(
            shot.get("deliver_seconds") or shot.get("duration_seconds") or 0.0
        )
        if seconds <= 0:
            return 0.0
        tail += seconds
    return tail if tail >= MIN_REACTION_TAIL_SECONDS else 0.0


async def _split_off_tail(
    source_path: str, head_path: str, tail_path: str, tail_seconds: float
) -> Tuple[str, Optional[str]]:
    """Cut the last ``tail_seconds`` off a clip, returning ``(head, tail)``.

    Returns ``(source_path, None)`` if the split cannot be made — too short to
    leave a head worth syncing, or ffmpeg trouble. The caller then falls back
    to the previous behaviour rather than losing the scene, because every
    failure here is recoverable and none of them is worth a dropped shot.
    """
    duration = _probe_video_duration(source_path)
    head_seconds = duration - tail_seconds
    if duration <= 0 or head_seconds < MIN_TRIMMED_SECONDS:
        return source_path, None

    try:
        head = await trim_clip(source_path, head_path, 0.0, tail_seconds)
        tail = await trim_clip(source_path, tail_path, head_seconds, 0.0)
    except Exception as exc:
        logger.warning("Could not split a scene from its reaction shot: %s", exc)
        return source_path, None

    # trim_clip fails open by returning its source, which here would mean
    # "head" and "tail" are both the whole clip -- concatenating those would
    # play the scene twice.
    if head == source_path or tail == source_path:
        return source_path, None
    return head, tail


async def _restore_trimmed_length(
    source_path: str,
    synced_path: str,
    remainder_path: str,
    output_path: str,
) -> Optional[str]:
    """Put back the seconds a sync provider trimmed off the end of a take.

    MuAPI's Sync Labs endpoint exposes no ``sync_mode``, and the provider's
    default returns a clip as long as the AUDIO. A line is shorter than its
    scene in nearly every scene ever written, so on the default backend the
    clip always comes back short -- and the length guard that protects the
    runtime then threw away every sync the job had paid for.

    What comes back is the head of the take with its mouth driven; the seconds
    it is missing are the take's own tail, which we still have and which has
    nothing to sync anyway (the line has stopped). Cutting them off the
    original and joining them behind the synced head gives a scene of exactly
    the length it was costed at, with the mouth driven for as long as there is
    speech to drive it.

    Returns None when the join cannot be made or does not come out at the
    right length, which leaves the caller with the behaviour it had: keep the
    unsynced take.
    """
    original = _clip_duration(source_path)
    synced = _clip_duration(synced_path)
    if original is None or synced is None:
        return None
    # A clip that is not a short head of the source is not the trim this
    # repairs -- it is a provider returning something else entirely, and
    # guessing at it would deliver a scene assembled out of the wrong footage.
    if synced < MIN_TRIMMED_SECONDS or synced >= original:
        return None
    if original - synced < MIN_TRIMMED_SECONDS:
        return None

    remainder = await trim_clip(source_path, remainder_path, synced, 0.0)
    # trim_clip fails open by returning its source, which here would be the
    # whole take: joining that behind the synced head plays the scene twice.
    if remainder == source_path:
        return None

    try:
        await concatenate_videos([synced_path, remainder], output_path)
    except Exception as exc:
        logger.warning(
            "Could not rejoin a lip-synced take to the rest of its scene: %s",
            exc,
        )
        return None

    if not _keeps_its_length(source_path, output_path):
        logger.warning(
            "Rejoining a lip-synced take did not restore its length; keeping "
            "the unsynced original."
        )
        return None

    logger.info(
        "Lip-synced clip came back %.2fs against a %.2fs take (the provider "
        "trims to the line); the remaining %.2fs of the take was rejoined "
        "behind it.",
        synced,
        original,
        original - synced,
    )
    return output_path


def _record_take(
    scene: Dict[str, Any], take: int, clip_url: Optional[str], clip_path: Optional[str]
) -> None:
    """Remember this take on the scene, so a later one can be undone.

    A retake is a roll of the dice the customer paid for, and the previous roll
    may well have been the better one -- the reason people re-roll at all is
    that a shot is 90% right and fails in its last second. Without a record of
    what came before, "re-shoot" is a one-way door: the only way back to take 1
    is to buy a take 4 and hope.

    Kept on the scene record rather than in a side table because that is what
    survives the Supabase round trip a job row already does, and a history the
    results page cannot read after a restart is not a history.
    """
    history = scene.setdefault("takes", [])
    entry = {
        "take": int(take),
        "clip_url": clip_url or "",
        "clip_path": clip_path or "",
    }
    for existing in history:
        if int(existing.get("take", 0)) == int(take):
            existing.update(entry)
            return
    history.append(entry)
    history.sort(key=lambda t: int(t.get("take", 0)))


def _scene_tension(scene: Any) -> int:
    """Dramatic tension 1-10, or 0 when the script does not carry one."""
    raw = _scene_field(scene, "tension").strip()
    if not raw:
        return 0
    try:
        return max(0, min(10, int(float(raw))))
    except ValueError:
        return 0


#: How many scenes may render at once. Scenes are independent by default, and
#: each is a multi-minute Kling call, so this is the single biggest lever on
#: wall-clock time. Capped to keep a burst of simultaneous requests off the
#: provider (and to bound peak memory during download/assembly).
DEFAULT_SCENE_CONCURRENCY = 3


def _scene_concurrency(total_scenes: int) -> int:
    """Resolve how many scenes to render in parallel.

    Forced to 1 when identity references are chained forward, because in that
    mode scene N's reference image is scene N-1's finished frame -- rendering
    them together would race and silently fall back to the locked portrait,
    quietly discarding the very continuity that mode exists to provide.
    """
    from pipelines.script2video import is_dynamic_reference_enabled

    if is_dynamic_reference_enabled():
        return 1
    raw = os.environ.get("MUSEFORGE_SCENE_CONCURRENCY", "").strip()
    if raw:
        try:
            configured = int(raw)
        except ValueError:
            logger.warning(
                "Invalid MUSEFORGE_SCENE_CONCURRENCY=%r, using %s",
                raw,
                DEFAULT_SCENE_CONCURRENCY,
            )
            configured = DEFAULT_SCENE_CONCURRENCY
    else:
        configured = DEFAULT_SCENE_CONCURRENCY
    return max(1, min(configured, max(1, total_scenes)))


def _format_scene_direction(scene: Any) -> str:
    """Render a scene's director-level notes for the storyboard artist.

    Only fields the script actually carries are emitted, so a legacy script
    produces an empty block rather than a wall of empty labels.
    """
    parts = []
    for label, field in (
        ("Dramatic function", "dramatic_function"),
        ("THE TURN — film this moment", "turn"),
        (
            "WHAT CHANGES ABOUT THE PLACE — this is the drama's event and it "
            "must be VISIBLE in this scene's shots, not implied",
            "world_change",
        ),
        ("Subtext (what they really mean)", "subtext"),
        ("Staging", "staging"),
    ):
        value = _scene_field(scene, field).strip()
        if value:
            parts.append(f"{label}: {value}")
    tension = _scene_field(scene, "tension").strip()
    if tension and tension not in ("0", "0.0"):
        parts.append(f"Dramatic tension: {tension}/10")
    return "\n".join(parts)


def _scene_beat_line(scene: Any, number: int) -> str:
    """One line describing what a scene does, for the story-state blocks.

    The turn is what actually changed in that scene, so it is what a later
    scene must keep true and an earlier scene must not have shown yet. Scenes
    with no turn fall back to their action line rather than dropping out —
    a missing beat would silently re-open the door this exists to close.
    """
    beat = _scene_field(scene, "turn").strip() or _scene_action(scene).strip()
    return f"Scene {number}: {beat}" if beat else ""


def _format_story_state(scenes: List[Any], index: int) -> tuple:
    """(already happened, not yet happened) around the scene at ``index``.

    Every scene is storyboarded on its own, with no idea of where it sits in
    the story, so the shot designer used to be free to stage the drama's
    payoff in scene 1 — and did: a story whose stated event was the moment a
    container is opened opened ON the container, already open and glowing,
    with four scenes of build-up behind it. Handing each scene the turns
    behind it and the turns still ahead of it is what makes the order of the
    cut visible to the step that draws it.
    """
    before = [
        line
        for i, scene in enumerate(scenes[:index])
        if (line := _scene_beat_line(scene, i + 1))
    ]
    after = [
        line
        for i, scene in enumerate(scenes[index + 1 :], start=index + 1)
        if (line := _scene_beat_line(scene, i + 1))
    ]
    return "\n".join(before), "\n".join(after)


#: How much of a provider error is worth putting in front of a user. Long
#: enough to carry a validation message and the field it names, short enough
#: not to paste a stack of JSON into the results page.
MAX_REASON_CHARS = 240

#: httpx appends this to every HTTPStatusError. Same words every time, and
#: longer than the budget it was eating.
_MDN_BOILERPLATE = re.compile(
    r"For more information check:\s*https?://\S*", re.IGNORECASE
)

#: Our own retry wrapper's prefix. The attempt count belongs in the log, not
#: in front of the provider's sentence: it is 40 characters of the budget
#: below, on every single failure, and it never varies with the cause.
_RETRY_PREFIX = re.compile(r"^MuAPI request failed after \d+ attempt\(s\):\s*")


def _provider_reason(exc: Exception) -> str:
    """A one-line, user-readable version of a provider failure.

    Collapsed to a single line because these messages arrive with the raw
    response body appended (see MuAPIClient._response_detail), and a wall of
    JSON in a results-page warning is not a message, it is wallpaper.
    """
    text = " ".join(str(exc or "").split())
    # httpx spends most of its message on a link to MDN's page about status
    # codes. It is the same sentence for every failure, it is longer than the
    # cap below, and it pushed the one specific part -- the provider's own
    # explanation -- off the end of the warning the user actually reads.
    text = _MDN_BOILERPLATE.sub("", text).strip()
    text = _RETRY_PREFIX.sub("", text).strip()
    if not text:
        return ""
    if len(text) > MAX_REASON_CHARS:
        text = text[:MAX_REASON_CHARS].rstrip() + "…"
    return text


def _reason_suffix(reasons: List[str]) -> str:
    """Attach the provider's own words to a warning, when it gave any."""
    if not reasons:
        return ""
    return " The voice provider reported: " + " | ".join(reasons)


def _world_state(scenes: List[Any], index: int) -> tuple:
    """(this scene's world change, changes already in force) at ``index``.

    A world change is not a one-shot event: once the city's power dies, it
    stays dead for the rest of the drama. The scene that CAUSES the change
    has to break the locked lighting; every scene after it has to inherit the
    broken state, or the film cuts from a blackout back to a lit harbour.
    """
    current = _scene_field(scenes[index], "world_change").strip() if index < len(scenes) else ""
    earlier = [
        change
        for scene in scenes[:index]
        if (change := _scene_field(scene, "world_change").strip())
    ]
    return current, "; ".join(earlier)


def _format_character_direction(script: DramaScript) -> str:
    """Render per-character performance direction (want / need / arc)."""
    lines = []
    for char in getattr(script, "characters", None) or []:
        bits = [
            f"{label}: {value.strip()}"
            for label, value in (
                ("wants", str(getattr(char, "want", "") or "")),
                ("needs", str(getattr(char, "need", "") or "")),
                ("arc", str(getattr(char, "arc", "") or "")),
            )
            if value.strip()
        ]
        if bits:
            lines.append(f"{char.name} — " + "; ".join(bits))
    return "\n".join(lines)


def _music_style_hint(script: DramaScript) -> str:
    """Describe the drama's emotional arc for the music generator.

    The score previously got ONE word (the drama's mood) for its whole
    length; a track that opens like the first scene and resolves like the
    last sits under the film instead of beside it.
    """
    scenes = getattr(script, "scenes", None) or []
    opening = _scene_emotion(scenes[0]) if scenes else ""
    closing = _scene_emotion(scenes[-1]) if len(scenes) > 1 else ""
    parts = []
    if opening:
        parts.append(f"opening with {opening}")
    if closing and closing != opening:
        parts.append(f"resolving into {closing}")
    theme = (getattr(script, "theme", "") or "").strip().rstrip(".")
    if theme:
        parts.append(f"about: {theme.lower()}")
    return (", ".join(parts) + ".") if parts else ""


def _format_scene_dialogue(dialogue: List[Any]) -> str:
    """Render dialogue lines as "Name: line" text for the storyboard artist.

    The storyboard step previously saw ONLY the scene's action line, so the
    words that carry the scene's emotional turn were invisible to the agent
    choosing which moment to draw — a direct cause of shots that felt
    unrelated to the story.
    """
    lines = []
    for entry in dialogue or []:
        if isinstance(entry, dict):
            character = str(entry.get("character") or "").strip()
            line = str(entry.get("line") or "").strip()
        else:
            character = str(getattr(entry, "character", "") or "").strip()
            line = str(getattr(entry, "line", "") or "").strip()
        if not line:
            continue
        lines.append(f"{character}: {line}" if character else line)
    return "\n".join(lines)


def _even(value: float) -> int:
    """Round a pixel dimension DOWN to the nearest even number.

    4:2:0 chroma subsampling (yuv420p, required for broad player support)
    halves both axes, so an odd width or height cannot be encoded -- x264
    fails outright. Aspect-ratio cropping produces fractional sizes routinely
    (a 640x360 source cropped to 9:16 wants 202.5px), so every computed
    dimension is normalised here. Rounding down never exceeds the source.
    """
    return max(2, int(value) // 2 * 2)


#: Opening fade-in / closing fade-out lengths, seconds. Standard finishing:
#: a hard cut from black into frame 1 (and out of the last frame) reads as
#: unfinished; every professionally delivered short opens and lands softly.
FADE_IN_SECONDS = 0.6
FADE_OUT_SECONDS = 0.9

#: Sample rate every delivered master carries. 48kHz is what platforms,
#: editors and players expect; anything above it is bandwidth spent where no
#: listener can follow.
DELIVERY_SAMPLE_RATE = 48000


def is_finishing_enabled() -> bool:
    """Master finishing pass (fades + loudness normalization). Default ON;
    MUSEFORGE_FINISHING=0 skips it entirely (and its one extra encode)."""
    return os.environ.get("MUSEFORGE_FINISHING", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


async def finalize_master(video_path: str, output_path: str) -> str:
    """One finishing encode: fade in from black, fade out to black, and --
    when the video carries audio -- matching audio fades plus EBU R128
    loudness normalization to -14 LUFS (the delivery loudness streaming
    platforms normalize to; an unnormalized mix plays back unpredictably
    quiet or hot next to everything else the viewer watches).

    Single pass so it costs ONE encode at the shared CRF-18 profile, not one
    per effect. Fails open: any error ships the un-finished video rather
    than failing the job, matching the rest of the assembly chain.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    def _copy_through() -> str:
        if os.path.abspath(video_path) != os.path.abspath(output_path):
            with open(video_path, "rb") as src, open(output_path, "wb") as dst:
                dst.write(src.read())
        return output_path

    try:
        from moviepy import VideoFileClip

        with VideoFileClip(video_path) as clip:
            duration = float(clip.duration or 0)
            has_audio = clip.audio is not None
            width, height = (clip.size or (0, 0))
    except Exception as exc:
        logger.warning("Finishing pass could not probe video, skipping: %s", exc)
        return _copy_through()

    # Too short to fade meaningfully -- don't eat the whole clip with fades.
    if duration < (FADE_IN_SECONDS + FADE_OUT_SECONDS) * 2:
        return _copy_through()

    fade_out_start = max(0.0, duration - FADE_OUT_SECONDS)
    # Film-look filters ride along in THIS encode. Cadence, grain and matte
    # each want a full re-encode of their own; folding them into the pass that
    # already re-encodes for the fades keeps it at one generation loss instead
    # of four. Order matters: resample and matte before grain, so the noise is
    # generated at the delivered frame rate and is not itself resampled.
    look_filters, look_args = build_film_look_filters(width, height)
    vf = ",".join(
        look_filters
        + [
            f"fade=t=in:st=0:d={FADE_IN_SECONDS}",
            f"fade=t=out:st={fade_out_start:.3f}:d={FADE_OUT_SECONDS}",
        ]
    )
    ffmpeg_binary = os.environ.get("MUSEFORGE_FFMPEG_BINARY") or shutil.which("ffmpeg")
    if not ffmpeg_binary:
        try:
            import imageio_ffmpeg

            ffmpeg_binary = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_binary = "ffmpeg"

    cmd = [ffmpeg_binary, "-y", "-i", video_path, "-vf", vf]
    if has_audio:
        cmd += [
            "-af",
            (
                f"afade=t=in:st=0:d={FADE_IN_SECONDS},"
                f"afade=t=out:st={fade_out_start:.3f}:d={FADE_OUT_SECONDS},"
                # I: integrated loudness target; TP: true-peak ceiling;
                # LRA: allowed loudness range. -14 LUFS / -1.5 dBTP is the
                # common streaming delivery spec.
                "loudnorm=I=-14:TP=-1.5:LRA=11,"
                # loudnorm works internally at 192kHz and leaves the stream
                # there, so ffmpeg picks whatever rate the encoder will take
                # next -- measured on a delivered master: 96kHz AAC. Nothing
                # in a drama needs it, no platform asks for it, and at a fixed
                # 192kbps the extra bandwidth is spent on inaudible headroom
                # instead of on the dialogue. 48kHz is the delivery standard.
                f"aresample={DELIVERY_SAMPLE_RATE}"
            ),
            "-ar",
            str(DELIVERY_SAMPLE_RATE),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]
    cmd += [*look_args, *video_encode_args(), output_path]

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode == 0 and os.path.isfile(output_path):
            return output_path
        logger.warning(
            "Finishing pass failed (exit=%s), shipping un-finished video: %s",
            process.returncode,
            stderr.decode("utf-8", errors="replace")[-1000:],
        )
    except Exception as exc:
        logger.warning("Finishing pass unavailable, shipping un-finished video: %s", exc)
    try:
        os.unlink(output_path)
    except OSError:
        pass
    return _copy_through()


def _find_watermark_font() -> Optional[str]:
    for path in _WATERMARK_FONT_CANDIDATES:
        if path and os.path.isfile(path):
            return path
    return None


def resolve_ffmpeg_binary() -> str:
    """The ffmpeg to shell out to, falling back to moviepy's bundled build."""
    binary = os.environ.get("MUSEFORGE_FFMPEG_BINARY") or shutil.which("ffmpeg")
    if binary:
        return binary
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


async def mux_silent_audio(video_path: str, output_path: str) -> bool:
    """Copy ``video_path`` to ``output_path`` with a silent AAC track added.

    Done in ffmpeg rather than moviepy, for two reasons that both cost a
    production job:

      * synthesising silence as a Python AudioClip and letting moviepy write
        it produced a file whose CONTAINER DURATION was ~2000x the video's (a
        3-second clip muxed to 5923 seconds, a 30-second drama to 13 hours).
        Every later stage then tried to decode a million frames, and the job
        that should have finished in a minute ran until someone killed it;
      * ``-c:v copy`` means the picture is not re-encoded at all. The old path
        re-encoded the entire master through moviepy to add nothing but
        silence, paying a full generation loss and several minutes for it.

    ``anullsrc`` is an infinite source, so ``-shortest`` is what ends the
    file -- without it ffmpeg would happily write silence forever, which is
    the same failure in a different tool.

    Returns True when the muxed file was written, False when the caller should
    fall back to shipping the video as it is.
    """
    try:
        process = await asyncio.create_subprocess_exec(
            resolve_ffmpeg_binary(),
            "-y",
            "-i",
            video_path,
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode == 0 and os.path.getsize(output_path) > 0:
            return True
        logger.warning(
            "Could not add a silent audio track (ffmpeg %s): %s",
            process.returncode,
            (stderr or b"").decode("utf-8", "replace")[-500:],
        )
    except Exception as exc:
        logger.warning("Could not add a silent audio track: %s", exc)
    return False


#: Level each layer sits at before the mix, relative to the dialogue it is
#: sharing a film with.
#:
#: These are not taste. Speech is the only layer whose intelligibility is
#: non-negotiable, so it runs at unity and everything else is placed under it:
#: the score far enough down to be felt rather than followed, and foley close
#: enough to speech to make objects feel present without competing with the
#: words describing them.
MUSIC_LEVEL = 0.55
FOLEY_LEVEL = 0.65

#: Sidechain ducking: how the score gets out of the way of a line, and comes
#: back between lines.
#:
#: The previous mixer scaled music to a flat 20% for the ENTIRE film the
#: moment any line was voiced -- so a drama with three lines in it played its
#: whole score at a fifth of the intended level, including the long stretches
#: with nobody speaking, which is where a score is supposed to do its work.
#: Ducking replaces one permanent decision with a continuous one.
#:
#: ``ratio`` 8 with this threshold lands around -10 to -12dB under speech;
#: ``attack`` is fast enough not to clip the first syllable and ``release``
#: slow enough that the music does not pump between words inside one line.
#: ffmpeg's own read/write timeout for remote inputs, in MICROseconds (its
#: unit, not a typo). 20 seconds: long enough for a slow CDN, short enough
#: that a dead one costs a fallback rather than a hung job.
MIX_NETWORK_TIMEOUT_US = 20_000_000

DUCK_THRESHOLD = 0.045
DUCK_RATIO = 8
DUCK_ATTACK_MS = 15
DUCK_RELEASE_MS = 320


def _ffmpeg_time_ms(seconds: float) -> int:
    """Milliseconds for adelay, never negative (it silently drops the input)."""
    return max(0, int(round(float(seconds or 0.0) * 1000)))


def build_audio_mix_graph(
    music_index: Optional[int],
    dialogue: List[Tuple[int, float]],
    foley: List[Tuple[int, float]],
    duration: float,
) -> Optional[str]:
    """The filter_complex that mixes one drama's audio.

    ``dialogue`` and ``foley`` are (ffmpeg input index, start seconds) pairs;
    ``music_index`` is the score's input index, if there is one. Returns None
    when there is nothing to mix, so the caller can lay down silence instead
    of running an encode that changes nothing.

    The shape, and why:

        dialogue -> adelay -> amix ----------------> [speech] --------+
                                     |                               |
                                     +-> (sidechain) -> ducks music --+--> amix
        music ----> volume -----------------------------------------+
        foley ----> adelay -> volume -> amix ------------------------+

    ``asplit`` on the speech bus is what makes the ducking possible at all:
    sidechaincompress CONSUMES its control input, so the speech that steers
    the compressor cannot also be the speech that reaches the mix.
    """
    chains: List[str] = []
    layers: List[str] = []

    speech_labels: List[str] = []
    for position, (index, start) in enumerate(dialogue):
        label = f"d{position}"
        chains.append(
            f"[{index}:a]adelay={_ffmpeg_time_ms(start)}:all=1,"
            f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
            f"[{label}]"
        )
        speech_labels.append(f"[{label}]")

    speech_bus: Optional[str] = None
    if speech_labels:
        if len(speech_labels) == 1:
            chains.append(f"{speech_labels[0]}acopy[speechraw]")
        else:
            # normalize=0: amix's default divides every input by their count,
            # which would quietly halve a scene's dialogue for the crime of
            # having two lines in it.
            chains.append(
                f"{''.join(speech_labels)}amix=inputs={len(speech_labels)}"
                f":normalize=0:dropout_transition=0[speechraw]"
            )
        speech_bus = "speech"
        if music_index is not None:
            chains.append("[speechraw]asplit=2[speech][sc]")
        else:
            # No music means nothing consumes [sc], and ffmpeg refuses a
            # filtergraph with a dangling output:
            #
            #   Filter 'asplit' has output 0 (sc) unconnected
            #   Error binding filtergraph inputs/outputs: Invalid argument
            #
            # It split unconditionally, so EVERY job with dialogue and no
            # music -- which is most of them, music being a paid Creator/Pro
            # extra -- failed the whole mix (exit 234) and fell back to
            # moviepy. That fallback is where the foley was being lost and
            # where forty minutes of post-processing were going: the ffmpeg
            # path was never once taken on a job like that.
            chains.append("[speechraw]acopy[speech]")

    if music_index is not None:
        chains.append(f"[{music_index}:a]volume={MUSIC_LEVEL}[musicraw]")
        if speech_bus:
            chains.append(
                f"[musicraw][sc]sidechaincompress="
                f"threshold={DUCK_THRESHOLD}:ratio={DUCK_RATIO}"
                f":attack={DUCK_ATTACK_MS}:release={DUCK_RELEASE_MS}[music]"
            )
        else:
            chains.append("[musicraw]acopy[music]")
        layers.append("[music]")

    foley_labels: List[str] = []
    for position, (index, start) in enumerate(foley):
        label = f"f{position}"
        chains.append(
            f"[{index}:a]adelay={_ffmpeg_time_ms(start)}:all=1,"
            f"volume={FOLEY_LEVEL},"
            f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo"
            f"[{label}]"
        )
        foley_labels.append(f"[{label}]")
    if foley_labels:
        chains.append(
            f"{''.join(foley_labels)}amix=inputs={len(foley_labels)}"
            f":normalize=0:dropout_transition=0[foley]"
        )
        layers.append("[foley]")

    if speech_bus:
        layers.append(f"[{speech_bus}]")

    if not layers:
        return None

    if len(layers) == 1:
        chains.append(f"{layers[0]}acopy[mixed]")
    else:
        chains.append(
            f"{''.join(layers)}amix=inputs={len(layers)}"
            f":normalize=0:dropout_transition=0[mixed]"
        )

    # apad + atrim: the mix must be exactly as long as the picture. Shorter and
    # the container's streams disagree about where the file ends (players stop
    # early, some editors refuse the file); longer and the master grows a tail
    # of black. alimiter catches the sum of three layers clipping without
    # squashing the dynamics that make the ducking audible.
    chains.append(
        f"[mixed]apad,atrim=0:{max(0.1, float(duration)):.3f},"
        f"alimiter=limit=0.95,"
        f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]"
    )
    return ";".join(chains)


async def mix_audio_layers(
    video_path: str,
    output_path: str,
    music_url: Optional[str] = None,
    dialogue_tracks: Optional[List[Dict[str, Any]]] = None,
    scene_paths: Optional[List[str]] = None,
    sfx_tracks: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """Mix score, foley and dialogue in ONE ffmpeg pass. None when it can't.

    Three things this does that the moviepy mixer cannot:

    * **The score ducks.** Under each line and back up between them, instead
      of one flat -14dB applied to the whole film (see DUCK_THRESHOLD).
    * **Foley has somewhere to go.** A third bus, laid at each scene's own
      start (see tools/muapi_sfx_generator).
    * **The picture is not re-encoded.** ``-c:v copy``: the mix costs a
      generation loss of nothing, where moviepy re-encodes every frame of the
      master to attach an audio stream to it.

    Returns None rather than raising on any problem, so the caller can fall
    back to the mixer that has always shipped.
    """
    duration = _probe_video_duration(video_path)
    if duration <= 0:
        return None

    dialogue_tracks = dialogue_tracks or []
    sfx_tracks = sfx_tracks or []

    scene_durations = [_probe_video_duration(path) for path in scene_paths or []]
    scene_starts: List[float] = []
    elapsed = 0.0
    for scene_duration in scene_durations:
        scene_starts.append(elapsed)
        elapsed += scene_duration

    # The same speech plan the SRT builder reads, so the words on screen and
    # the words in the air cannot disagree about when they happen.
    anchors = plan_scene_speech_anchors(dialogue_tracks, scene_starts, duration)

    inputs: List[str] = []
    dialogue_inputs: List[Tuple[int, float]] = []
    foley_inputs: List[Tuple[int, float]] = []
    music_index: Optional[int] = None

    def _add_input(source: str) -> int:
        inputs.append(source)
        return len(inputs)  # +1 because input 0 is the video

    if music_url:
        music_index = _add_input(music_url)

    line_offsets: Dict[int, float] = {}
    for track in dialogue_tracks:
        audio_url = str(track.get("audio_url") or "").strip()
        if not audio_url:
            continue  # caption-only row; its words are in the SRT, not the mix
        scene_index = int(track.get("scene_index", 0))
        anchor = anchors.get(
            scene_index,
            scene_starts[scene_index] if 0 <= scene_index < len(scene_starts) else 0.0,
        )
        local = line_offsets.get(scene_index, 0.0)
        start = anchor + local
        if start >= duration:
            continue
        dialogue_inputs.append((_add_input(audio_url), start))
        measured = _probe_audio_duration_seconds(audio_url) or float(
            track.get("duration_seconds") or 0.0
        )
        line_offsets[scene_index] = local + max(0.0, measured) + 0.2

    for track in sfx_tracks:
        audio_url = str(track.get("audio_url") or "").strip()
        if not audio_url:
            continue
        scene_index = int(track.get("scene_index", 0))
        start = (
            scene_starts[scene_index]
            if 0 <= scene_index < len(scene_starts)
            else 0.0
        )
        if start >= duration:
            continue
        foley_inputs.append((_add_input(audio_url), start))

    graph = build_audio_mix_graph(music_index, dialogue_inputs, foley_inputs, duration)
    if not graph:
        return None

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    command = [resolve_ffmpeg_binary(), "-y", "-i", video_path]
    for source in inputs:
        # Music and foley arrive as provider URLs and are read over the
        # network by ffmpeg itself -- no download step, but also no Python
        # timeout around it. A provider whose CDN stalls would otherwise hold
        # the mixing stage open indefinitely at the very end of a paid job.
        if "://" in source:
            command += ["-rw_timeout", str(MIX_NETWORK_TIMEOUT_US)]
        command += ["-i", source]
    command += [
        "-filter_complex",
        graph,
        "-map",
        "0:v",
        "-map",
        "[aout]",
        # The whole reason this path exists at the encode level: the master's
        # picture is copied through untouched.
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        output_path,
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
    except Exception as exc:
        logger.warning("ffmpeg mixer unavailable, falling back to moviepy: %s", exc)
        return None

    if process.returncode == 0 and os.path.isfile(output_path):
        logger.info(
            "Mixed %d dialogue, %d foley and %s music layer(s) with ducking, "
            "picture copied.",
            len(dialogue_inputs),
            len(foley_inputs),
            "1" if music_index is not None else "0",
        )
        return output_path

    logger.warning(
        "ffmpeg mix failed (exit=%s), falling back to moviepy: %s",
        process.returncode,
        stderr.decode("utf-8", errors="replace")[-1000:],
    )
    try:
        os.unlink(output_path)
    except OSError:
        pass
    return None


async def add_background_music(
    video_path: str,
    output_path: str,
    music_url: Optional[str] = None,
    dialogue_tracks: Optional[List[Dict[str, Any]]] = None,
    scene_paths: Optional[List[str]] = None,
    sfx_tracks: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Lay the drama's audio over its picture.

    Tries the ffmpeg mixer first (real ducking, a foley bus, no re-encode of
    the picture) and falls back to the moviepy one that has shipped every
    drama this product has made. Keeping both is deliberate: this is the last
    stage that can turn a finished render into a file with no sound, and a
    silent master is indistinguishable from a broken product.
    """
    mixed = await mix_audio_layers(
        video_path,
        output_path,
        music_url=music_url,
        dialogue_tracks=dialogue_tracks,
        scene_paths=scene_paths,
        sfx_tracks=sfx_tracks,
    )
    if mixed:
        return mixed
    return await _mix_with_moviepy(
        video_path,
        output_path,
        music_url=music_url,
        dialogue_tracks=dialogue_tracks,
        scene_paths=scene_paths,
    )


async def _mix_with_moviepy(
    video_path: str,
    output_path: str,
    music_url: Optional[str] = None,
    dialogue_tracks: Optional[List[Dict[str, Any]]] = None,
    scene_paths: Optional[List[str]] = None,
) -> str:
    """Mix music and timed dialogue once, with dialogue louder than music.

    The FALLBACK mixer. ``mix_audio_layers`` does this in ffmpeg with real
    ducking, a foley layer and no re-encode of the picture; this one stays
    because it is the code that has shipped every drama this product has made,
    and a mixing pass is not a place to have exactly one implementation.

    Its ducking is a blunt instrument by comparison: the score is scaled to a
    fixed 20% for the WHOLE film as soon as any line is voiced, rather than
    dipping under each line and coming back up between them.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    video = None
    opened_audio = []
    final = None
    final_audio = None
    try:
        from moviepy import AudioFileClip, CompositeAudioClip, VideoFileClip

        video = VideoFileClip(video_path)
        dialogue_tracks = dialogue_tracks or []
        layers = []

        # Preserve source audio when present. Generated MuAPI clips are normally
        # silent, but this avoids unexpectedly discarding audio from future models.
        if video.audio is not None:
            layers.append(video.audio)

        if music_url:
            try:
                music = AudioFileClip(music_url).with_duration(video.duration)
                # Dialogue remains at full level; duck music only when speech
                # exists. Caption rows carry no audio, so ducking for them
                # would quiet the ONLY sound the video has left.
                if has_voiced_track(dialogue_tracks):
                    music = music.with_volume_scaled(0.2)
                opened_audio.append(music)
                layers.append(music)
            except Exception as exc:
                logger.warning("Music track could not be loaded; continuing without it: %s", exc)

        scene_durations: List[float] = []
        for path in scene_paths or []:
            scene_clip = None
            try:
                scene_clip = VideoFileClip(path)
                scene_durations.append(float(scene_clip.duration or 0))
            except Exception:
                scene_durations.append(0.0)
            finally:
                if scene_clip is not None:
                    scene_clip.close()

        scene_starts: List[float] = []
        elapsed = 0.0
        for duration in scene_durations:
            scene_starts.append(elapsed)
            elapsed += duration
        line_offsets: Dict[int, float] = {}
        # Where each scene's speech actually begins, which is its picture
        # unless an earlier scene's speech is still running (see
        # plan_scene_speech_anchors). Captions are laid out from the same plan,
        # so the words on screen and the words in the air cannot disagree.
        speech_anchors = plan_scene_speech_anchors(
            dialogue_tracks, scene_starts, float(video.duration or 0.0)
        )

        for track in dialogue_tracks:
            dialogue = None
            try:
                audio_url = track.get("audio_url")
                if not audio_url:
                    # Caption-only rows (ElevenLabs returns one combined file
                    # per scene; later lines carry text for SRT only).
                    continue
                scene_index = int(track.get("scene_index", 0))
                scene_start = speech_anchors.get(
                    scene_index,
                    scene_starts[scene_index]
                    if 0 <= scene_index < len(scene_starts)
                    else 0.0,
                )
                local_start = line_offsets.get(scene_index, 0.0)
                dialogue = AudioFileClip(audio_url)
                # Clipped at the END OF THE FILM and nowhere else. It used to
                # be clipped at the end of the SCENE, which meant a line longer
                # than its shot was cut off mid-word -- audibly, every time,
                # and worse the faster the picture was cut. Letting it run over
                # the join is an audio bridge, which is what makes fast cutting
                # legible in the first place.
                available = float(video.duration or 0.0) - (scene_start + local_start)
                if available <= 0:
                    dialogue.close()
                    continue
                if dialogue.duration > available:
                    dialogue = dialogue.subclipped(0, available)
                dialogue = dialogue.with_start(scene_start + local_start)
                opened_audio.append(dialogue)
                layers.append(dialogue)
                line_offsets[scene_index] = local_start + float(dialogue.duration or 0) + 0.2
            except Exception as exc:
                if dialogue is not None:
                    try:
                        dialogue.close()
                    except Exception:
                        pass
                logger.warning("Dialogue track could not be mixed; skipping it: %s", exc)

        if not layers:
            # Nothing to mix: music off, and either no dialogue or a voice
            # provider that failed. Rather than write a video with NO audio
            # stream at all, lay down a silent one. A track of silence and no
            # track are the same thing to a viewer and very different things
            # to everything else: editors, some phone players and several
            # upload pipelines treat a missing stream as a malformed file, and
            # concatenating a silent master with anything that HAS audio drops
            # to a re-encode or loses the audio outright.
            #
            # Handed to ffmpeg, which copies the picture untouched -- there is
            # no mix to perform, so re-encoding the master through moviepy
            # would spend a full generation loss on adding nothing. It also
            # cannot get the duration wrong, which the moviepy version did:
            # see mux_silent_audio.
            video.close()
            video = None
            if await mux_silent_audio(video_path, output_path):
                return output_path
            # Could not add it -- ship the picture as it is, exactly as before
            # a silent track was ever attempted.
            with open(video_path, "rb") as src:
                data = src.read()
            with open(output_path, "wb") as dst:
                dst.write(data)
            return output_path

        # There is at least one layer here: the no-layer case returned above.
        final_audio = CompositeAudioClip(layers).with_duration(video.duration)
        final = video.with_audio(final_audio)
        final.write_videofile(
            output_path, codec="libx264", audio_codec="aac", logger=None,
            **moviepy_encode_kwargs(),
        )
    except Exception as exc:
        logger.warning("Audio mixing failed; shipping silent/source video: %s", exc)
        with open(video_path, "rb") as src:
            data = src.read()
        with open(output_path, "wb") as dst:
            dst.write(data)
    finally:
        if final is not None and final is not video:
            try:
                final.close()
            except Exception:
                pass
        if final_audio is not None:
            try:
                final_audio.close()
            except Exception:
                pass
        if video is not None:
            try:
                video.close()
            except Exception:
                pass
        for audio in opened_audio:
            try:
                audio.close()
            except Exception:
                pass
    return output_path


def _format_srt_timestamp(seconds: float) -> str:
    """SRT timestamp: HH:MM:SS,mmm"""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _estimate_line_duration_seconds(line: str) -> float:
    """Rough spoken duration from text when audio can't be probed (~2.5 words/sec)."""
    words = max(1, len((line or "").split()))
    return max(1.2, min(8.0, words / 2.5))


def _probe_audio_duration_seconds(audio_url: str) -> Optional[float]:
    # A caption-only row has no recording by definition, and asking moviepy to
    # open "" still spawns an FFMPEG_AudioReader that dies before it has a
    # `proc` to close -- which is the `AttributeError: 'FFMPEG_AudioReader'
    # object has no attribute 'proc'` traceback that fills the job log of every
    # drama whose voice provider failed, once per line, looking like the crash
    # that silenced it rather than a swallowed no-op.
    if not (audio_url or "").strip():
        return None
    try:
        from moviepy import AudioFileClip

        clip = AudioFileClip(audio_url)
        try:
            duration = float(clip.duration or 0)
            return duration if duration > 0 else None
        finally:
            clip.close()
    except Exception:
        return None


#: Breath between two spoken lines, so consecutive captions do not swap on the
#: same frame.
CAPTION_GAP_SECONDS = 0.2

#: Air between one cue and the next. Two frames at 24fps: enough that a change
#: of caption registers as a change, short enough not to read as a dropout.
CUE_GAP_SECONDS = 0.08


def _scene_boundaries(scene_paths: Optional[List[str]]) -> List[float]:
    """Absolute start time of each scene, plus the end of the last one.

    One entry longer than the scene list on purpose: a line belonging to the
    final scene needs somewhere to stop just as much as the others do. A scene
    whose duration could not be probed contributes 0, which collapses its span
    to nothing -- read downstream as "unknown", never as "no room".
    """
    starts: List[float] = []
    elapsed = 0.0
    for path in scene_paths or []:
        starts.append(elapsed)
        duration = 0.0
        scene_clip = None
        try:
            from moviepy import VideoFileClip

            scene_clip = VideoFileClip(path)
            duration = float(scene_clip.duration or 0)
        except Exception:
            duration = 0.0
        finally:
            if scene_clip is not None:
                try:
                    scene_clip.close()
                except Exception:
                    pass
        elapsed += duration
    starts.append(elapsed)
    return starts


#: Silence left between one scene's speech and the next scene's, when the
#: first has run past its own picture. Long enough to read as a new line
#: rather than as one run-on sentence; short enough not to feel like a gap.
SPEECH_GAP_SECONDS = 0.35


#: Word-at-a-time captions: the vertical-video convention, where the line
#: appears in short bursts timed to the voice instead of as one block held for
#: its whole duration.
#:
#: OFF by default, because it is a house style rather than an improvement: a
#: 16:9 drama wants broadcast-style subtitles, and burning karaoke cues into
#: one would look like a mistake. It needs measured word timings, which only
#: the direct ElevenLabs path returns (tools/elevenlabs_voice_generator.
#: _word_timings) -- with any other voice provider this silently does nothing,
#: which is the correct behaviour: guessing word times from a word count would
#: put the highlight on the wrong word, and a wrong karaoke caption is far
#: more distracting than none.
def is_word_captions_enabled() -> bool:
    return os.environ.get("MUSEFORGE_WORD_CAPTIONS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


#: Words per burst, and the longest a burst may stay up. Three words is about
#: what the eye takes in a single fixation at reading distance on a phone.
WORDS_PER_CAPTION_CHUNK = 3
MAX_CHUNK_SECONDS = 1.4


def chunk_words_into_cues(
    words: List[Dict[str, Any]],
    words_per_chunk: int = WORDS_PER_CAPTION_CHUNK,
    max_seconds: float = MAX_CHUNK_SECONDS,
) -> List[Dict[str, Any]]:
    """Group timed words into short cues, each ending where the next begins.

    A chunk is closed by whichever comes first: the word count, the time
    limit, or a word that ends a sentence -- breaking a cue across "." would
    put the start of the next sentence on screen before it is spoken.
    """
    cues: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []

    def _flush():
        if not current:
            return
        cues.append(
            {
                "text": " ".join(str(word["text"]) for word in current),
                "start": float(current[0]["start"]),
                "end": float(current[-1]["end"]),
            }
        )
        current.clear()

    for word in words or []:
        current.append(word)
        spans = float(current[-1]["end"]) - float(current[0]["start"])
        ends_sentence = str(word["text"]).rstrip()[-1:] in {".", "!", "?", "…", ":"}
        if len(current) >= words_per_chunk or spans >= max_seconds or ends_sentence:
            _flush()
    _flush()
    return cues


def _scene_speech_lengths(
    dialogue_tracks: Optional[List[Dict[str, Any]]],
) -> Dict[int, float]:
    """How long each scene's speech actually runs, keyed by scene index.

    Measured where the provider measured it (ElevenLabs returns per-line
    ``end_seconds`` inside the scene's own audio file) and summed from
    per-line durations otherwise, which is the shape the MuAPI voice path
    returns.
    """
    lengths: Dict[int, float] = {}
    for track in dialogue_tracks or []:
        if not str(track.get("line") or "").strip():
            continue
        # A scene whose voice generation failed carries subtitle rows and no
        # sound (see caption_only_tracks). Counting those as speech would make
        # a LATER scene's real dialogue wait for a silence -- the film would
        # hold its audio back for lines nobody can hear.
        if track.get("caption_only"):
            continue
        scene_index = int(track.get("scene_index", 0))
        if "end_seconds" in track:
            lengths[scene_index] = max(
                lengths.get(scene_index, 0.0), float(track["end_seconds"])
            )
        else:
            duration = float(track.get("duration_seconds") or 0.0)
            if duration <= 0:
                duration = _estimate_line_duration_seconds(
                    str(track.get("line") or "")
                )
            lengths[scene_index] = (
                lengths.get(scene_index, 0.0) + duration + CAPTION_GAP_SECONDS
            )
    return lengths


def plan_scene_speech_anchors(
    dialogue_tracks: Optional[List[Dict[str, Any]]],
    scene_starts: Sequence[float],
    master_duration: float = 0.0,
) -> Dict[int, float]:
    """Where each scene's speech begins on the master timeline.

    Normally that is simply where the scene's picture begins. It stops being
    that as soon as the picture is cut faster than the speech: a four-second
    line under a two-second scene has to finish somewhere, and the two honest
    options are to cut the sentence off or to let it play over the next shot.

    Film has an answer, and it is the second one. Speech carrying across a cut
    (an audio bridge, an L-cut) is ordinary grammar — it is a large part of
    why fast cutting works at all, because the ear stitches what the eye is
    being shown in pieces. Truncating mid-word, which is what this pipeline
    used to do at every scene border, is not grammar; it is a defect the
    viewer hears as a broken file.

    So a scene's speech starts at its picture, or after the previous scene's
    speech has finished, whichever is later. Two consequences worth stating:

    * Speech never overlaps speech. Two characters talking over each other is
      a deliberate effect, not something that should happen because a shot
      ran short.
    * Captions and audio come from THIS function, both of them. They used to
      derive their timings independently from scene offsets, which was fine
      only while neither could move; the moment speech is allowed to drift,
      a second opinion about where it drifted to is a desync.
    """
    lengths = _scene_speech_lengths(dialogue_tracks)
    anchors: Dict[int, float] = {}
    floor = 0.0
    for scene_index in sorted(lengths):
        picture_start = (
            float(scene_starts[scene_index])
            if 0 <= scene_index < len(scene_starts)
            else 0.0
        )
        start = max(picture_start, floor)
        if master_duration > 0:
            # Never anchor past the end of the film: a line placed there is a
            # line nobody can hear, and a caption placed there never shows.
            start = min(start, max(0.0, master_duration - 0.1))
        anchors[scene_index] = start
        floor = start + lengths[scene_index] + SPEECH_GAP_SECONDS
    return anchors


def _lay_out_scene_captions(
    durations: List[float], span: float
) -> List[Tuple[float, float]]:
    """Sequential (start, end) pairs for one scene's lines, inside ``span``.

    Without a real voice track the durations are guesses from the word count,
    and a guess that runs long used to run straight past the cut: the last
    line of a scene stayed on screen over the first line of the next, so the
    drama showed two cues at once -- twice with the SAME speaker named on both
    rows, which reads as a broken renderer rather than a conversation. Since
    the picture is the thing that cannot be stretched, the guesses are what
    give: when a scene's lines do not fit its shot they are scaled down to it
    together, keeping their proportions and their order.

    ``span`` of 0 means the scene's length is unknown (no paths passed, or a
    clip that would not probe), and then nothing is scaled -- an unknown
    boundary is not a boundary to squeeze against.
    """
    gaps = CAPTION_GAP_SECONDS * max(0, len(durations) - 1)
    needed = sum(durations) + gaps
    scale = span / needed if span > 0 and needed > span else 1.0

    placed: List[Tuple[float, float]] = []
    cursor = 0.0
    for duration in durations:
        end = cursor + duration * scale
        placed.append((cursor, end))
        cursor = end + CAPTION_GAP_SECONDS * scale
    return placed


def build_kinetic_ass(
    dialogue_tracks: List[Dict[str, Any]],
    scene_paths: Optional[List[str]] = None,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Kinetic captions for the tracks that carry measured word timings.

    Returns "" when no track does, which is the honest answer for every voice
    provider except the direct ElevenLabs path: the effect depends entirely on
    knowing when each word is said, and a highlight on the wrong word reads as
    a broken player rather than as a style.

    Timing comes from the same speech plan the mixer and the SRT builder use
    (plan_scene_speech_anchors), so all three agree about when a line happens
    even when it has run past its own scene.
    """
    bounds = _scene_boundaries(scene_paths)
    anchors = plan_scene_speech_anchors(
        dialogue_tracks, bounds[:-1], bounds[-1] if bounds else 0.0
    )

    cues: List[ass_captions.CaptionCue] = []
    emphasis: set = set()
    for track in dialogue_tracks or []:
        words = track.get("words")
        if not words:
            continue
        scene_index = int(track.get("scene_index", 0))
        offset = anchors.get(
            scene_index,
            bounds[scene_index] if 0 <= scene_index < len(bounds) - 1 else 0.0,
        )
        emphasis |= ass_captions.emphasis_stems(str(track.get("emphasis") or ""))
        for cue in ass_captions.chunk_into_cues(words):
            cue.start += offset
            cue.end += offset
            for word in cue.words:
                word.start += offset
                word.end += offset
            cues.append(cue)

    return ass_captions.build_ass(cues, width, height, emphasis=emphasis)


def build_srt_from_dialogue_tracks(
    dialogue_tracks: List[Dict[str, Any]],
    scene_paths: Optional[List[str]] = None,
) -> str:
    """Build an SRT document from dialogue tracks.

    Timing mirrors ``add_background_music``: lines within a scene are laid
    out sequentially from that scene's start, with a short gap between lines,
    and the whole scene's worth of captions is kept inside that scene's shot
    (see ``_lay_out_scene_captions``). Tracks may optionally carry explicit
    ``start_seconds`` / ``end_seconds`` (or ``duration_seconds``), which are
    honoured as given -- a caller that timed its own cues knows more than any
    estimate here.
    """
    bounds = _scene_boundaries(scene_paths)
    last_scene = len(bounds) - 2  # bounds carries the final scene's end too
    # The same speech plan the mixer lays the audio down from. Deriving the
    # two independently was safe only while speech could not move; now that a
    # line may run past its own scene (see plan_scene_speech_anchors), a
    # second opinion about where it starts is a desync between the sound and
    # the subtitle.
    speech_anchors = plan_scene_speech_anchors(
        dialogue_tracks, bounds[:-1], bounds[-1] if bounds else 0.0
    )

    # Two passes: a scene cannot be fitted to its shot until every line in it
    # is known, and the lines arrive one at a time.
    rows: List[Dict[str, Any]] = []
    by_scene: Dict[int, List[int]] = {}

    for track in dialogue_tracks or []:
        line = str(track.get("line") or "").strip()
        if not line:
            continue
        character = str(track.get("character") or "").strip()
        # Typeset to the broadcast conventions rather than dumped onto one
        # line with a name in front of it (see interfaces/subtitles): the
        # speaker is named only when a deployment asks for SDH, and a line too
        # long for two 42-character lines becomes SEVERAL cues instead of one
        # unreadable one.
        text = f"{subtitles.format_speaker(character)}{line}"
        duration = float(
            track.get("duration_seconds")
            or _probe_audio_duration_seconds(str(track.get("audio_url") or ""))
            or _estimate_line_duration_seconds(line)
        )
        row: Dict[str, Any] = {"text": text, "duration": duration}
        row["voiced"] = bool(str(track.get("audio_url") or "").strip())

        # Word-at-a-time captions, when the provider measured the words and
        # the deployment asked for them. Emitted INSTEAD of the whole-line cue
        # (not alongside it -- two overlapping cues is how libass ends up
        # stacking the same sentence twice on screen), and only where real
        # timings exist, so nothing here is ever guessed.
        words = track.get("words") if is_word_captions_enabled() else None
        if words and "scene_index" in track:
            scene_index = int(track["scene_index"])
            offset = speech_anchors.get(
                scene_index,
                bounds[scene_index] if 0 <= scene_index <= last_scene else 0.0,
            )
            for cue in chunk_words_into_cues(words):
                rows.append(
                    {
                        "text": cue["text"],
                        "duration": cue["end"] - cue["start"],
                        "voiced": row["voiced"],
                        "start": offset + cue["start"],
                        "end": offset + cue["end"],
                    }
                )
            continue

        if "start_seconds" in track:
            start = float(track["start_seconds"])
            end = float(
                track["end_seconds"] if "end_seconds" in track else start + duration
            )
            # Explicit timings are SCENE-RELATIVE when the track names a scene,
            # and absolute when it does not. A provider that measures its own
            # speech (ElevenLabs returns voice_segments per line) measures it
            # from the start of the audio it just made -- which is this scene's
            # audio, laid down at this scene's offset by the mixer. Read as
            # absolute, every measured cue in the drama would pile onto the
            # opening shot. Callers that time the whole master themselves pass
            # no scene_index and are untouched.
            if "scene_index" in track:
                bounds_index = int(track["scene_index"])
                if 0 <= bounds_index <= len(bounds) - 2:
                    # The scene's SPEECH offset, not its picture offset: they
                    # are the same number until a line runs past its own shot,
                    # and after that only this one follows the audio.
                    offset = speech_anchors.get(bounds_index, bounds[bounds_index])
                    start += offset
                    end += offset
            row["start"] = start
            row["end"] = end
        else:
            scene_index = int(track.get("scene_index", 0))
            row["scene_index"] = scene_index
            by_scene.setdefault(scene_index, []).append(len(rows))
        rows.append(row)

    for scene_index, positions in by_scene.items():
        if 0 <= scene_index <= last_scene:
            scene_start = speech_anchors.get(scene_index, bounds[scene_index])
            # A scene whose speech was pushed later than its own picture has
            # no scene-shaped window left to squeeze its cues into; the film's
            # end is then the only real boundary.
            scene_end = max(bounds[scene_index + 1], scene_start)
            if scene_end <= scene_start:
                scene_end = bounds[-1] if bounds else scene_start
            # The master fades to black over its last FADE_OUT_SECONDS (see
            # finish_master), and a caption burned underneath fades with it --
            # so a drama that has no voices, and whose closing line therefore
            # exists ONLY as text, ends on its most important sentence going
            # dark as it is being read. Measured on a delivered 30.2s drama:
            # the picture drops from 64 to 9 grey levels over the last 0.75s
            # with the final cue still up.
            #
            # Only for a scene with no recording: when the line is actually
            # spoken, the audio is the timing that matters and pulling the
            # caption off it to dodge the fade would desync the two.
            if scene_index == last_scene and not any(
                rows[at].get("voiced") for at in positions
            ):
                scene_end = max(scene_start, scene_end - FADE_OUT_SECONDS)
            span = max(0.0, scene_end - scene_start)
        else:
            scene_start, span = 0.0, 0.0
        placed = _lay_out_scene_captions(
            [rows[at]["duration"] for at in positions], span
        )
        for at, (local_start, local_end) in zip(positions, placed):
            rows[at]["start"] = scene_start + local_start
            rows[at]["end"] = scene_start + local_end

    blocks: List[str] = []
    index = 0
    for row in rows:
        start = row["start"]
        end = row["end"]
        if end <= start:
            end = start + 1.0
        # A line too long for two legal lines becomes SEVERAL cues, and its
        # time is divided between them in proportion to how much there is to
        # read -- which is what makes the split honest rather than cosmetic:
        # each cue is on screen for as long as its own words need.
        cue_texts = subtitles.split_into_cues(str(row["text"])) or [str(row["text"])]
        total_chars = sum(len(c) for c in cue_texts) or 1
        span = end - start
        cursor = start
        for position, cue_text in enumerate(cue_texts):
            share = span * (len(cue_text) / total_chars)
            cue_end = end if position == len(cue_texts) - 1 else cursor + share
            if cue_end <= cursor:
                cue_end = cursor + 0.5
            index += 1
            # SRT uses blank lines between cues; strip carriage returns so a
            # single cue stays one logical block, and lay the text out over at
            # most two lines broken where the prose breaks.
            safe_text = (
                subtitles.wrap_cue(cue_text).replace("\r\n", "\n").replace("\r", "\n")
            )
            blocks.append(
                f"{index}\n"
                f"{_format_srt_timestamp(cursor)} --> "
                f"{_format_srt_timestamp(cue_end)}\n"
                f"{safe_text}\n"
            )
            # Two frames of air between cues, so a change of caption reads as
            # a change rather than as a re-render of the same one.
            cursor = min(cue_end + CUE_GAP_SECONDS, end)

    return "\n".join(blocks)


#: libass renders an ASS script at its declared PlayRes and scales the result
#: to the frame, so a FontSize is not a pixel count -- it is multiplied by
#: ``frame_height / PlayResY``. ffmpeg's built-in SRT-to-ASS conversion
#: declares the classic 384x288, which is where this number comes from. It is
#: the whole reason a fixed FontSize cannot work across delivery formats.
_ASS_PLAY_RES_Y = 288

#: Caption line height as a fraction of the frame's SHORTER side.
#:
#: The shorter side is what actually constrains a caption, whichever way the
#: frame is turned: it caps how long a line can run before wrapping, and on a
#: phone held upright it is the dimension the reader's eye spans. Sizing from
#: HEIGHT alone -- one fixed FontSize for every format -- meant a 9:16 master
#: (1920 tall, 1080 wide) got a font scaled as though its lines had 1920px to
#: run along. One 69-character sentence came out as SIX lines covering 44.5%
#: of the entire frame; the same sentence at 16:9 was two lines and 14.1%.
#: Measured, both, in tests/test_caption_legibility.py.
#:
#: 4.5% lands within a hair of 4.5-4.9% of the short side in BOTH formats,
#: at one to two lines, which is the broadcast subtitle convention and close
#: to what social platforms burn in.
CAPTION_HEIGHT_FRACTION = 0.045

#: Side margins, as a fraction of width, so libass wraps before the frame
#: edge instead of at it. Nothing set these before, so a long line ran the
#: full width of the picture.
CAPTION_SIDE_MARGIN_FRACTION = 0.06

#: Distance from the bottom of the frame, as a fraction of HEIGHT (this one
#: really is vertical). Kept clear of the ~10% a video player's control bar
#: covers, which is what greyed out the second line of every caption in the
#: results page preview.
CAPTION_BOTTOM_MARGIN_FRACTION = 0.11


def _probe_video_size(video_path: str) -> Tuple[int, int]:
    """(width, height) of a video, or (0, 0) when it cannot be read."""
    try:
        from moviepy import VideoFileClip

        with VideoFileClip(video_path) as clip:
            width, height = clip.size or (0, 0)
            return int(width), int(height)
    except Exception as exc:
        logger.warning("Could not probe %s for caption sizing: %s", video_path, exc)
        return 0, 0


def build_caption_style(width: int, height: int) -> str:
    """The ASS ``force_style`` string for a frame of this size.

    Every length is derived from the frame rather than fixed, because the
    numbers libass wants are in PlayRes units, not pixels: the same literal
    FontSize is a different physical size in every delivery format. Falls back
    to the previous constants when the frame could not be measured, so a probe
    failure cannot leave a video with no captions at all.
    """
    if width <= 0 or height <= 0:
        font_size, margin_v, margin_side = 22, 36, 20
    else:
        scale = _ASS_PLAY_RES_Y / height  # pixels -> ASS units
        # One ASS unit is height/288 pixels, so on a 1920-tall frame the font
        # can only be chosen in ~6.7px steps. The floor is what keeps a
        # vertical master's caption from rounding down into unreadability.
        font_size = max(8, round(min(width, height) * CAPTION_HEIGHT_FRACTION * scale))
        margin_v = max(8, round(height * CAPTION_BOTTOM_MARGIN_FRACTION * scale))
        margin_side = max(4, round(width * CAPTION_SIDE_MARGIN_FRACTION * scale))
    # Outline and shadow scaled to the type, not fixed: a 1-unit outline that
    # is right at 22pt disappears at 40 and swallows the letters at 12.
    outline = max(1, round(font_size * 0.09))
    shadow = max(1, round(font_size * 0.05))
    return (
        f"FontSize={font_size},PrimaryColour=&H00FFFFFF,"
        # BorderStyle=1 — outline and drop shadow, NOT the opaque box (=3)
        # this used to draw.
        #
        # The box is legible; it is also the single most recognisable mark of
        # an automatically captioned video, because it is what YouTube's own
        # auto-captions draw. Every streaming service burns white type with a
        # black outline and a soft shadow instead, and it reads over a graded
        # night exterior perfectly well once the outline is sized to the font
        # rather than left at one unit.
        f"OutlineColour=&H00000000,BackColour=&H80000000,"
        f"BorderStyle=1,Outline={outline},Shadow={shadow},"
        f"Alignment=2,MarginV={margin_v},"
        f"MarginL={margin_side},MarginR={margin_side}"
    )


#: How far the finished master's duration may stray from the scenes it was
#: built out of before something is badly wrong. Generous: fades, transitions
#: and re-encodes all move the total by a frame or two, and a false alarm in
#: a log nobody trusts is worse than no alarm.
MASTER_DURATION_TOLERANCE = 0.25


#: How far the delivered runtime may drift from the budget before it is worth
#: saying so. Generous on purpose: the provider rounds to whole seconds, the
#: cold open adds a second or two, and transitions overlap -- none of which is
#: a fault. A film that is half again as long as it was costed is.
BUDGET_DRIFT_TOLERANCE = 0.35


#: A film may hold a beat without it being a fault. Past this share of the
#: runtime it is not a beat, it is a missing soundtrack.
MAX_SILENT_SHARE = 0.5


def check_master_is_not_mostly_silent(final_path: Optional[str]) -> Optional[str]:
    """Report a master whose audio is mostly nothing at all.

    Every audio layer here is independently optional -- music is a plan
    feature, foley is behind MUSEFORGE_FOLEY, dialogue is a Pro toggle -- and
    each one is correct to be off on its own. Nothing ever looked at the sum.
    With music off and foley off, a drama's soundtrack is a few seconds of
    speech and then DIGITAL silence: not quiet room tone, zero samples.

    Measured on a delivered drama: 12 audible seconds out of 60, the other 43
    absolute zero, and the reason the speech in it sounded pasted on rather
    than spoken in a place. Every stage had behaved exactly as configured, so
    nothing anywhere had a reason to mention it.

    Reads the FINISHED master through ffmpeg rather than the layers that went
    in: the question is what the viewer hears, and a track that was generated
    but mixed to nothing has to read the same as one that was never asked for.

    Returns a sentence for the job's warnings, or None.
    """
    if not final_path or not os.path.isfile(final_path):
        return None

    rate = 8000
    command = [
        resolve_ffmpeg_binary(), "-v", "error", "-i", final_path,
        "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-",
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=120)
    except Exception as exc:
        logger.warning("Could not measure how much of the master is silent: %s", exc)
        return None
    raw = result.stdout or b""
    if len(raw) < rate:  # under a second of audio, or no audio stream at all
        return None

    import numpy as np

    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    window = rate // 10  # 0.1s
    blocks = np.abs(
        samples[: len(samples) // window * window].reshape(-1, window)
    ).max(axis=1)
    if len(blocks) == 0:
        return None
    # -60 dBFS. Below this nothing is audible on any playback a viewer owns,
    # which is the question being asked -- true digital zero and a codec's
    # noise floor are the same silence to an ear.
    silent_share = float((blocks < 1e-3).sum()) / len(blocks)
    if silent_share <= MAX_SILENT_SHARE:
        return None

    duration = len(samples) / rate
    logger.warning(
        "Master is %.0f%% silence (%.1fs of %.1fs). Check MUSEFORGE_FOLEY and "
        "whether music was enabled for this job.",
        silent_share * 100,
        silent_share * duration,
        duration,
    )
    return (
        f"About {silent_share * 100:.0f}% of this video has no sound at all — "
        "with music and sound effects both off, only the spoken lines are "
        "audible and the rest plays in silence."
    )


def check_budget_was_honoured(
    actual_seconds: Optional[float], num_scenes: int
) -> Optional[str]:
    """Compare the delivered runtime against the budget the job was costed at.

    Nothing did this. distribute_budget decides a fixed total BEFORE any
    provider call, precisely so the cost of a job is known at charge time --
    and then the number is logged and never looked at again. check_master_
    duration is not this check: it compares the master against the sum of its
    own scene clips, so if every clip came back longer than it was asked for,
    both sides of that comparison are wrong together and it stays silent.

    Which is what a delivered drama looks like: three scenes, a 30-second
    budget, and a 60-second master that nothing in the pipeline found
    surprising. Over-delivery is not free -- it is the per-scene pricing model
    and the tension-weighted pacing plan both quietly not applying.

    Returns a sentence for the job's warnings, or None when the runtime is
    what it should be. Reports rather than repairs: trimming a finished master
    to a budget would cut a shot mid-motion, and the honest fix is upstream.
    """
    if not actual_seconds or actual_seconds <= 0 or num_scenes <= 0:
        return None
    expected = total_budget_seconds(num_scenes)
    if expected <= 0:
        return None
    drift = (actual_seconds - expected) / expected
    if abs(drift) <= BUDGET_DRIFT_TOLERANCE:
        return None
    logger.error(
        "Runtime does not match the budget: %.1fs delivered against %.1fs "
        "budgeted for %d scene(s) (%+.0f%%). The per-scene second budget is "
        "what the job was costed at, so this is the pricing model and the "
        "pacing plan both not applying.",
        actual_seconds,
        expected,
        num_scenes,
        drift * 100,
    )
    longer = actual_seconds > expected
    return (
        f"This video runs {actual_seconds:.0f} seconds against the "
        f"{expected:.0f} seconds its {num_scenes} scene(s) were planned for — "
        + (
            "longer than planned, so the pacing the scenes were written to "
            "does not apply."
            if longer
            else "shorter than planned, so part of what was paid for is missing."
        )
    )


def check_master_duration(final_path: str, scene_paths: Optional[List[str]]) -> bool:
    """Log loudly when the finished master is not the length of its scenes.

    Nothing in the assembly chain ever asked how long the result was, and a
    stage that got it wrong therefore had no way of saying so. One did: a
    silent audio track written by moviepy produced a 30-second drama whose
    container claimed 13 hours 22 minutes. It reached the user's browser as a
    player that could not seek, could not scrub and stopped after three
    seconds -- and the only reason anyone found it was a screen recording.

    Every stage here fails open by design, which is right for a picture that
    is merely imperfect and wrong for a file that is structurally broken. This
    cannot repair anything; it makes the breakage searchable, in the same logs
    the failure already scrolls past. Returns True when the master looks sane.
    """
    expected = 0.0
    for path in scene_paths or []:
        expected += _probe_video_duration(path)
    actual = _probe_video_duration(final_path)
    if expected <= 0 or actual <= 0:
        return True  # nothing to compare against; not evidence of a problem
    drift = abs(actual - expected) / expected
    if drift > MASTER_DURATION_TOLERANCE:
        logger.error(
            "Master duration is wrong: %s is %.1fs but its %d scene(s) total "
            "%.1fs (%.0f%% off). The file will not seek or scrub correctly.",
            os.path.basename(final_path),
            actual,
            len(scene_paths or []),
            expected,
            drift * 100,
        )
        return False
    return True


def _probe_video_duration(video_path: str) -> float:
    """Duration in seconds, or 0.0 when it cannot be read."""
    try:
        from moviepy import VideoFileClip

        with VideoFileClip(video_path) as clip:
            return float(clip.duration or 0.0)
    except Exception:
        return 0.0


def _escape_subtitles_filter_path(path: str) -> str:
    """Escape a filesystem path for ffmpeg's subtitles= filter."""
    # Prefer forward slashes; escape characters that break the filter grammar.
    escaped = os.path.abspath(path).replace("\\", "/")
    escaped = escaped.replace(":", "\\:").replace("'", "\\'")
    return escaped


async def _burn_kinetic_captions(
    video_path: str,
    output_path: str,
    dialogue_tracks: List[Dict[str, Any]],
    scene_paths: Optional[List[str]] = None,
) -> Optional[str]:
    """Burn word-by-word captions, or return None to leave it to the SRT path.

    None is returned for every ordinary reason not to do this -- no measured
    word timings in any track, an ffmpeg that cannot render ASS, a failed
    encode -- so the caller simply carries on and burns the plain captions it
    always has.
    """
    width, height = _probe_video_size(video_path)
    document = build_kinetic_ass(
        dialogue_tracks, scene_paths=scene_paths, width=width or 1080, height=height or 1920
    )
    if not document.strip():
        return None

    ass_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".ass",
            prefix="museforge_kinetic_",
            dir=os.path.dirname(output_path) or ".",
            delete=False,
            encoding="utf-8",
        ) as handle:
            ass_path = handle.name
            handle.write(document)

        process = await asyncio.create_subprocess_exec(
            resolve_ffmpeg_binary(),
            "-y",
            "-i",
            video_path,
            "-vf",
            f"ass={_escape_subtitles_filter_path(ass_path)}",
            *video_encode_args(),
            # The mix is already made and must survive being written over.
            "-c:a",
            "copy",
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode == 0 and os.path.isfile(output_path):
            return output_path
        logger.warning(
            "Kinetic caption burn failed (exit=%s), falling back to plain "
            "captions: %s",
            process.returncode,
            stderr.decode("utf-8", errors="replace")[-800:],
        )
    except Exception as exc:
        logger.warning(
            "Kinetic captions unavailable, falling back to plain captions: %s", exc
        )
    finally:
        if ass_path:
            try:
                os.unlink(ass_path)
            except OSError:
                pass
    try:
        os.unlink(output_path)
    except OSError:
        pass
    return None


async def burn_subtitles(
    video_path: str,
    output_path: str,
    dialogue_tracks: list,
    scene_paths: Optional[List[str]] = None,
) -> str:
    """Burn dialogue captions into ``video_path`` via ffmpeg's subtitles filter.

    Builds a temporary .srt from ``dialogue_tracks`` (white text + black outline
    / box for readability). Fails open: on any error the original video is
    copied through unchanged — same pattern as watermark / color grade.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    def _copy_through() -> str:
        if os.path.abspath(video_path) != os.path.abspath(output_path):
            with open(video_path, "rb") as src:
                data = src.read()
            with open(output_path, "wb") as dst:
                dst.write(data)
        return output_path

    if not dialogue_tracks:
        return _copy_through()

    # Kinetic captions first, when the deployment asked for them AND the voice
    # provider measured its words. Not a fallback chain out of caution: these
    # are two different house styles, and the plain one is right for a 16:9
    # drama in the same way the kinetic one is right for a vertical feed.
    #
    # Which is why the flag alone cannot be the whole decision. It is set per
    # DEPLOYMENT and the shape of the picture is set per JOB, so a deployment
    # serving both got word-by-word captions -- three words at a time, in
    # accent yellow, sized and placed for a phone held at arm's length -- burnt
    # onto a 1920x1080 cinematic master. Delivered, and the single most
    # recognisably un-cinematic thing in the frame. The style follows the
    # picture it is being written onto.
    if is_word_captions_enabled():
        width, height = _probe_video_size(video_path)
        if width and height and width > height:
            logger.info(
                "Word captions are enabled, but this master is %dx%d — "
                "landscape gets the broadcast caption style, not the feed one.",
                width,
                height,
            )
        else:
            kinetic = await _burn_kinetic_captions(
                video_path, output_path, dialogue_tracks, scene_paths
            )
            if kinetic:
                return kinetic

    srt_path = None
    try:
        srt_body = build_srt_from_dialogue_tracks(
            list(dialogue_tracks), scene_paths=scene_paths
        )
        if not srt_body.strip():
            return _copy_through()

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".srt",
            prefix="museforge_subs_",
            dir=os.path.dirname(output_path) or ".",
            delete=False,
            encoding="utf-8",
        ) as srt_file:
            srt_path = srt_file.name
            srt_file.write(srt_body)

        ffmpeg_binary = resolve_ffmpeg_binary()

        # White primary text, black outline, BorderStyle=3 = opaque box behind
        # text for readability on busy backgrounds. Every size is measured off
        # this video's own frame -- see build_caption_style.
        force_style = build_caption_style(*_probe_video_size(video_path))
        vf = (
            f"subtitles={_escape_subtitles_filter_path(srt_path)}"
            f":force_style='{force_style}'"
        )

        process = await asyncio.create_subprocess_exec(
            ffmpeg_binary,
            "-y",
            "-i",
            video_path,
            "-vf",
            vf,
            *video_encode_args(),
            "-c:a",
            "copy",
            output_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode == 0 and os.path.isfile(output_path):
            return output_path
        logger.warning(
            "Subtitle burn ffmpeg filter failed (exit=%s), shipping without captions: %s",
            process.returncode,
            stderr.decode("utf-8", errors="replace")[-1000:],
        )
    except Exception as exc:
        logger.warning("Subtitle burn unavailable, shipping without captions: %s", exc)
        try:
            os.unlink(output_path)
        except OSError:
            pass
        return _copy_through()
    finally:
        if srt_path:
            try:
                os.unlink(srt_path)
            except OSError:
                pass

    try:
        os.unlink(output_path)
    except OSError:
        pass
    return _copy_through()


async def add_watermark(video_path: str, output_path: str) -> str:
    """Burn a small, semi-transparent "MuseForge" text watermark into the
    bottom-right corner. Free plan only (see WATERMARK_PLANS).

    Fails open: if moviepy/ffmpeg text rendering isn't available (e.g. no
    ImageMagick on the host), the original video is copied through
    unwatermarked rather than failing the job.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    font_path = _find_watermark_font()
    if not font_path:
        logger.warning("No usable font found for watermark, shipping unwatermarked video")
        if os.path.abspath(video_path) != os.path.abspath(output_path):
            with open(video_path, "rb") as src:
                data = src.read()
            with open(output_path, "wb") as dst:
                dst.write(data)
        return output_path
    try:
        from moviepy import CompositeVideoClip, TextClip, VideoFileClip

        video = VideoFileClip(video_path)
        margin = max(10, int(video.h * 0.02))
        watermark = (
            TextClip(
                font=font_path,
                text=WATERMARK_TEXT,
                font_size=max(14, int(video.h * 0.035)),
                color="white",
                stroke_color="black",
                stroke_width=1,
            )
            .with_opacity(0.55)
            .with_duration(video.duration)
        )
        watermark = watermark.with_position(
            (video.w - watermark.w - margin, video.h - watermark.h - margin)
        )
        final = CompositeVideoClip([video, watermark])
        final.write_videofile(
            output_path, codec="libx264", audio_codec="aac", logger=None,
            **moviepy_encode_kwargs(),
        )
        video.close()
        watermark.close()
        final.close()
    except Exception as exc:
        logger.warning("Watermark rendering failed, shipping unwatermarked video: %s", exc)
        if os.path.abspath(video_path) != os.path.abspath(output_path):
            with open(video_path, "rb") as src:
                data = src.read()
            with open(output_path, "wb") as dst:
                dst.write(data)
    return output_path


def _parse_aspect_ratio(ratio: str) -> tuple:
    """Parse '9:16' / '1:1' into (w, h) floats. Raises ValueError if invalid."""
    parts = (ratio or "").strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Invalid aspect ratio: {ratio!r}")
    w, h = float(parts[0]), float(parts[1])
    if w <= 0 or h <= 0:
        raise ValueError(f"Invalid aspect ratio: {ratio!r}")
    return w, h


async def export_alternate_format(
    source_path: str,
    output_path: str,
    target_ratio: str,
) -> str:
    """Center-crop ``source_path`` to ``target_ratio`` and write ``output_path``.

    IMPORTANT LIMITATION: this is a *naive center crop*, not smart subject-
    aware reframing. Content near the edges of the original frame may be
    lost. Suitable for quick 9:16 / 1:1 exports from a finished 16:9 master
    without another MuAPI render.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    target_w, target_h = _parse_aspect_ratio(target_ratio)
    target = target_w / target_h

    # moviepy is sync/CPU-bound — run in a worker thread so the event loop
    # stays responsive during the export.
    def _crop() -> str:
        from moviepy import VideoFileClip

        clip = VideoFileClip(source_path)
        try:
            src_w, src_h = clip.w, clip.h
            src_ratio = src_w / src_h
            if abs(src_ratio - target) < 1e-3:
                # Already the right ratio — just remux/copy encode.
                cropped = clip
            elif src_ratio > target:
                # Source is wider than target → crop left/right (center).
                new_w = _even(src_h * target)
                x1 = (src_w - new_w) / 2
                cropped = clip.cropped(x1=x1, y1=0, width=new_w, height=_even(src_h))
            else:
                # Source is taller than target → crop top/bottom (center).
                new_h = _even(src_w / target)
                y1 = (src_h - new_h) / 2
                cropped = clip.cropped(x1=0, y1=y1, width=_even(src_w), height=new_h)

            cropped.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                logger=None,
                **moviepy_encode_kwargs(),
            )
            if cropped is not clip:
                cropped.close()
        finally:
            clip.close()
        return output_path

    import asyncio

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _crop)


#: A clip trimmed below this is not a shot any more, it is a glitch. Guards
#: against a UI that lets someone drag both handles past each other.
MIN_TRIMMED_SECONDS = 0.5

#: How much shorter a lip-synced clip may be than the take it replaces before
#: it is rejected. Re-encoding moves the last frame around by a hair; a real
#: trim-to-audio removes seconds.
LIPSYNC_LENGTH_TOLERANCE_SECONDS = 0.35

#: How far a scene's speech may start AFTER its picture and still be worth
#: driving a mouth with.
#:
#: The sync provider drives the mouth from the first frame of the clip it is
#: given, which assumes the line begins where the scene begins. Usually it
#: does. It stops doing so the moment a previous scene's line overruns its
#: shot: plan_scene_speech_anchors then holds this scene's speech back so the
#: two do not talk over each other (an audio bridge, which is ordinary film
#: grammar), and the mixer lays the voice down at that later anchor -- while
#: the mouth in the picture has already said the line.
#:
#: A mouth moving where there are no words is the dubbing error the whole
#: feature exists to remove, so a scene whose speech has drifted keeps its
#: unsynced take. Well above a frame at 24fps and well under the smallest
#: drift a bridge can produce, so rounding never trips it and a real bridge
#: always does.
LIPSYNC_MAX_ANCHOR_DRIFT_SECONDS = 0.25


def _clip_duration(path: str) -> Optional[float]:
    """Seconds of video at ``path``, or None if it cannot be measured."""
    if not path or not os.path.isfile(path):
        return None
    try:
        from moviepy import VideoFileClip

        with VideoFileClip(path) as clip:
            return float(clip.duration)
    except Exception as exc:
        logger.warning("Could not measure %s: %s", path, exc)
        return None


def _keeps_its_length(original_path: str, candidate_path: str) -> bool:
    """Whether ``candidate_path`` is (near enough) as long as the original.

    Fails OPEN: when either clip cannot be measured the candidate is accepted,
    because refusing every sync on a probe failure would quietly disable a
    feature the customer paid for. The check exists to catch a provider that
    trims to the audio, which is unmistakable, not to police rounding.
    """
    original = _clip_duration(original_path)
    candidate = _clip_duration(candidate_path)
    if original is None or candidate is None:
        return True
    return candidate >= original - LIPSYNC_LENGTH_TOLERANCE_SECONDS


async def trim_clip(
    source_path: str,
    output_path: str,
    trim_start: float = 0.0,
    trim_end: float = 0.0,
) -> str:
    """Cut ``trim_start``/``trim_end`` seconds off the head/tail of one clip.

    This is the timeline editor's only picture operation, and it deliberately
    costs nothing but CPU: trimming a clip that already exists is the cheap way
    to fix "the shot holds two seconds too long", which otherwise forced a paid
    retake that re-rolled the whole take just to lose its tail.

    Fails open by returning the untrimmed source: a trim that cannot be applied
    should cost the user a second of runtime, never their video.
    """
    trim_start = max(0.0, float(trim_start or 0.0))
    trim_end = max(0.0, float(trim_end or 0.0))
    if trim_start <= 0 and trim_end <= 0:
        return source_path

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    def _trim() -> str:
        from moviepy import VideoFileClip

        clip = VideoFileClip(source_path)
        try:
            start = min(trim_start, max(0.0, clip.duration - MIN_TRIMMED_SECONDS))
            end = max(start + MIN_TRIMMED_SECONDS, clip.duration - trim_end)
            end = min(end, clip.duration)
            if end - start >= clip.duration - 1e-3:
                return source_path
            trimmed = clip.subclipped(start, end)
            trimmed.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                logger=None,
                **moviepy_encode_kwargs(),
            )
            trimmed.close()
        finally:
            clip.close()
        return output_path

    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, _trim)
    except Exception as exc:
        logger.warning("Trim failed for %s, keeping the full clip: %s", source_path, exc)
        return source_path


class Idea2VideoPipeline:
    def __init__(self, api_key: str, demo: bool = False):
        self.api_key = api_key
        self.demo = demo
        self.screenwriter = ScreenwriterAgent(demo=demo)
        self.image_gen = _make_image_generator(api_key, demo=demo)
        self.script2video = Script2VideoPipeline(api_key, demo=demo)

    async def _lock_character_portraits(
        self,
        characters: List[CharacterInScene],
        style: str = "Cinematic",
        character_portraits_override: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Generate one portrait per character for the entire drama (consistency lock).

        character_portraits_override: user-uploaded reference photo(s), keyed
        by character name. These are used as-is instead of generating a
        fresh AI portrait for that character — this is what lets a user
        upload their own face/character photo and have it appear consistently
        across every scene.
        """
        portraits: Dict[str, str] = dict(character_portraits_override or {})

        pending = []
        for char in characters:
            if not char.is_visible:
                continue
            if char.name in portraits:
                # Already supplied by the user — skip AI generation for this one.
                char.portrait_url = portraits[char.name]
                continue
            pending.append(char)
        if not pending:
            return portraits

        # Portraits are independent of one another, and NOTHING starts until
        # the last one lands: this runs before the location plate, which runs
        # before the first scene. Generated serially, a four-hander spent four
        # full image round trips of dead time before any scene work began.
        # Bounded so a large cast does not arrive at the provider as one burst.
        semaphore = asyncio.Semaphore(
            max(1, int(os.environ.get("MUSEFORGE_PORTRAIT_CONCURRENCY", "3")))
        )

        look = resolve_visual_style(style)

        async def _portrait(char) -> tuple:
            wardrobe = (getattr(char, "wardrobe", "") or "").strip()
            prompt = (
                f"Character portrait, {style} style. "
                f"{char.static_features}. {char.dynamic_features}. "
                # The locked portrait is the costume reference too -- generating
                # it without wardrobe leaves every scene to invent an outfit.
                f"{('Wearing ' + wardrobe + '. ') if wardrobe else ''}"
                f"Front-facing, neutral expression, studio lighting, high detail."
                # The portrait is the identity anchor every frame is matched
                # against, so it has to be made the same way the frames are.
                # A photographic face bound into cel-shaded scenes fights the
                # style in every shot of the drama. Added only for stylised
                # looks: a photoreal style already renders this correctly and
                # a redundant note could only move a picture that was right.
                f"{'' if look.is_photoreal else ' ' + look.render_note}"
            )
            async with semaphore:
                return char, await self.image_gen.generate_image(
                    prompt, aspect_ratio="1:1"
                )

        for char, url in await asyncio.gather(*[_portrait(c) for c in pending]):
            portraits[char.name] = url
            char.portrait_url = url
        return portraits

    async def _lock_location_plate(
        self,
        script: DramaScript,
        style: str = "Cinematic",
        aspect_ratio: str = "16:9",
        location_image_override: Optional[str] = None,
    ) -> Optional[str]:
        """Generate ONE empty-set plate of the drama's locked setting.

        The character portrait lock solves identity drift; nothing solved
        PLACE drift. The screenwriter already fixes a single location for the
        whole drama, but that agreement only ever existed as words in each
        frame prompt -- so "stone-walled Istanbul coffeehouse" was re-imagined
        from scratch for every shot, and the room changed between cuts.

        This renders that room ONCE and reuses the image as the visual
        reference for shots that have no character to anchor to (see
        script2video: establishing shots, inserts, object shots). Deliberately
        shot empty -- no people -- because it is a place reference, not a
        character one; a figure in the plate would leak into every shot that
        uses it.

        Returns None when the script names no location, which leaves the
        previous behaviour completely untouched.
        """
        if location_image_override:
            return location_image_override

        location = (getattr(script, "setting_location", "") or "").strip()
        if not location:
            return None

        time_of_day = (getattr(script, "setting_time_of_day", "") or "").strip()
        era = (getattr(script, "setting_era", "") or "").strip()
        look = resolve_visual_style(style)
        prompt = (
            f"Empty location plate, {style} style. {location}. "
            f"{('Time of day: ' + time_of_day + '. ') if time_of_day else ''}"
            f"{('Era: ' + era + '. ') if era else ''}"
            "Wide establishing view of the space itself, no people, no figures, "
            "no characters. Consistent architecture, materials, furniture and "
            "lighting. High detail."
            # Same reason as the character portrait: the plate is the set
            # reference every establishing shot is drawn from, so it has to
            # be built in the drama's own look.
            f"{'' if look.is_photoreal else ' ' + look.render_note}"
        )
        try:
            return await self.image_gen.generate_image(prompt, aspect_ratio=aspect_ratio)
        except Exception as exc:
            # Fail-open, exactly like music/dialogue: a missing plate costs
            # continuity, but it must never cost the whole job.
            logger.warning(
                "Location plate generation failed, continuing without a "
                "locked setting reference: %s",
                exc,
            )
            return None

    async def _lipsync_scenes(
        self,
        scene_paths: List[str],
        dialogue_tracks: List[Dict[str, Any]],
        working_dir: str,
        progress: Callable,
        is_cancelled: Optional[Callable[[], bool]] = None,
        only_scenes: Optional[set] = None,
        requested: bool = True,
        reaction_tails: Optional[Dict[int, float]] = None,
    ) -> List[int]:
        """Replace each speaking scene's clip with a lip-synced one, in place.

        Mutates ``scene_paths`` (the list concatenation reads from) and
        ``dialogue_tracks`` (the list the audio mixer reads from), and returns
        the scene indices that were successfully synced.

        ``reaction_tails`` maps a scene to the seconds at the END of its clip
        that belong to a cutaway. Those seconds are held back from the sync and
        concatenated again afterwards: the sync model cannot see the cut in the
        middle of a two-angle scene, and there is no mouth in a reaction shot
        to drive anyway. Without it the product's answer was to refuse the
        second angle whenever lip sync was on -- so turning lip sync on flattened
        every peak scene to a single framing, which is the pair of features
        users ask for together.

        Fail-open per scene, not per drama: if scene 2 cannot be synced, scenes
        1 and 3 still are, and scene 2 simply keeps its original clip with its
        voice mixed over the top exactly as before.
        """
        # `requested` is the per-job opt-in (the user paid for it);
        # is_lipsync_enabled() is the deployment flag. Both must hold.
        #
        # Four different reasons used to share one silent `return []`. An
        # operator who had switched the deployment flag on and still got closed
        # mouths had nothing anywhere -- no log line, no warning on the job --
        # to tell them which of the four it was, and the video looks identical
        # in every case. Say which.
        if self.demo:
            return []
        if not requested:
            logger.info(
                "Lip sync was not requested on this job (the per-job opt-in is "
                "off, or /api/generate dropped it because dialogue or the Pro "
                "plan was missing) — mouths will not be driven."
            )
            return []
        if not is_lipsync_enabled():
            logger.info(
                "Lip sync was requested but MUSEFORGE_LIPSYNC_ENABLED is not "
                "set on this deployment — mouths will not be driven."
            )
            return []
        if not dialogue_tracks:
            logger.info(
                "Lip sync was requested but this drama has no dialogue tracks, "
                "so there is no speech to drive a mouth from."
            )
            return []

        lipsync = make_lipsync(demo=self.demo)
        if not lipsync.available():
            logger.info(
                "Lip sync enabled but %s has no API key — skipping.",
                type(lipsync).__name__,
            )
            return []

        # One request per SCENE, keyed off the track that actually carries the
        # audio (the voice generator returns one combined file per scene and
        # attaches it to that scene's first line only).
        audio_by_scene: Dict[int, str] = {}
        for track in dialogue_tracks:
            # synced_audio_url is the same file, kept under a name the mixer
            # ignores, so re-syncing a REGENERATED scene later still has the
            # voice to sync against instead of finding it deleted.
            audio_url = track.get("audio_url") or track.get("synced_audio_url")
            if not audio_url:
                continue
            scene_index = int(track.get("scene_index", -1))
            if only_scenes is not None and scene_index not in only_scenes:
                continue
            if 0 <= scene_index < len(scene_paths):
                audio_by_scene.setdefault(scene_index, audio_url)

        # Where each scene's speech actually lands on the finished timeline.
        # Read from the same plan the mixer and the captions read, so all three
        # agree -- and computed from EVERY dialogue track, not just the scenes
        # being synced, because a bridge is caused by the scene before.
        scene_lengths = [_probe_video_duration(path) for path in scene_paths]
        picture_starts: List[float] = []
        elapsed = 0.0
        for length in scene_lengths:
            picture_starts.append(elapsed)
            elapsed += length
        speech_anchors = plan_scene_speech_anchors(
            dialogue_tracks, picture_starts, elapsed
        )

        synced: List[int] = []
        for position, (scene_index, audio_url) in enumerate(sorted(audio_by_scene.items())):
            if is_cancelled and is_cancelled():
                break

            picture_start = (
                picture_starts[scene_index]
                if 0 <= scene_index < len(picture_starts)
                else 0.0
            )
            # Only where the timeline is actually known. A clip that will not
            # probe contributes a length of 0, which drags every scene after
            # it back to the same start and would read as a drift that is not
            # there -- so an unmeasurable timeline fails OPEN and syncs, the
            # same way the length check does.
            timeline_known = all(
                length > 0 for length in scene_lengths[: scene_index + 1]
            )
            drift = speech_anchors.get(scene_index, picture_start) - picture_start
            if timeline_known and drift > LIPSYNC_MAX_ANCHOR_DRIFT_SECONDS:
                # The line does not start where this clip starts, and the sync
                # provider has no way to be told that -- it drives the mouth
                # from frame one. Syncing here would put the words in the
                # mouth before they are in the air, which is the exact dubbing
                # error the feature is bought to remove.
                logger.warning(
                    "Scene %s speaks %.2fs after its picture starts (the "
                    "previous scene's line is still running), so its mouth "
                    "would move before the words — keeping the unsynced take.",
                    scene_index,
                    drift,
                )
                continue
            await progress(
                "lipsync",
                f"Syncing lips to dialogue ({position + 1}/{len(audio_by_scene)})",
                88,
            )
            # A scene that bought a second angle is master-then-reaction in one
            # file. Sync the master, keep the cutaway out of it, put them back
            # together -- see _reaction_tail_seconds.
            source_path = scene_paths[scene_index]
            tail_seconds = float((reaction_tails or {}).get(scene_index, 0.0) or 0.0)
            sync_source = source_path
            tail_path: Optional[str] = None
            if tail_seconds > 0:
                sync_source, tail_path = await _split_off_tail(
                    source_path,
                    os.path.join(working_dir, f"scene_{scene_index}_master.mp4"),
                    os.path.join(working_dir, f"scene_{scene_index}_reaction.mp4"),
                    tail_seconds,
                )
                if tail_path is None:
                    # The split did not work, so the only safe request is the
                    # old one: sync the whole clip, cut and all.
                    sync_source = source_path

            synced_url = await lipsync.sync(
                sync_source, audio_url, is_cancelled=is_cancelled
            )
            if not synced_url:
                continue
            local_path = os.path.join(working_dir, f"scene_{scene_index}_lipsync.mp4")
            try:
                await download_video(synced_url, local_path)
            except Exception as exc:
                logger.warning(
                    "Lip-synced clip for scene %s could not be downloaded, "
                    "keeping the original: %s",
                    scene_index,
                    exc,
                )
                continue
            if not _keeps_its_length(sync_source, local_path):
                # Sync Labs' own default (cut_off) trims the video down to the
                # length of the audio, which would let a short line silently
                # shorten a scene and break the fixed per-credit second budget
                # the whole costing model rests on. The fal backend pins
                # sync_mode to stop that; MuAPI's endpoint exposes no such knob.
                #
                # Discarding the clip protected the runtime and cost the
                # feature: a line is shorter than its scene in nearly every
                # scene ever written, so on the default backend this rejected
                # the sync essentially every time. Measured on a delivered job
                # -- three scenes, three syncs bought and paid for (633s of
                # render), three rejections, not one mouth driven.
                #
                # The seconds that came back missing are the END of the take,
                # and the take still has them. Put them back.
                restored = await _restore_trimmed_length(
                    sync_source,
                    local_path,
                    os.path.join(working_dir, f"scene_{scene_index}_after_line.mp4"),
                    os.path.join(working_dir, f"scene_{scene_index}_lipsync_full.mp4"),
                )
                if restored is None:
                    logger.warning(
                        "Lip-synced clip for scene %s came back shorter than "
                        "the take it replaces and could not be restored to "
                        "length — keeping the original so the runtime the "
                        "customer paid for is preserved.",
                        scene_index,
                    )
                    continue
                local_path = restored

            if tail_path is not None:
                rejoined = os.path.join(
                    working_dir, f"scene_{scene_index}_lipsync_cut.mp4"
                )
                try:
                    await concatenate_videos([local_path, tail_path], rejoined)
                except Exception as exc:
                    # The master synced but the cutaway could not be put back.
                    # Shipping the master alone would silently shorten the
                    # scene, which is the one thing the length guard above
                    # exists to prevent -- so the whole scene keeps its
                    # unsynced take instead.
                    logger.warning(
                        "Scene %s could not be re-joined to its reaction shot "
                        "after lip sync, keeping the unsynced take: %s",
                        scene_index,
                        exc,
                    )
                    continue
                local_path = rejoined

            scene_paths[scene_index] = local_path
            synced.append(scene_index)

        # The speech stays in the MIX. Handing it over to the picture is the
        # obvious move -- the synced clip carries the line in its own audio
        # track -- and nothing downstream can deliver it: every tier of
        # concatenate_videos drops audio on purpose (`-an`, `audio=False`,
        # `a=0`, so a generated clip's incidental audio cannot reach the
        # master), and mix_audio_layers maps `0:v` alone. Verified by joining
        # two clips that both had sound and probing the result: video only.
        #
        # So dropping the row from the mix did not stop the line playing
        # twice. It stopped it playing at all -- a scene with a moving mouth,
        # a subtitle, and silence where the dialogue should be. The mouth is
        # driven from the same file the mixer lays down at the same anchor, so
        # picture and voice are reading one clock, which is what makes the
        # sync worth buying in the first place.
        #
        # synced_audio_url is still written: it is what a regenerated scene's
        # re-sync reads, and jobs stored by the older behaviour have their
        # voice under that name and nowhere else.
        for track in dialogue_tracks:
            if int(track.get("scene_index", -1)) in synced:
                audio_url = track.get("audio_url")
                if audio_url:
                    track["synced_audio_url"] = audio_url
                track["lipsynced"] = True

        return synced

    async def _archive_scene_clips(
        self,
        scene_results: List[Dict[str, Any]],
        scene_paths: List[str],
        working_dir: str,
    ) -> None:
        """Persist every scene clip so a single scene can be replaced later.

        Writes ``clip_url`` (and ``clip_path``) onto each scene in
        ``scene_results``. Fail-open: an upload that does not work leaves the
        local path behind, which still works until the working dir is cleaned,
        and simply means that scene cannot be regenerated after cleanup.
        """
        if self.demo:
            return

        from tools.supabase_storage import upload_video

        job_id = os.path.basename(os.path.normpath(working_dir))
        for scene in scene_results:
            clip_index = scene.get("clip_index")
            if clip_index is None or not (0 <= clip_index < len(scene_paths)):
                continue
            local_path = scene_paths[clip_index]
            if not local_path or not os.path.isfile(local_path):
                continue
            scene["clip_path"] = local_path
            take = int(scene.get("take", 1) or 1)
            try:
                # Keyed by TAKE. The key used to be the scene alone, so every
                # retake overwrote the archive of the take it replaced: the
                # local file survived in its own take directory, but the only
                # copy that outlives the working dir did not. A user who
                # re-shot a scene and preferred the first version had nothing
                # to go back to, and the clip they paid for was gone.
                stored = await upload_video(
                    local_path, f"{job_id}_scene_{scene['index']}_take{take}"
                )
            except Exception as exc:
                logger.warning(
                    "Scene %s clip could not be archived (regeneration will be "
                    "unavailable for it once the working dir is cleaned): %s",
                    scene["index"],
                    exc,
                )
                continue
            if stored and stored.startswith("http"):
                scene["clip_url"] = stored
            _record_take(scene, take, scene.get("clip_url"), local_path)

    def _characters_from_script(self, script: DramaScript) -> List[CharacterInScene]:
        return [
            CharacterInScene(
                idx=i,
                name=c.name,
                static_features=c.description,
                dynamic_features="",
                wardrobe=str(getattr(c, "wardrobe", "") or ""),
                is_visible=True,
            )
            for i, c in enumerate(script.characters)
        ]

    async def _rerender_scenes(
        self,
        previous_result: Dict[str, Any],
        scene_indices: List[int],
        working_dir: str,
        director_note: str = "",
        progress_callback: Optional[Callable] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        portraits_override: Optional[Dict[str, str]] = None,
        location_plate_override: Optional[str] = None,
        script_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Re-render the named scenes and splice them into the finished drama.

        Everything not named is reused verbatim: the same script, the same
        locked portraits, the same set plate, the same second budget, the same
        voice tracks. That is the whole point — re-running the job would also
        re-roll the scenes the user was happy with, and charge for them.

        ``director_note`` is the user's reason for rejecting the take ("too
        dark", "show his hands"). It is appended to the shot brief for the
        re-rendered scenes only, so the retry is directed rather than merely a
        different dice roll.

        The ``*_override`` arguments are what makes a *global* edit different
        from a retake: a changed portrait, set plate or script is threaded
        through every re-rendered scene, so "put her in the red coat" moves the
        lock itself instead of hoping each scene's prompt drifts the same way.
        """
        os.makedirs(working_dir, exist_ok=True)

        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        async def progress(stage: str, message: str, pct: float, data=None):
            if progress_callback:
                await progress_callback(stage, message, pct, data)

        state = (previous_result or {}).get("_render_state") or {}
        script_data = script_override or state.get("script") or {}
        if not script_data:
            raise SceneRegenerationUnavailable(
                "This video was made before single-scene retakes existed, so "
                "the information needed to re-render one scene was not kept. "
                "Generating it again will make retakes available."
            )

        script = DramaScript(**script_data)
        scenes = list(previous_result.get("scenes") or [])
        wanted = sorted({int(i) for i in scene_indices})
        if not wanted:
            raise SceneRegenerationUnavailable("No scenes were selected to re-render.")

        targets: List[Dict[str, Any]] = []
        for index in wanted:
            match = next((s for s in scenes if int(s.get("index", -1)) == index), None)
            if match is None:
                raise SceneRegenerationUnavailable(
                    f"Scene {index + 1} is not part of this video."
                )
            targets.append(match)

        # Every scene that is NOT being re-rendered has to be recoverable, or
        # there is nothing to splice the new takes into. Checked up front so
        # the user is told before a paid generation runs, not after.
        others = [
            s for s in scenes if s not in targets and s.get("clip_index") is not None
        ]
        missing = [
            s["index"] + 1
            for s in others
            if not (s.get("clip_url") or (s.get("clip_path") and os.path.isfile(s["clip_path"])))
        ]
        if missing:
            raise SceneRegenerationUnavailable(
                "The other scenes of this video are no longer stored, so a "
                f"single scene cannot be replaced (missing: scene {missing[0]}). "
                "Please generate the video again."
            )

        characters = self._characters_from_script(script)
        portraits = {**(previous_result.get("portraits") or {}), **(portraits_override or {})}
        for char in characters:
            if portraits.get(char.name):
                char.portrait_url = portraits[char.name]

        location_plate = (
            location_plate_override
            if location_plate_override is not None
            else previous_result.get("location_plate")
        )

        for index in wanted:
            if index >= len(script.scenes):
                raise SceneRegenerationUnavailable(
                    f"Scene {index + 1} is not part of this script."
                )

        durations = state.get("scene_durations") or []
        user_requirement = state.get("user_requirement") or ""
        # A retake that ignores the note is just another roll of the dice.
        note = (director_note or "").strip()
        if note:
            user_requirement = (
                f"{user_requirement}\n\nDIRECTOR'S NOTE FOR THIS RETAKE (binding): {note}"
            ).strip()

        _check_cancel()
        label = (
            f"scene {wanted[0] + 1}"
            if len(wanted) == 1
            else f"{len(wanted)} scenes"
        )
        await progress("storyboard", f"Re-shooting {label}", 15)

        # Each target gets a fresh take sub-directory: overwriting the previous
        # take's files in place would corrupt the old clip while the master
        # still points at it, leaving the user with neither version if this
        # take then fails.
        # Recomputed rather than stored: it is a pure function of the script,
        # and the script is what a retake re-reads anyway.
        retake_scales = plan_shot_scales(script.scenes)
        new_paths: Dict[int, str] = {}
        new_shots: Dict[int, Any] = {}
        takes: Dict[int, int] = {}
        semaphore = asyncio.Semaphore(_scene_concurrency(len(targets)))

        async def _render_target(target: Dict[str, Any]) -> None:
            index = int(target["index"])
            scene_script = script.scenes[index]
            take = int(target.get("take", 1)) + 1
            takes[index] = take
            scene_dir = os.path.join(working_dir, f"scene_{index}_take{take}")
            story_so_far, not_yet = _format_story_state(script.scenes, index)
            async with semaphore:
                _check_cancel()
                scene_result = await self.script2video.run(
                    script=_scene_action(scene_script),
                    characters=characters,
                    user_requirement=user_requirement,
                    style=previous_result.get("style", "Cinematic"),
                    working_dir=scene_dir,
                    progress_callback=progress_callback,
                    scene_idx=index,
                    total_scenes=max(1, len(script.scenes)),
                    character_portraits=portraits,
                    director_style=previous_result.get("director_style", "cinematic_balanced"),
                    aspect_ratio=previous_result.get("aspect_ratio", "16:9"),
                    is_cancelled=is_cancelled,
                    plan=previous_result.get("plan", "free"),
                    setting_location=getattr(script, "setting_location", "") or "",
                    setting_time_of_day=getattr(script, "setting_time_of_day", "") or "",
                    setting_era=getattr(script, "setting_era", "") or "",
                    location_plate_url=location_plate,
                    has_dialogue=bool(_scene_dialogue(scene_script)),
                    lipsync_enabled=bool(previous_result.get("lipsynced_scenes")),
                    scene_emotion=_scene_emotion(scene_script),
                    scene_dialogue=_format_scene_dialogue(_scene_dialogue(scene_script)),
                    scene_direction=_format_scene_direction(scene_script),
                    # A retake replaces one scene inside a cut that already
                    # exists, so it needs the same story-state fence the first
                    # pass had — otherwise the new take comes back showing a
                    # later scene's payoff.
                    story_so_far=story_so_far,
                    not_yet=not_yet,
                    scene_tension=_scene_tension(scene_script),
                    # Same slice of the second budget as the take it replaces,
                    # so a retake can never quietly lengthen (or shorten) the
                    # paid runtime.
                    scene_duration=durations[index] if index < len(durations) else 0.0,
                    character_direction=_format_character_direction(script),
                    theme=getattr(script, "theme", "") or "",
                    visual_motif=getattr(script, "visual_motif", "") or "",
                    user_brief=getattr(script, "user_brief", "") or "",
                    # The SAME framing plan the first pass used, so a retake
                    # cannot quietly hand this scene the setup its neighbour
                    # already has.
                    scene_shot_scale=(
                        retake_scales[index] if index < len(retake_scales) else ""
                    ),
                )
            if not scene_result.get("path"):
                raise SceneRegenerationUnavailable(
                    "The retake did not produce a usable clip. Your credit has "
                    "been refunded — please try again."
                )
            new_paths[index] = scene_result["path"]
            new_shots[index] = scene_result.get("shots", [])

        await asyncio.gather(*(_render_target(t) for t in targets))

        # Rebuild the full clip list in scene order, pulling the untouched
        # scenes back down from storage.
        _check_cancel()
        await progress("assembly", "Splicing the new takes back in", 80)
        ordered = sorted(
            [s for s in scenes if s.get("clip_index") is not None],
            key=lambda s: s["clip_index"],
        )
        scene_paths: List[str] = []
        for scene in ordered:
            index = int(scene["index"])
            if index in new_paths:
                scene_paths.append(new_paths[index])
                continue
            local = scene.get("clip_path")
            if local and os.path.isfile(local):
                scene_paths.append(local)
                continue
            local = os.path.join(working_dir, f"scene_{scene['index']}_restored.mp4")
            await download_video(scene["clip_url"], local)
            scene_paths.append(local)

        dialogue_tracks = [dict(t) for t in (state.get("dialogue_tracks") or [])]
        target_clip_indices = {int(t["clip_index"]) for t in targets if t.get("clip_index") is not None}
        resync = {
            int(t.get("scene_index", -1))
            for t in dialogue_tracks
            if int(t.get("scene_index", -1)) in target_clip_indices and t.get("lipsynced")
        }
        if resync:
            # The replacement clips have never been synced. Re-sync THOSE
            # scenes only — the others already carry their synced audio
            # in-picture and re-syncing them would be a second charge for no
            # change.
            for track in dialogue_tracks:
                if int(track.get("scene_index", -1)) in resync:
                    track.pop("lipsynced", None)
                    # Put the voice back where the MIXER looks for it, not
                    # just where the sync step does. The first pass moved it
                    # to synced_audio_url because the speech was baked into
                    # the picture -- but the picture it was baked into has
                    # just been thrown away. If the re-sync then fails (it is
                    # fail-open, one clip at a time), the track carries no
                    # audio_url, the mixer lays down nothing, and the retaken
                    # scene plays silent in a video whose other scenes speak.
                    if not track.get("audio_url") and track.get("synced_audio_url"):
                        track["audio_url"] = track["synced_audio_url"]
            await self._lipsync_scenes(
                scene_paths=scene_paths,
                dialogue_tracks=dialogue_tracks,
                working_dir=working_dir,
                progress=progress,
                is_cancelled=is_cancelled,
                only_scenes=resync,
                reaction_tails={
                    int(scene["clip_index"]): _reaction_tail_seconds(
                        scene.get("shots")
                    )
                    for scene in scenes
                    if scene.get("clip_index") is not None
                },
            )

        # A retake keeps the cut's order, so the foley beds are still keyed to
        # the right clips and travel as they are. The hook is rebuilt rather
        # than reused: the scene it is taken from may be the one just retaken.
        sfx_tracks = [dict(t) for t in (state.get("sfx_tracks") or [])]
        assembly_paths, assembly_dialogue, assembly_sfx = await self._with_cold_open(
            scene_paths,
            [
                {"clip_index": position, "script": scene.get("script") or {}}
                for position, scene in enumerate(ordered)
            ],
            dialogue_tracks,
            sfx_tracks,
            working_dir,
            narrative_mode=previous_result.get("narrative_mode", ""),
            language=previous_result.get("language", DEFAULT_LANGUAGE),
        )

        final_path = await self._assemble_final_drama(
            assembly_paths,
            working_dir,
            progress_callback,
            state.get("music_url"),
            previous_result.get("plan", "free"),
            is_cancelled=is_cancelled,
            dialogue_tracks=assembly_dialogue,
            director_style=previous_result.get("director_style", "cinematic_balanced"),
            transitions=plan_transitions([s["script"] for s in ordered]),
            aspect_ratio=previous_result.get("aspect_ratio", "16:9"),
            sfx_tracks=assembly_sfx,
        )

        # Update just the re-rendered scenes' records, then re-archive them so
        # the NEXT retake (of these or any other scene) still finds every clip.
        for target in targets:
            index = int(target["index"])
            target["shots"] = new_shots.get(index, [])
            target["take"] = takes.get(index, int(target.get("take", 1)))
            target.pop("clip_url", None)
            target.pop("clip_path", None)
        await self._archive_scene_clips(targets, scene_paths, working_dir)

        result = {**previous_result, "scenes": scenes}
        result["portraits"] = portraits
        result["location_plate"] = location_plate
        result["_render_state"] = {
            **state,
            "script": script_data,
            "dialogue_tracks": dialogue_tracks,
        }

        highest_take = max(takes.values()) if takes else 1
        await self._publish_master(
            result, final_path, working_dir, suffix=f"take{highest_take}"
        )
        await progress(
            "complete", f"Re-shot {label}", 100, {"video_url": result["video_url"]}
        )
        return result

    async def _publish_master(
        self,
        result: Dict[str, Any],
        final_path: Optional[str],
        working_dir: str,
        suffix: str,
    ) -> None:
        """Measure, upload and record a freshly assembled master on ``result``.

        Shared by every post-production path (retake, global edit, timeline
        edit) because they all have the same two ways to go wrong: reporting
        the ORIGINAL runtime after the cut changed it, and overwriting the
        previous master's object key — which leaves every already-issued
        signed URL (and any cache in front of it) pointing at a video that
        silently changed under the viewer.
        """
        job_id = os.path.basename(os.path.normpath(working_dir))

        actual_duration_seconds = None
        if final_path and os.path.isfile(final_path):
            from moviepy import VideoFileClip

            try:
                with VideoFileClip(final_path) as clip:
                    actual_duration_seconds = clip.duration
            except Exception as exc:
                logger.warning("Could not measure regenerated video duration: %s", exc)

        video_url = None
        if final_path and os.path.isfile(final_path) and not self.demo:
            from tools.supabase_storage import upload_video

            stored = await upload_video(final_path, f"{job_id}_{suffix}")
            if stored and stored.startswith("http"):
                video_url = stored

        result["video_path"] = final_path
        result["video_url"] = video_url or f"/api/jobs/{job_id}/video"
        if actual_duration_seconds is not None:
            result["duration_estimate"] = round(actual_duration_seconds)

    async def regenerate_scene(
        self,
        previous_result: Dict[str, Any],
        scene_index: int,
        working_dir: str,
        director_note: str = "",
        progress_callback: Optional[Callable] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Re-render ONE scene and splice it back into the finished drama."""
        return await self._rerender_scenes(
            previous_result=previous_result,
            scene_indices=[scene_index],
            working_dir=working_dir,
            director_note=director_note,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
        )

    def scenes_featuring(
        self, previous_result: Dict[str, Any], character_name: str
    ) -> List[int]:
        """Indices of the scenes a character actually appears in.

        Read from the recorded per-shot reference (see script2video's
        ``reference_character``) rather than from the script text, because the
        reference is what the picture was actually built from — a character
        named in the prose but never given a shot does not need re-rendering,
        and charging for those scenes would be charging for nothing.

        Falls back to "every scene" when no shot recorded a reference, which is
        the case for videos made before that field existed: re-rendering too
        much is recoverable, missing the character's scenes is not.
        """
        wanted = (character_name or "").strip().lower()
        if not wanted:
            return []
        scenes = previous_result.get("scenes") or []
        matched: List[int] = []
        saw_any_reference = False
        for scene in scenes:
            for shot in scene.get("shots") or []:
                reference = (shot.get("reference_character") or "").strip()
                if reference:
                    saw_any_reference = True
                if reference.lower() == wanted:
                    matched.append(int(scene["index"]))
                    break
        if not saw_any_reference:
            return [int(s["index"]) for s in scenes]
        return matched

    async def apply_global_edit(
        self,
        previous_result: Dict[str, Any],
        instruction: str,
        target: str,
        working_dir: str,
        scene_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Change one continuity fact everywhere it appears.

        ``target`` is either a character's name or the literal ``"location"``;
        ``instruction`` is the change in plain words ("put her in a red coat",
        "make it night"). The edit is applied to the LOCK first — the character
        portrait or the set plate — and only then are the affected scenes
        re-rendered against the new lock. Editing scene prompts alone would ask
        each scene to reinvent the same change independently, which is exactly
        the drift the locks exist to prevent.

        The script's own description of the target is patched too, because the
        identity clause built from it is restated in every frame prompt: a
        stale "wearing a grey coat" in the text would fight the new reference
        image for the rest of the drama.
        """
        instruction = (instruction or "").strip()
        if not instruction:
            raise SceneRegenerationUnavailable("Describe the change you want.")

        async def progress(stage: str, message: str, pct: float, data=None):
            if progress_callback:
                await progress_callback(stage, message, pct, data)

        if is_cancelled and is_cancelled():
            raise PipelineCancelled("Job cancelled")

        state = (previous_result or {}).get("_render_state") or {}
        script_data = dict(state.get("script") or {})
        if not script_data:
            raise SceneRegenerationUnavailable(
                "This video was made before continuity edits existed, so the "
                "information needed to change it was not kept. Generating it "
                "again will make edits available."
            )

        is_location = (target or "").strip().lower() in ("location", "set", "setting")
        portraits_override: Optional[Dict[str, str]] = None
        location_override: Optional[str] = None

        await progress("storyboard", "Updating the continuity lock", 8)

        if is_location:
            plate = previous_result.get("location_plate")
            if not plate:
                raise SceneRegenerationUnavailable(
                    "This video has no locked set to edit — its scenes were "
                    "not anchored to a single location."
                )
            prompt = (
                "Empty location plate. "
                f"{script_data.get('setting_location', '')}. "
                f"CHANGE TO APPLY: {instruction}. "
                "Keep the same room, the same architecture, materials and camera "
                "position — change only what the instruction names. No people."
            )
            location_override = await self.image_gen.generate_image_with_reference(
                prompt,
                plate,
                previous_result.get("aspect_ratio", "16:9"),
                is_cancelled=is_cancelled,
            )
            # Restate the change in the script's setting so every re-rendered
            # scene's prompt agrees with the new plate.
            script_data["setting_location"] = (
                f"{script_data.get('setting_location', '')} ({instruction})".strip()
            )
            affected = (
                scene_indices
                if scene_indices is not None
                else [int(s["index"]) for s in (previous_result.get("scenes") or [])]
            )
        else:
            portraits = previous_result.get("portraits") or {}
            name = next(
                (n for n in portraits if n.strip().lower() == (target or "").strip().lower()),
                None,
            )
            if not name:
                raise SceneRegenerationUnavailable(
                    f"There is no character called {target!r} in this video."
                )
            prompt = (
                f"Character portrait. CHANGE TO APPLY: {instruction}. "
                "Same person, same face, same age, same hair colour and length, "
                "same build — change only what the instruction names. "
                "Front-facing, neutral expression, studio lighting, high detail."
            )
            portraits_override = {
                name: await self.image_gen.generate_image_with_reference(
                    prompt, portraits[name], "1:1", is_cancelled=is_cancelled
                )
            }
            for character in script_data.get("characters") or []:
                if str(character.get("name", "")).strip().lower() == name.strip().lower():
                    character["description"] = (
                        f"{character.get('description', '')} ({instruction})".strip()
                    )
                    # Wardrobe is its own prompt clause; an edit that changes
                    # clothing has to land there or the old outfit is restated
                    # alongside the new reference image on every frame.
                    if character.get("wardrobe"):
                        character["wardrobe"] = (
                            f"{character['wardrobe']} ({instruction})".strip()
                        )
                    break
            affected = (
                scene_indices
                if scene_indices is not None
                else self.scenes_featuring(previous_result, name)
            )

        if not affected:
            raise SceneRegenerationUnavailable(
                f"{target} does not appear in any scene of this video."
            )

        return await self._rerender_scenes(
            previous_result=previous_result,
            scene_indices=affected,
            working_dir=working_dir,
            director_note=f"CONTINUITY EDIT (applies to every shot): {instruction}",
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
            portraits_override=portraits_override,
            location_plate_override=location_override,
            script_override=script_data,
        )

    async def restore_scene_take(
        self,
        previous_result: Dict[str, Any],
        scene_index: int,
        take: int,
        working_dir: str,
        progress_callback: Optional[Callable] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Put an earlier take of one scene back into the cut.

        Re-shooting is a roll of the dice, and the previous roll is often the
        better one -- a shot fails in its last second, not its first, so the
        take being replaced was usually 90% right. Without this, "re-shoot" is
        a one-way door: the only route back to take 1 is to buy a take 4 and
        hope. The clips already exist and were already paid for, so nothing
        here calls a generation model and nothing here costs credits.

        Implemented on top of apply_timeline_edit rather than beside it: the
        picture, the dialogue re-keying, the cold open and the master publish
        are the same problem a re-cut already solves, and a second assembly
        path is how the cold open went missing from two of them last time.
        The CURRENT cut is reused, so restoring a take inside a drama the user
        has already reordered or trimmed does not quietly undo that edit.
        """
        scenes = list(previous_result.get("scenes") or [])
        scene = next(
            (s for s in scenes if int(s.get("index", -1)) == int(scene_index)), None
        )
        if scene is None:
            raise SceneRegenerationUnavailable(
                f"Scene {int(scene_index) + 1} is not part of this video."
            )

        history = scene.get("takes") or []
        wanted = next(
            (t for t in history if int(t.get("take", 0)) == int(take)), None
        )
        if wanted is None:
            available = ", ".join(str(t.get("take")) for t in history) or "none"
            raise SceneRegenerationUnavailable(
                f"Take {take} of scene {int(scene_index) + 1} was not kept "
                f"(available: {available})."
            )

        clip_url = str(wanted.get("clip_url") or "").strip()
        clip_path = str(wanted.get("clip_path") or "").strip()
        if not clip_url and not (clip_path and os.path.isfile(clip_path)):
            raise SceneRegenerationUnavailable(
                f"The clip for take {take} of scene {int(scene_index) + 1} is "
                "no longer stored, so it cannot be restored."
            )

        # Record where the CURRENT take's clip lives before overwriting the
        # pointers, or restoring take 1 would strand take 3 with no way back.
        _record_take(
            scene,
            int(scene.get("take", 1) or 1),
            scene.get("clip_url"),
            scene.get("clip_path"),
        )
        scene["clip_url"] = clip_url
        scene["clip_path"] = clip_path
        scene["take"] = int(take)

        timeline = previous_result.get("timeline") or [
            {"scene_index": int(s["index"]), "trim_start": 0.0, "trim_end": 0.0}
            for s in sorted(
                (s for s in scenes if s.get("clip_index") is not None),
                key=lambda s: int(s["clip_index"]),
            )
        ]

        result = await self.apply_timeline_edit(
            previous_result={**previous_result, "scenes": scenes},
            timeline=timeline,
            working_dir=working_dir,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
        )
        result["scenes"] = scenes
        return result

    async def apply_timeline_edit(
        self,
        previous_result: Dict[str, Any],
        timeline: List[Dict[str, Any]],
        working_dir: str,
        progress_callback: Optional[Callable] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Re-cut a finished drama from clips that already exist.

        ``timeline`` is the new edit, in order: a list of
        ``{"scene_index": int, "trim_start": float, "trim_end": float}``.
        Scenes left out are dropped from the cut. Nothing here calls a
        generation model — reordering, trimming and dropping are pure ffmpeg
        work on clips the customer has already paid for, so this costs no
        credits and takes seconds instead of minutes.

        The dropped/reordered scenes' voice tracks follow the picture: dialogue
        is re-keyed to the new positions, so a scene moved to the front takes
        its lines with it instead of playing someone else's.
        """
        os.makedirs(working_dir, exist_ok=True)

        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        async def progress(stage: str, message: str, pct: float, data=None):
            if progress_callback:
                await progress_callback(stage, message, pct, data)

        scenes = list(previous_result.get("scenes") or [])
        by_index = {int(s["index"]): s for s in scenes if s.get("index") is not None}

        entries: List[Dict[str, Any]] = []
        for entry in timeline or []:
            index = int(entry.get("scene_index", -1))
            scene = by_index.get(index)
            if scene is None:
                raise SceneRegenerationUnavailable(
                    f"Scene {index + 1} is not part of this video."
                )
            entries.append(
                {
                    "scene": scene,
                    "index": index,
                    "trim_start": max(0.0, float(entry.get("trim_start", 0.0) or 0.0)),
                    "trim_end": max(0.0, float(entry.get("trim_end", 0.0) or 0.0)),
                }
            )
        if not entries:
            raise SceneRegenerationUnavailable(
                "A cut needs at least one scene — an empty timeline would "
                "produce an empty video."
            )

        missing = [
            e["index"] + 1
            for e in entries
            if not (
                e["scene"].get("clip_url")
                or (e["scene"].get("clip_path") and os.path.isfile(e["scene"]["clip_path"]))
            )
        ]
        if missing:
            raise SceneRegenerationUnavailable(
                "The clips for this video are no longer stored, so it cannot "
                f"be re-cut (missing: scene {missing[0]}). Please generate it again."
            )

        _check_cancel()
        await progress("assembly", "Re-cutting the timeline", 20)

        scene_paths: List[str] = []
        for position, entry in enumerate(entries):
            _check_cancel()
            scene = entry["scene"]
            local = scene.get("clip_path")
            if not (local and os.path.isfile(local)):
                local = os.path.join(working_dir, f"scene_{entry['index']}_restored.mp4")
                await download_video(scene["clip_url"], local)
            trimmed = await trim_clip(
                local,
                os.path.join(working_dir, f"cut_{position}_scene_{entry['index']}.mp4"),
                entry["trim_start"],
                entry["trim_end"],
            )
            scene_paths.append(trimmed)

        # Dialogue is keyed by the clip's POSITION in the cut, not by which
        # scene it came from, so a reorder has to re-key it or every line lands
        # on the wrong picture.
        state = (previous_result or {}).get("_render_state") or {}
        source_tracks = state.get("dialogue_tracks") or []
        clip_index_by_scene = {
            int(s["index"]): int(s["clip_index"])
            for s in scenes
            if s.get("clip_index") is not None
        }
        dialogue_tracks: List[Dict[str, Any]] = []
        for position, entry in enumerate(entries):
            origin = clip_index_by_scene.get(entry["index"])
            if origin is None:
                continue
            for track in source_tracks:
                if int(track.get("scene_index", -1)) == origin:
                    dialogue_tracks.append({**track, "scene_index": position})

        # Foley is re-keyed exactly like dialogue and for the same reason: a
        # bed is addressed by its clip's POSITION in the cut, so a reorder that
        # moved the dialogue and left the sound of the room behind would put
        # scene 3's footsteps under scene 1's picture.
        sfx_tracks: List[Dict[str, Any]] = []
        for position, entry in enumerate(entries):
            origin = clip_index_by_scene.get(entry["index"])
            if origin is None:
                continue
            for track in state.get("sfx_tracks") or []:
                if int(track.get("scene_index", -1)) == origin:
                    sfx_tracks.append({**track, "scene_index": position})

        scene_paths, dialogue_tracks, sfx_tracks = await self._with_cold_open(
            scene_paths,
            [
                {"clip_index": position, "script": entry["scene"].get("script") or {}}
                for position, entry in enumerate(entries)
            ],
            dialogue_tracks,
            sfx_tracks,
            working_dir,
            narrative_mode=previous_result.get("narrative_mode", ""),
            language=previous_result.get("language", DEFAULT_LANGUAGE),
        )

        _check_cancel()
        final_path = await self._assemble_final_drama(
            scene_paths,
            working_dir,
            progress_callback,
            state.get("music_url"),
            previous_result.get("plan", "free"),
            is_cancelled=is_cancelled,
            dialogue_tracks=dialogue_tracks,
            director_style=previous_result.get("director_style", "cinematic_balanced"),
            transitions=plan_transitions([e["scene"]["script"] for e in entries]),
            aspect_ratio=previous_result.get("aspect_ratio", "16:9"),
            sfx_tracks=sfx_tracks,
        )

        # The source scenes are kept intact (with their original clips) so the
        # cut can be revised again, or reverted, without re-rendering anything.
        result = {**previous_result}
        result["timeline"] = [
            {
                "scene_index": e["index"],
                "trim_start": e["trim_start"],
                "trim_end": e["trim_end"],
            }
            for e in entries
        ]
        result["scene_count"] = len(entries)
        version = int(previous_result.get("cut_version", 0)) + 1
        result["cut_version"] = version
        await self._publish_master(result, final_path, working_dir, suffix=f"cut{version}")
        await progress("complete", "New cut ready", 100, {"video_url": result["video_url"]})
        return result

    async def _with_cold_open(
        self,
        scene_paths: List[str],
        scene_records: List[Dict[str, Any]],
        dialogue_tracks: Optional[List[Dict[str, Any]]],
        sfx_tracks: Optional[List[Dict[str, Any]]],
        working_dir: str,
        narrative_mode: str = "",
        language: str = DEFAULT_LANGUAGE,
    ) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Put the hook in front of the film, and move everything timed with it.

        Written as one function used by all three assembly paths -- the first
        render, a retake, and a re-cut -- because it was first written as one:
        the hook lived only in the initial assembly, so re-cutting a
        micro-drama or retaking a single scene of one silently produced a film
        with no hook at all. A derived clip that only one of three assembly
        paths knows about is a feature that disappears the moment the customer
        edits anything.

        Rebuilt rather than carried across: a re-cut may have reordered the
        scenes, so the climax the hook is taken from may not be the one it was
        taken from last time. The teaser has to follow the story, not the file.
        """
        if not scene_paths:
            return scene_paths, list(dialogue_tracks or []), list(sfx_tracks or [])
        if not (
            micro_drama.is_micro_drama(narrative_mode)
            and micro_drama.is_cold_open_enabled()
        ):
            return scene_paths, list(dialogue_tracks or []), list(sfx_tracks or [])

        cold_open = await self._build_cold_open(
            scene_records, scene_paths, working_dir, language=language
        )
        if not cold_open:
            return scene_paths, list(dialogue_tracks or []), list(sfx_tracks or [])

        offset = len(cold_open)
        logger.info("Cold open: %d clip(s) in front of the drama.", offset)
        return (
            cold_open + scene_paths,
            self.shift_track_scenes(dialogue_tracks, offset),
            self.shift_track_scenes(sfx_tracks, offset),
        )

    async def _build_cold_open(
        self,
        scene_results: List[Dict[str, Any]],
        scene_paths: List[str],
        working_dir: str,
        language: str = DEFAULT_LANGUAGE,
    ) -> List[str]:
        """A glimpse of the climax, then a card, to put in front of the film.

        Returns the clips to PREPEND, or [] when there is nothing to build.
        Nothing here generates video: the teaser is the last second and a half
        of a scene that has already been rendered and paid for, which is what
        a flash-forward is — the same footage, shown early.

        The last second and a half specifically, because that is where the
        acted peak lands (interfaces/acting) and where the scene's own cut to
        the reaction sits. The opening of a clip is where a model settles into
        motion; nobody was ever hooked by that.
        """
        declared = None
        most_tense = None
        for scene in scene_results:
            clip_index = scene.get("clip_index")
            if clip_index is None or not (0 <= clip_index < len(scene_paths)):
                continue  # a scene that produced no clip has nothing to show
            script = scene.get("script") or {}
            if str(_scene_field(script, "dramatic_function") or "").lower() == "climax":
                declared = scene
            if most_tense is None or _scene_tension(script) > _scene_tension(
                most_tense.get("script") or {}
            ):
                most_tense = scene
        # A script that names its climax is believed. One that does not
        # (legacy scripts carry no dramatic_function) falls back to the most
        # tense scene that actually produced a clip -- tracked separately,
        # because deciding both in one pass is how "the peak" quietly became
        # "the first scene".
        climax = declared or most_tense
        if climax is None:
            return []

        source = scene_paths[int(climax["clip_index"])]
        teaser = await trim_to_duration(
            source,
            os.path.join(working_dir, "cold_open_teaser.mp4"),
            micro_drama.COLD_OPEN_SECONDS,
        )
        if teaser == source:
            # Nothing was trimmed, so the "teaser" would be the whole scene
            # played twice. That is not a hook, it is a repeat.
            return []

        card = await self._build_title_card(teaser, working_dir, language)
        return [teaser, card] if card else [teaser]

    async def _build_title_card(
        self,
        reference_clip: str,
        working_dir: str,
        language: str = DEFAULT_LANGUAGE,
    ) -> Optional[str]:
        """A black card reading "EARLIER", matched to the film's geometry.

        Without it the teaser reads as a continuity error rather than as a
        flash-forward — the viewer has no way to know the shock they just saw
        has not happened yet. Returns None if it cannot be made (no font, no
        encoder), which leaves the teaser in place: a hook without a card is
        still a hook.
        """
        font = _find_watermark_font()
        if not font:
            logger.info("No font available for the cold-open card; skipping it.")
            return None
        width, height = _probe_video_size(reference_clip)
        if width <= 0 or height <= 0:
            return None
        fps = 24
        text = micro_drama.card_text(language)
        output_path = os.path.join(working_dir, "cold_open_card.mp4")
        # Sized off the frame's shorter side for the same reason captions are
        # (see CAPTION_HEIGHT_FRACTION): one fixed size cannot serve both a
        # vertical and a horizontal master.
        font_size = max(16, int(round(min(width, height) * 0.075)))
        draw = (
            f"drawtext=fontfile='{font}':text='{text}':fontcolor=white"
            f":fontsize={font_size}:x=(w-text_w)/2:y=(h-text_h)/2"
            f":alpha='if(lt(t,0.2),t/0.2,if(lt(t,0.75),1,(1-(t-0.75)/0.25)))'"
        )
        try:
            process = await asyncio.create_subprocess_exec(
                resolve_ffmpeg_binary(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=black:s={width}x{height}:r={fps}:d={micro_drama.TITLE_CARD_SECONDS}",
                "-vf",
                draw,
                *video_encode_args(),
                "-an",
                output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
            if process.returncode == 0 and os.path.isfile(output_path):
                return output_path
            logger.warning(
                "Cold-open card failed (exit=%s): %s",
                process.returncode,
                stderr.decode("utf-8", errors="replace")[-500:],
            )
        except Exception as exc:
            logger.warning("Cold-open card unavailable: %s", exc)
        return None

    @staticmethod
    def shift_track_scenes(
        tracks: Optional[List[Dict[str, Any]]], offset: int
    ) -> List[Dict[str, Any]]:
        """Move every track's scene index along by ``offset``.

        Prepending the cold open puts clips in front of scene 0, and every
        piece of timed audio and every caption is addressed by its POSITION in
        that list. Without this shift the drama's first line would be laid
        over the teaser and each one after it would land a scene early — the
        exact failure the speech anchors exist to prevent, reintroduced by the
        hook.
        """
        if not tracks or offset <= 0:
            return list(tracks or [])
        return [
            {**track, "scene_index": int(track.get("scene_index", 0)) + offset}
            for track in tracks
        ]

    async def _generate_foley(
        self,
        scene_results: List[Dict[str, Any]],
        scene_paths: List[str],
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> List[Dict[str, Any]]:
        """A sound bed per scene, or an empty list. Never raises.

        The prompt is the scene's own ``audio_desc`` -- the storyboard agent
        has written one for every shot since the field existed, and until now
        nothing read it, so every drama this product has made was designed
        with a soundtrack it then threw away.

        Scenes are generated concurrently and failures are swallowed per
        scene: foley is the layer a film can most afford to lose, and it is
        being added at the very end of a job the customer has already paid
        for.
        """
        if self.demo or not is_foley_enabled() or not scene_paths:
            return []

        generator = MuAPISFXGenerator(self.api_key, demo=self.demo)

        async def _one(scene: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            clip_index = scene.get("clip_index")
            if clip_index is None or not (0 <= clip_index < len(scene_paths)):
                return None
            shots = scene.get("shots") or []
            # The master shot's note describes the scene; a two-second cutaway
            # of a face has nothing of its own to sound like.
            audio_desc = next(
                (str(s.get("audio_desc") or "").strip() for s in shots if s.get("audio_desc")),
                "",
            )
            duration = _probe_video_duration(scene_paths[clip_index])
            if duration <= 0:
                return None
            try:
                url = await generator.generate_scene_sfx(
                    audio_desc,
                    duration=duration,
                    scene_emotion=_scene_emotion(scene.get("script")),
                    is_cancelled=is_cancelled,
                )
            except Exception as exc:
                logger.warning(
                    "Foley failed for scene %s, continuing without it: %s",
                    scene.get("index"),
                    exc,
                )
                return None
            if not url:
                return None
            return {"scene_index": int(clip_index), "audio_url": url}

        results = await asyncio.gather(
            *[_one(scene) for scene in scene_results], return_exceptions=True
        )
        tracks = [r for r in results if isinstance(r, dict)]
        if tracks:
            logger.info("Generated foley for %d scene(s).", len(tracks))
        return tracks

    async def _assemble_final_drama(
        self,
        scene_paths: List[str],
        working_dir: str,
        progress_callback: Optional[Callable] = None,
        music_url: Optional[str] = None,
        plan: str = "free",
        is_cancelled: Optional[Callable[[], bool]] = None,
        dialogue_tracks: Optional[List[Dict[str, Any]]] = None,
        director_style: str = "cinematic_balanced",
        transitions: Optional[List[float]] = None,
        aspect_ratio: str = "16:9",
        sfx_tracks: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Concatenate all scene videos, color-grade, add background music,
        burn dialogue captions (when tracks present), then watermark
        (Free plan only) — exactly once per drama.

        Cancel is checked BEFORE each step starts (concat / grade / music /
        subtitles / watermark). Once an ffmpeg/moviepy render has begun we
        intentionally do NOT abort mid-write — that would leave a half-baked
        file on disk.
        """
        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        os.makedirs(working_dir, exist_ok=True)

        # Before concatenate
        _check_cancel()
        if progress_callback:
            await progress_callback("assembly", "Concatenating scene videos", 85)

        concatenated_path = os.path.join(working_dir, "drama_concatenated.mp4")
        # Crossfade transitions are opt-in (MUSEFORGE_SCENE_TRANSITIONS) --
        # moviepy's "compose" mode they require is heavier on memory than
        # the default ffmpeg stream-copy path, so it stays off unless
        # explicitly enabled.
        # A planned boundary list decides per join (see interfaces/
        # transitions); an all-cuts plan hands straight back to the cheap
        # stream-copy path inside the transition concat itself. The env flag
        # remains the master switch because compositing costs memory.
        if is_scene_transitions_enabled() and any(transitions or []):
            await concatenate_videos_with_transitions(
                scene_paths, concatenated_path, transitions=transitions
            )
        else:
            await concatenate_videos(scene_paths, concatenated_path)

        # Before color grade
        _check_cancel()
        if progress_callback:
            await progress_callback("grade", "Applying color grade", 89)

        graded_path = os.path.join(working_dir, "drama_graded.mp4")
        # The grade encode also conforms the master to the ordered aspect
        # ratio (no-op when the clips already carry it, which is the normal
        # case since every frame was generated at that ratio).
        await apply_color_grade(
            concatenated_path,
            graded_path,
            director_style=director_style,
            aspect_ratio=aspect_ratio,
        )

        # Before music mix
        _check_cancel()
        if progress_callback:
            await progress_callback("music", "Adding background music", 93)

        with_music_path = os.path.join(working_dir, "drama_with_music.mp4")
        # Foley rides in beside the score and the dialogue rather than in a
        # pass of its own: a second pass would mean a second encode of the
        # same master (see mix_audio_layers).
        #
        # The bare three-argument call is kept for the case where there is
        # neither dialogue nor foley, and not only for tidiness: passing a
        # keyword whose value is None still changes the call's shape, and the
        # music-only path is the one every existing caller and test double
        # was written against.
        if dialogue_tracks or sfx_tracks:
            await add_background_music(
                graded_path,
                with_music_path,
                music_url,
                dialogue_tracks=dialogue_tracks,
                scene_paths=scene_paths,
                sfx_tracks=sfx_tracks,
            )
        else:
            await add_background_music(graded_path, with_music_path, music_url)

        # Burn captions only when dialogue tracks are actually present —
        # no extra ffmpeg work when dialogue is off / empty.
        video_for_final = with_music_path
        if dialogue_tracks:
            _check_cancel()
            if progress_callback:
                await progress_callback("subtitles", "Burning captions", 95)
            subtitled_path = os.path.join(working_dir, "drama_subtitled.mp4")
            await burn_subtitles(
                with_music_path,
                subtitled_path,
                dialogue_tracks,
                scene_paths=scene_paths,
            )
            video_for_final = subtitled_path

        # Master finishing (fades + loudness) BEFORE the watermark so the
        # watermark stays at constant opacity over the fade to black.
        if is_finishing_enabled():
            _check_cancel()
            if progress_callback:
                await progress_callback("finishing", "Mastering fades & loudness", 96)
            finished_path = os.path.join(working_dir, "drama_finished.mp4")
            video_for_final = await finalize_master(video_for_final, finished_path)

        final_path = os.path.join(working_dir, "drama_final.mp4")
        if plan in WATERMARK_PLANS:
            # Before watermark render
            _check_cancel()
            if progress_callback:
                await progress_callback("music", "Applying watermark", 97)
            await add_watermark(video_for_final, final_path)
        else:
            final_path = video_for_final
        check_master_duration(final_path, scene_paths)
        return final_path

    async def write_script_only(
        self,
        idea: str,
        style: str = "Cinematic",
        num_scenes: int = 3,
        user_requirement: str = "",
        progress_callback: Optional[Callable] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        preset_characters: Optional[List[Dict[str, Any]]] = None,
        language: str = DEFAULT_LANGUAGE,
        dialogue_enabled: bool = False,
        narrative_mode: str = "",
    ) -> DramaScript:
        """Phase A: screenwriting only — no portraits / frames / video."""

        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        async def progress(stage: str, message: str, pct: float, data=None):
            if progress_callback:
                await progress_callback(stage, message, pct, data)

        _check_cancel()
        await progress("screenwriting", "Writing script", 5)
        return await self.screenwriter.write_script(
            idea,
            style,
            num_scenes,
            user_requirement,
            preset_characters=preset_characters,
            language=language,
            # The screenwriter is otherwise free to write a silent film --
            # the base prompt explicitly allows empty dialogue lists -- and a
            # silent script on a run the user enabled (and paid for) dialogue
            # on produces no voices, no captions and, with music off, a master
            # with no audio stream at all.
            require_dialogue=dialogue_enabled,
            # Cinematic or micro-drama: two different dramatic curves, not one
            # curve at two lengths (see interfaces/micro_drama).
            narrative_mode=narrative_mode,
        )

    async def continue_from_script(
        self,
        script: DramaScript,
        style: str = "Cinematic",
        director_style: str = "cinematic_balanced",
        user_requirement: str = "",
        aspect_ratio: str = "16:9",
        working_dir: str = "/tmp/museforge_drama",
        progress_callback: Optional[Callable] = None,
        music_url: Optional[str] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        character_portraits_override: Optional[Dict[str, str]] = None,
        music_enabled: bool = False,
        dialogue_enabled: bool = False,
        lipsync_enabled: bool = False,
        plan: str = "free",
        library_characters: Optional[List[Dict[str, Any]]] = None,
        location_image_override: Optional[str] = None,
        language: str = DEFAULT_LANGUAGE,
        narrative_mode: str = "",
    ) -> dict:
        """Phase B: everything after screenwriting (portraits → scenes → assemble)."""
        os.makedirs(working_dir, exist_ok=True)

        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        async def progress(stage: str, message: str, pct: float, data=None):
            if progress_callback:
                await progress_callback(stage, message, pct, data)

        # A template script means every LLM provider failed: the user's idea
        # was effectively discarded and they are about to get a generic drama
        # about "Alex" in a "generic cinematic location", with no dialogue and
        # no described wardrobe. Rendering it anyway spends the user's credits
        # on a video of a different person, in a different room, saying
        # nothing -- and it looks to them like the product cannot follow a
        # prompt. The job fails instead, which refunds the credits (see
        # jobs.run_generation_job) and states the real cause.
        #
        # Demo mode is exempt: there the template IS the intended offline
        # fixture, and nothing is charged.
        if getattr(script, "generated_by", "llm") == "template" and not self.demo:
            logger.error(
                "Screenwriter fell back to the deterministic template for this "
                "job -- no LLM provider answered. The user's idea is NOT "
                "reflected in the script, so the render is being refused. "
                "Check ANTHROPIC_API_KEY (and MUAPI_LLM_MODEL if the MuAPI LLM "
                "path is meant to be enabled)."
            )
            await progress(
                "screenwriting",
                "Script model unavailable — the result would not follow your "
                "idea, so nothing was rendered.",
                8,
                {"script_degraded": True},
            )
            raise ScriptGenerationFailed(
                "The script model is unavailable, so your idea could not be "
                "turned into a script. Your credits have been refunded — "
                "please try again shortly."
            )

        characters = self._characters_from_script(script)
        if not characters:
            characters = [
                CharacterInScene(
                    idx=0, name="Protagonist",
                    static_features="main character", dynamic_features="", is_visible=True,
                )
            ]

        # Apply library character features + portraits (Pro reuse path).
        lib_by_name: Dict[str, Dict[str, Any]] = {}
        for lib in library_characters or []:
            name = str(lib.get("name") or "").strip()
            if not name:
                continue
            lib_by_name[name] = lib
            url = str(lib.get("portrait_url") or "").strip()
            if url:
                character_portraits_override = dict(character_portraits_override or {})
                character_portraits_override.setdefault(name, url)

        for char in characters:
            lib = lib_by_name.get(char.name)
            if lib and lib.get("static_features"):
                char.static_features = str(lib["static_features"])

        # If the user uploaded a reference photo under a name that doesn't
        # match any character the screenwriter came up with, add it as its
        # own character rather than silently dropping the upload.
        if character_portraits_override:
            existing_names = {c.name for c in characters}
            for name in character_portraits_override:
                if name not in existing_names:
                    lib = lib_by_name.get(name) or {}
                    characters.append(
                        CharacterInScene(
                            idx=len(characters),
                            name=name,
                            static_features=str(
                                lib.get("static_features") or "uploaded reference photo"
                            ),
                            dynamic_features="",
                            is_visible=True,
                        )
                    )

        # The cast lock and the SET lock are independent -- the plate is shot
        # deliberately empty, so it needs no portrait -- but they used to be
        # awaited one after the other, and no scene starts until both land.
        # Run them together: on a job with a set and any cast at all this is
        # a whole image round trip of dead time removed from every render.
        #
        # The plate is generated at the drama's own aspect ratio (unlike
        # portraits, which are square) because it is a background reference,
        # so its framing has to match the frames it will condition.
        _check_cancel()
        await progress("portraits", "Locking cast and set for consistency", 10)
        portraits, location_plate = await asyncio.gather(
            self._lock_character_portraits(
                characters, style, character_portraits_override=character_portraits_override
            ),
            self._lock_location_plate(
                script,
                style,
                aspect_ratio=aspect_ratio,
                location_image_override=location_image_override,
            ),
        )

        # Dynamic reference selection (adapted from ViMax's "previous
        # timeline" technique): as scenes progress, prefer each character's
        # MOST RECENTLY generated frame over the static locked portrait as
        # the identity reference for the next shot. This tracks drift in
        # outfit/pose/lighting across the story better than always pinning
        # to the first-ever portrait. Reset per call so retries/re-runs on
        # the same pipeline instance don't leak state from a prior attempt.
        # Starts empty -- the very first shot of the whole drama has no
        # entry yet, so it still falls back to the locked portrait exactly
        # as before.
        self._last_frame_by_character: Dict[str, str] = {}

        scene_paths: List[str] = []
        scene_results: List[Dict[str, Any]] = []
        dialogue_tracks: List[Dict[str, Any]] = []
        lipsynced_scenes: List[int] = []
        dialogue_requested = (
            dialogue_enabled and is_dialogue_enabled() and not self.demo
        )
        # Every audio stage below is deliberately fail-open: a dead voice
        # provider must not throw away a finished picture. The cost of that is
        # a master with NO audio stream at all (music off + no voice = a silent
        # mp4), delivered without a word of explanation — the user switched
        # dialogue on, paid the dialogue surcharge, and got silence that looks
        # exactly like a broken feature. Collect the reasons instead and hand
        # them back on the result.
        warnings: List[str] = []
        if dialogue_enabled and not dialogue_requested and not self.demo:
            warnings.append(
                "Spoken dialogue is switched off on this server, so the video "
                "was rendered without voices."
            )
        voice_gen = (
            _make_voice_generator(self.api_key, self.demo, working_dir)
            if dialogue_requested
            else None
        )
        character_voices: Dict[str, str] = {}
        if voice_gen is not None:
            # A returning character's voice, decided when they were first cast
            # and stored on the library entry. Applied BEFORE the ensemble is
            # cast, because casting skips a name that already has a voice --
            # see VoiceGenerator.lock_voices for why the hash alone does not
            # survive a change of cast.
            locked_voices = {
                str(lib.get("name") or ""): str(lib.get("voice_id") or "")
                for lib in (library_characters or [])
                if str(lib.get("voice_id") or "").strip()
            }
            if locked_voices and hasattr(voice_gen, "lock_voices"):
                voice_gen.lock_voices(locked_voices)
            # Cast the whole ensemble up front, gender-matched to each
            # character's description -- otherwise the per-line hash fallback
            # can voice a mother with a male voice.
            character_voices = voice_gen.cast_characters(characters) or {}
            # Then ask the provider whether it can actually speak with those
            # voices. An id the account does not hold is not answered with
            # silence -- the endpoint substitutes and the drama ships with the
            # wrong person talking, which is only ever noticed by watching it.
            # Fail-open: an account that cannot be asked casts as before.
            if hasattr(voice_gen, "verify_cast"):
                try:
                    character_voices = (
                        await voice_gen.verify_cast() or character_voices
                    )
                except Exception as exc:
                    logger.warning("Could not verify the cast: %s", exc)
        total_scenes = max(1, len(script.scenes))

        # Kick off background music as soon as the mood is known (it needs
        # nothing from the scene loop) so its generation time overlaps with
        # scene rendering instead of adding to the end of the job. Best-effort
        # — any failure just leaves music_url as None, same as before.
        music_task: Optional["asyncio.Task"] = None
        if music_enabled and not self.demo and not music_url:

            async def _generate_music() -> Optional[str]:
                try:
                    music_gen = _make_music_generator(self.api_key, demo=self.demo)
                    return await music_gen.generate_instrumental(
                        mood=script.mood or "cinematic",
                        style_hint=_music_style_hint(script),
                    )
                except Exception as exc:
                    logger.warning("Background music generation failed, continuing without music: %s", exc)
                    return None

            music_task = asyncio.create_task(_generate_music())

        # Scene dialogue is generated in the background too: it only feeds
        # the final audio mix, not the next scene's visual continuity (that
        # comes from the video's last frame), so there's no need to block
        # the next scene's rendering on it finishing first.
        dialogue_tasks: List[tuple] = []

        # Drama-wide direction: identical for every scene, so build it once.
        character_direction = _format_character_direction(script)

        # Fixed second budget for the whole drama, split by tension. The total
        # is decided here -- before any provider call -- so the cost of the job
        # is known at charge time and cannot drift with what the story turns
        # out to be. Tension still shapes the RHYTHM within that total.
        scene_durations = distribute_budget(
            [_scene_tension(scene) for scene in script.scenes]
        )
        logger.info(
            "Second budget for job: %s (total %ss across %s scenes)",
            scene_durations,
            billable_seconds(scene_durations),
            len(script.scenes),
        )

        # Scene rendering is the whole cost of a job: each scene is a Kling
        # call that takes 1-3+ minutes, and with one shot per scene the
        # existing per-shot concurrency never engaged, so a 5-scene drama
        # spent 5 x that time strictly in series.
        #
        # Scenes are only independent when identity references are NOT chained
        # forward (the default -- see is_dynamic_reference_enabled). With
        # chaining on, scene N's reference is scene N-1's finished frame, so
        # that mode stays strictly sequential and simply renders as before.
        scene_concurrency = _scene_concurrency(total_scenes)

        def _scene_progress_data(done: int) -> Dict[str, Any]:
            """Counters the live ETA measures this deployment's rate from.

            The estimate shown to the user is only a prior until a scene
            actually lands; these three numbers are what turn it into a
            measurement (see interfaces/render_eta.RenderEta.observe).
            """
            return {
                "scenes_completed": done,
                "scenes_total": total_scenes,
                "scene_concurrency": scene_concurrency,
            }

        shot_scales = plan_shot_scales(script.scenes)
        scene_slots: List[Optional[Dict[str, Any]]] = [None] * len(script.scenes)
        scene_semaphore = asyncio.Semaphore(scene_concurrency)
        progress_lock = asyncio.Lock()
        completed_scenes = 0

        async def _render_scene(idx: int, scene: Any) -> None:
            nonlocal completed_scenes
            async with scene_semaphore:
                _check_cancel()
                scene_dialogue_lines = _scene_dialogue(scene)
                story_so_far, not_yet = _format_story_state(script.scenes, idx)
                world_change, world_state = _world_state(script.scenes, idx)

                async def scene_progress(stage, message, pct, data=None, _idx=idx):
                    # Scenes may finish out of order, so progress tracks how
                    # many have COMPLETED rather than which one is running --
                    # a percentage that jumps backwards reads as a bug.
                    async with progress_lock:
                        base = 15 + (completed_scenes / total_scenes) * 65
                        await progress(
                            stage, f"[{_idx + 1}/{total_scenes}] {message}", base, data
                        )

                scene_slots[idx] = await self.script2video.run(
                    script=_scene_action(scene),
                    characters=characters,
                    user_requirement=user_requirement,
                    style=style,
                    working_dir=os.path.join(working_dir, f"scene_{idx}"),
                    progress_callback=scene_progress,
                    scene_idx=idx,
                    total_scenes=total_scenes,
                    character_portraits=portraits,
                    director_style=director_style,
                    aspect_ratio=aspect_ratio,
                    is_cancelled=is_cancelled,
                    plan=plan,
                    setting_location=getattr(script, "setting_location", "") or "",
                    setting_time_of_day=getattr(script, "setting_time_of_day", "") or "",
                    setting_era=getattr(script, "setting_era", "") or "",
                    location_plate_url=location_plate,
                    has_dialogue=dialogue_requested and bool(scene_dialogue_lines),
                    # Decides whether the frame is asked to SHOW the mouth or
                    # hide it — opposite instructions, see build_frame_prompt.
                    lipsync_enabled=lipsync_enabled and dialogue_requested,
                    last_frame_by_character=self._last_frame_by_character,
                    scene_emotion=_scene_emotion(scene),
                    # Always pass the words themselves to the storyboard step,
                    # independent of whether VOICE generation is enabled --
                    # dialogue is what tells the artist which moment matters.
                    scene_dialogue=_format_scene_dialogue(scene_dialogue_lines),
                    scene_direction=_format_scene_direction(scene),
                    # Where this scene sits in the story. Without it every
                    # scene is designed as if it were the only one, and the
                    # most striking beat in the brief gets staged in all of
                    # them — including scene 1, which spoils the payoff.
                    story_so_far=story_so_far,
                    not_yet=not_yet,
                    # The drama's event, and whether this scene causes it or
                    # inherits it. The locked-setting clause in the frame
                    # prompt otherwise renders the climax under the opening
                    # scene's lamps — see build_frame_prompt.
                    world_change=world_change,
                    world_state=world_state,
                    scene_tension=_scene_tension(scene),
                    scene_duration=scene_durations[idx] if idx < len(scene_durations) else 0.0,
                    character_direction=character_direction,
                    theme=getattr(script, "theme", "") or "",
                    visual_motif=getattr(script, "visual_motif", "") or "",
                    # The user's own words, verbatim. The scene action line is
                    # the screenwriter's paraphrase; the brief is what the user
                    # actually asked for, so shot design is held to it.
                    user_brief=getattr(script, "user_brief", "") or "",
                    # Planned across the whole script BEFORE any scene is
                    # designed. Scenes are storyboarded in parallel, so this is
                    # the only place in the system that can see two of them at
                    # once -- and repetition is only visible from there.
                    scene_shot_scale=(
                        shot_scales[idx] if idx < len(shot_scales) else ""
                    ),
                )
                async with progress_lock:
                    completed_scenes += 1
                    await progress(
                        "video",
                        f"Scene {completed_scenes}/{total_scenes} complete",
                        15 + (completed_scenes / total_scenes) * 65,
                        _scene_progress_data(completed_scenes),
                    )

        try:
            # Opens the scene phase, and starts the clock the live ETA measures
            # its rate against (jobs.Job._eta). It has to be emitted BEFORE the
            # first scene rather than only on completion: with no start marker
            # the tracker would see its first scene land in zero elapsed time
            # and could not derive a rate at all.
            await progress(
                "video",
                f"Rendering {total_scenes} scene(s)",
                15,
                _scene_progress_data(0),
            )
            if scene_concurrency <= 1:
                # Strictly sequential: preserves the exact previous ordering,
                # which the reference-chaining mode depends on.
                for idx, scene in enumerate(script.scenes):
                    await _render_scene(idx, scene)
            else:
                scene_tasks = [
                    asyncio.create_task(_render_scene(idx, scene))
                    for idx, scene in enumerate(script.scenes)
                ]
                try:
                    await asyncio.gather(*scene_tasks)
                except BaseException:
                    # gather() propagates the first failure but does NOT stop
                    # the siblings -- left alone they would keep polling the
                    # provider (and burning credits) behind a failed job.
                    for task in scene_tasks:
                        task.cancel()
                    await asyncio.gather(*scene_tasks, return_exceptions=True)
                    raise

            # Collect results in SCENE order regardless of completion order --
            # scene_paths feeds concatenation, so a shuffled list would splice
            # the drama out of sequence.
            for idx, scene in enumerate(script.scenes):
                scene_result = scene_slots[idx]
                if scene_result is None:
                    continue
                assembled_scene_index = None
                if scene_result.get("path"):
                    scene_paths.append(scene_result["path"])
                    assembled_scene_index = len(scene_paths) - 1

                scene_dialogue_lines = _scene_dialogue(scene)
                if voice_gen is not None and scene_dialogue_lines and assembled_scene_index is not None:
                    task = asyncio.create_task(
                        voice_gen.generate_scene_dialogue(
                            scene_dialogue_lines,
                            is_cancelled=is_cancelled,
                            language=language,
                            # The same beat the face is playing. Without it a
                            # scene could look like grief and sound like a
                            # weather report -- the picture was directed and
                            # the voice was not.
                            emotion=_scene_emotion(scene),
                        )
                    )
                    dialogue_tasks.append(
                        (assembled_scene_index, idx, task, list(scene_dialogue_lines))
                    )

                serialized_scene = scene.model_dump() if hasattr(scene, "model_dump") else scene
                scene_results.append(
                    {
                        "index": idx,
                        "script": serialized_scene,
                        "shots": scene_result.get("shots", []),
                        # Position in scene_paths, i.e. in the concatenation.
                        # Not always == index: a scene that produced no clip is
                        # skipped, which shifts every later scene down one.
                        "clip_index": assembled_scene_index,
                    }
                )

            # Foley, one bed per scene, from the sound note the storyboard has
            # been writing into every shot and nothing has ever read
            # (StoryboardShot.audio_desc). A cent a scene, and the layer that
            # most separates a drama from a slideshow with music over it.
            #
            # Fired here rather than beside the scene render because it wants
            # the FINISHED clip's length, and because a foley failure must not
            # be able to take a rendered scene down with it.
            sfx_tracks = await self._generate_foley(
                scene_results, scene_paths, is_cancelled=is_cancelled
            )

            _check_cancel()
            failed_dialogue_scenes: List[int] = []
            dialogue_failure_reasons: List[str] = []
            for assembled_scene_index, scene_number, task, scene_lines in dialogue_tasks:
                try:
                    generated_tracks = await task
                    # The scene's TURN travels with its lines. Kinetic
                    # captions emphasise the words a scene actually turns on
                    # (see interfaces/ass_captions.emphasis_stems), and the
                    # screenwriter has already written that sentence -- which
                    # is both free and, unlike a list of trigger words, in
                    # whatever language the drama is in.
                    turn = _scene_field(script.scenes[scene_number], "turn")
                    for track in generated_tracks:
                        dialogue_tracks.append(
                            {
                                **track,
                                "scene_index": assembled_scene_index,
                                "emphasis": turn,
                            }
                        )
                except Exception as exc:
                    logger.warning(
                        "Scene %s dialogue failed, continuing without its voice layer: %s",
                        scene_number + 1,
                        exc,
                    )
                    failed_dialogue_scenes.append(scene_number + 1)
                    # The words survive even when the voice does not: the
                    # script already holds them, and a silent film with
                    # subtitles is watchable where a silent film without them
                    # is a mime show the viewer cannot even tell is missing
                    # something.
                    dialogue_tracks.extend(
                        caption_only_tracks(scene_lines, assembled_scene_index)
                    )
                    # Deduped: every scene fails the same way when the cause
                    # is the request itself, and "the provider said X" five
                    # times over is noise, not information.
                    reason = _provider_reason(exc)
                    if reason and reason not in dialogue_failure_reasons:
                        dialogue_failure_reasons.append(reason)
            if dialogue_requested:
                # DIALOGUE_CLAUSE allows ONE deliberately silent scene, because
                # a held look is an instrument and banning it made every beat
                # get discharged through speech. Two or more is not an
                # instrument, it is the writer running out of lines on a run
                # the user paid the dialogue surcharge for -- and it is
                # invisible from the finished video, which simply looks like
                # scenes where nobody bothered to speak.
                silent_scenes = sum(
                    1 for scene in script.scenes if not _scene_dialogue(scene)
                )
                if silent_scenes > 1:
                    warnings.append(
                        f"{silent_scenes} of {len(script.scenes)} scenes were "
                        "written without dialogue, so they play silent. One "
                        "silent scene is a deliberate choice; this many is the "
                        "script coming back thinner than it should have."
                    )
                if not dialogue_tasks:
                    # The script came back with no spoken lines at all, so
                    # there was never anything to voice. The screenwriter is
                    # now told when a run is going to be voiced (see
                    # ScreenwriterAgent.DIALOGUE_CLAUSE), which makes this
                    # rare -- but an approved/edited script can still arrive
                    # silent, and silently shipping it is what made this look
                    # like the dialogue feature failing.
                    warnings.append(
                        "The script has no spoken lines, so there was nothing "
                        "to voice — the video has no dialogue."
                    )
                elif not has_voiced_track(dialogue_tracks):
                    # Not `not dialogue_tracks`: the list now also holds the
                    # caption rows written for the scenes that failed, so the
                    # only question it can still answer is whether anything is
                    # AUDIBLE.
                    #
                    # The reason is attached because without it this sentence
                    # is unactionable for everyone who reads it: the user
                    # cannot tell a provider outage from a broken request,
                    # and whoever fixes it has to go digging in server logs
                    # for a message the job already had in its hands. A
                    # request that is malformed fails every scene identically,
                    # so this is exactly the case where the reason matters
                    # most and costs one line.
                    warnings.append(
                        "Voice generation failed for every scene, so the video "
                        "plays silent with the dialogue shown as captions."
                        + _reason_suffix(dialogue_failure_reasons)
                    )
                elif failed_dialogue_scenes:
                    scenes_label = ", ".join(str(n) for n in failed_dialogue_scenes)
                    warnings.append(
                        f"Voice generation failed for scene(s) {scenes_label}, "
                        f"which play with captions instead of spoken lines."
                        + _reason_suffix(dialogue_failure_reasons)
                    )

            # Drive the mouths from the voice track that is about to be
            # played. Deliberately placed AFTER dialogue is collected and
            # BEFORE assembly: the provider works on one clip at a time, and
            # by this point each scene clip and its audio both exist. A synced
            # scene's audio is baked into its clip, so its track is stripped
            # of `audio_url` (keeping the text for subtitles) -- otherwise the
            # mixer would lay the same speech over it a second time and every
            # line would be heard twice, slightly out of phase.
            _check_cancel()
            lipsynced_scenes = await self._lipsync_scenes(
                scene_paths=scene_paths,
                dialogue_tracks=dialogue_tracks,
                working_dir=working_dir,
                progress=progress,
                is_cancelled=is_cancelled,
                requested=lipsync_enabled,
                # Keyed by position in the concatenation, which is what
                # _lipsync_scenes indexes scene_paths by -- not by scene index,
                # which differs the moment a scene produces no clip.
                reaction_tails={
                    int(scene["clip_index"]): _reaction_tail_seconds(
                        scene.get("shots")
                    )
                    for scene in scene_results
                    if scene.get("clip_index") is not None
                },
            )

            # The user switched lip sync on and paid a credit per speaking
            # scene for it. When none of those scenes came back synced, the
            # video is indistinguishable from one that never asked -- closed
            # mouths and a voice over the top -- so the job has to say so
            # rather than let them wonder whether the feature exists.
            if lipsync_enabled and dialogue_requested and not lipsynced_scenes:
                warnings.append(
                    "Lip sync did not run on any scene, so the voices play "
                    "over the picture instead of driving the mouths. The "
                    "server log line beginning \"Lip sync\" says which stage "
                    "declined it."
                )

            # Archive each finished scene clip individually, not just the
            # concatenated master. Regenerating scene 3 later has to splice it
            # back in beside scenes 1, 2 and 4 -- and the working dir is wiped
            # once the master uploads, so without this the only surviving
            # artifact is a master that cannot be taken apart again.
            await self._archive_scene_clips(scene_results, scene_paths, working_dir)
        except BaseException:
            if music_task is not None:
                music_task.cancel()
            for _, _, task in dialogue_tasks:
                task.cancel()
            raise

        final_path: Optional[str] = None
        video_url: Optional[str] = None

        if music_task is not None:
            music_url = await music_task
            if not music_url:
                warnings.append(
                    "Background music could not be generated, so the video "
                    "was rendered without a score."
                )

        actual_duration_seconds: Optional[float] = None
        if self.demo or not scene_paths:
            await progress("assembly", "Assembling preview", 90)
            for scene in reversed(scene_results):
                shots = scene.get("shots") or []
                if shots and shots[-1].get("video_url"):
                    video_url = shots[-1]["video_url"]
                    break
        else:
            # The hook, for dramas written to the micro-drama shape: a glimpse
            # of the climax, a card, and only then scene 1. Prepended to the
            # CLIP LIST rather than spliced in afterwards, so the duration
            # check, the captions and the mix all see the same film.
            scene_paths, dialogue_tracks, sfx_tracks = await self._with_cold_open(
                scene_paths,
                scene_results,
                dialogue_tracks,
                sfx_tracks,
                working_dir,
                narrative_mode=narrative_mode,
                language=language,
            )

            final_path = await self._assemble_final_drama(
                scene_paths,
                working_dir,
                progress_callback,
                music_url,
                plan,
                is_cancelled=is_cancelled,
                dialogue_tracks=dialogue_tracks,
                director_style=director_style,
                # Planned from the SCENES THAT MADE IT into the cut, in cut
                # order -- a scene that produced no clip is not a boundary.
                transitions=plan_transitions(
                    [s["script"] for s in scene_results if s.get("clip_index") is not None]
                ),
                aspect_ratio=aspect_ratio,
                sfx_tracks=sfx_tracks,
            )
            # Measure the real assembled length before upload/cleanup — the
            # screenwriter's estimated_duration_seconds is a pre-generation
            # guess and can drift far from reality since storyboard_artist
            # picks each shot's actual duration (3-15s) independently, later.
            if final_path and os.path.isfile(final_path):
                from moviepy import VideoFileClip

                try:
                    with VideoFileClip(final_path) as _clip:
                        actual_duration_seconds = _clip.duration
                except Exception as exc:
                    logger.warning("Could not measure final video duration: %s", exc)

            # The budget was fixed before any provider call so the job's cost
            # was known at charge time. Until now nothing ever compared it to
            # what actually shipped -- see check_budget_was_honoured.
            budget_notice = check_budget_was_honoured(
                actual_duration_seconds, len(script.scenes)
            )
            if budget_notice:
                warnings.append(budget_notice)

            # Every audio layer is independently optional, and each one is
            # correct to be off on its own. Nothing ever looked at the sum:
            # music off, foley off and a script with a few short lines gives a
            # master that is mostly DIGITAL SILENCE, not room tone. Measured on
            # a delivered drama -- 12 audible seconds in 60, the other 43 of
            # them absolute zero -- and the speech that remained sounded pasted
            # on because there was no scene underneath it to sit in. Reported,
            # not repaired: the fix is a layer the operator has to switch on
            # and pay for, and inventing ambience here would be a decision this
            # code is not entitled to make.
            silence_notice = check_master_is_not_mostly_silent(final_path)
            if silence_notice:
                warnings.append(silence_notice)

            # Persist final video to Supabase Storage (signed URL) when available.
            if final_path and os.path.isfile(final_path):
                from tools.supabase_storage import upload_video

                job_id = os.path.basename(os.path.normpath(working_dir))
                stored = await upload_video(final_path, job_id)
                if stored and stored != final_path and stored.startswith("http"):
                    video_url = stored
                    # Delete local final file only after a successful remote upload.
                    try:
                        os.unlink(final_path)
                    except OSError:
                        pass
                    final_path = stored
                else:
                    # Fail-open: never expose a raw disk path to the client —
                    # serve via the authenticated streaming endpoint instead.
                    # (A bare "/tmp/..." URL becomes "https://host/tmp/..." and 404s.)
                    job_id = os.path.basename(os.path.normpath(working_dir))
                    video_url = video_url or f"/api/jobs/{job_id}/video"

        await progress(
            "complete",
            "Drama generation complete",
            100,
            {"video_path": final_path, "video_url": video_url},
        )

        return {
            "title": script.title,
            "logline": script.logline,
            "mood": script.mood,
            "video_path": final_path,
            "video_url": video_url,
            "scene_count": len(scene_results),
            "duration_estimate": (
                round(actual_duration_seconds)
                if actual_duration_seconds is not None
                else script.estimated_duration_seconds
            ),
            "characters": [c.model_dump() for c in characters],
            "portraits": portraits,
            "location_plate": location_plate,
            # Who ended up speaking with which voice, keyed by the character's
            # real name. Written out so a character SAVED to the library after
            # this drama carries the voice this drama gave them: without it the
            # first episode's casting is thrown away and episode two re-derives
            # it from a different ensemble (see VoiceGenerator.lock_voices).
            "character_voices": {
                c.name: character_voices[c.name.casefold()]
                for c in characters
                if c.name.casefold() in character_voices
            },
            "lipsynced_scenes": lipsynced_scenes,
            # Everything regenerate_scene() needs to re-render ONE scene the
            # same way it was rendered the first time. Underscore-prefixed
            # because it is machinery, not something the UI should render;
            # kept on the result (rather than on Job) so it survives the
            # Supabase round-trip that job rows already do.
            "_render_state": {
                "script": script.model_dump() if hasattr(script, "model_dump") else {},
                "scene_durations": list(scene_durations),
                "music_url": music_url,
                "user_requirement": user_requirement,
                "dialogue_tracks": dialogue_tracks,
                # Foley is generated once, per scene, and paid for once. A
                # re-cut or a retake that did not carry it forward would
                # silently deliver a quieter film than the one the customer
                # already has -- and would have no way to get it back without
                # re-generating every bed.
                "sfx_tracks": sfx_tracks,
            },
            "scenes": scene_results,
            "director_style": director_style,
            "style": style,
            "aspect_ratio": aspect_ratio,
            # Recorded rather than persisted on the job row: the drama's
            # language is a property of what was MADE, and the result already
            # survives the Supabase round-trip that a new jobs column would
            # have needed a migration for.
            "language": language,
            "narrative_mode": micro_drama.resolve_mode(narrative_mode),
            "demo": self.demo,
            "music_enabled": bool(music_url) if not self.demo else False,
            "dialogue_enabled": bool(dialogue_tracks) if not self.demo else False,
            "plan": plan,
            "setting_location": getattr(script, "setting_location", "") or "",
            "setting_time_of_day": getattr(script, "setting_time_of_day", "") or "",
            "setting_era": getattr(script, "setting_era", "") or "",
            # Lets the UI explain a generic result instead of leaving the
            # user to guess why their prompt was ignored.
            "script_degraded": getattr(script, "generated_by", "llm") == "template",
            # Anything that was ASKED for and quietly did not happen. Every
            # audio stage fails open (a dead voice provider must not bin a
            # finished picture), so without this the user's only evidence is a
            # video that is silent for no stated reason.
            "warnings": warnings,
        }

    async def run(
        self,
        idea: str,
        style: str = "Cinematic",
        director_style: str = "cinematic_balanced",
        user_requirement: str = "",
        num_scenes: int = 3,
        aspect_ratio: str = "16:9",
        working_dir: str = "/tmp/museforge_drama",
        progress_callback: Optional[Callable] = None,
        music_url: Optional[str] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        character_portraits_override: Optional[Dict[str, str]] = None,
        music_enabled: bool = False,
        dialogue_enabled: bool = False,
        lipsync_enabled: bool = False,
        plan: str = "free",
        preset_characters: Optional[List[Dict[str, Any]]] = None,
        location_image_override: Optional[str] = None,
        language: str = DEFAULT_LANGUAGE,
        narrative_mode: str = "",
    ) -> dict:
        """Full end-to-end run (script + production). Default path unchanged."""
        script = await self.write_script_only(
            idea=idea,
            style=style,
            num_scenes=num_scenes,
            user_requirement=user_requirement,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
            preset_characters=preset_characters,
            language=language,
            dialogue_enabled=dialogue_enabled,
            narrative_mode=narrative_mode,
        )
        return await self.continue_from_script(
            script=script,
            style=style,
            director_style=director_style,
            user_requirement=user_requirement,
            aspect_ratio=aspect_ratio,
            working_dir=working_dir,
            progress_callback=progress_callback,
            music_url=music_url,
            is_cancelled=is_cancelled,
            character_portraits_override=character_portraits_override,
            music_enabled=music_enabled,
            dialogue_enabled=dialogue_enabled,
            lipsync_enabled=lipsync_enabled,
            plan=plan,
            library_characters=preset_characters,
            location_image_override=location_image_override,
            language=language,
            narrative_mode=narrative_mode,
        )
