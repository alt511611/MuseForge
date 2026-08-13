"""Full idea-to-video orchestration pipeline."""

import asyncio
import logging
import os
import re
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional

from agents.screenwriter import ScreenwriterAgent, ScriptGenerationFailed
from interfaces.character import CharacterInScene, DramaScript
from interfaces.film_look import build_film_look_filters
from interfaces.language import DEFAULT_LANGUAGE
from interfaces.second_budget import billable_seconds, distribute_budget
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
    is_scene_transitions_enabled,
    moviepy_encode_kwargs,
    video_encode_args,
)
from tools.muapi_lipsync import is_lipsync_enabled, make_lipsync
from tools.muapi_voice_generator import MuAPIVoiceGenerator, is_dialogue_enabled

logger = logging.getLogger(__name__)


class SceneRegenerationUnavailable(Exception):
    """A single scene cannot be re-rendered for this job.

    Separate from a generation failure because nothing was attempted and
    nothing should be charged: the job predates scene archiving, or its clips
    have already been cleaned up. The API turns this into a 4xx explaining
    which, rather than a 500.
    """


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
                "loudnorm=I=-14:TP=-1.5:LRA=11"
            ),
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


async def add_background_music(
    video_path: str,
    output_path: str,
    music_url: Optional[str] = None,
    dialogue_tracks: Optional[List[Dict[str, Any]]] = None,
    scene_paths: Optional[List[str]] = None,
) -> str:
    """Mix music and timed dialogue once, with dialogue louder than music."""
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

        for track in dialogue_tracks:
            dialogue = None
            try:
                audio_url = track.get("audio_url")
                if not audio_url:
                    # Caption-only rows (ElevenLabs returns one combined file
                    # per scene; later lines carry text for SRT only).
                    continue
                scene_index = int(track.get("scene_index", 0))
                scene_start = (
                    scene_starts[scene_index]
                    if 0 <= scene_index < len(scene_starts)
                    else 0.0
                )
                local_start = line_offsets.get(scene_index, 0.0)
                dialogue = AudioFileClip(audio_url)
                available = (
                    scene_durations[scene_index] - local_start
                    if 0 <= scene_index < len(scene_durations)
                    else video.duration - scene_start - local_start
                )
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


def _scene_start_offsets(scene_paths: Optional[List[str]]) -> List[float]:
    """Absolute start time of each scene in the concatenated drama (seconds)."""
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
    return starts


def build_srt_from_dialogue_tracks(
    dialogue_tracks: List[Dict[str, Any]],
    scene_paths: Optional[List[str]] = None,
) -> str:
    """Build an SRT document from dialogue tracks.

    Timing mirrors ``add_background_music``: lines within a scene are laid
    out sequentially from that scene's start, with a short gap between lines.
    Tracks may optionally carry explicit ``start_seconds`` / ``end_seconds``
    (or ``duration_seconds``) for tests / pre-timed callers.
    """
    scene_starts = _scene_start_offsets(scene_paths)
    line_offsets: Dict[int, float] = {}
    blocks: List[str] = []
    index = 0

    for track in dialogue_tracks or []:
        line = str(track.get("line") or "").strip()
        if not line:
            continue
        character = str(track.get("character") or "").strip()
        text = f"{character}: {line}" if character else line

        if "start_seconds" in track:
            start = float(track["start_seconds"])
            if "end_seconds" in track:
                end = float(track["end_seconds"])
            else:
                duration = float(
                    track.get("duration_seconds")
                    or _probe_audio_duration_seconds(str(track.get("audio_url") or ""))
                    or _estimate_line_duration_seconds(line)
                )
                end = start + duration
        else:
            scene_index = int(track.get("scene_index", 0))
            scene_start = (
                scene_starts[scene_index]
                if 0 <= scene_index < len(scene_starts)
                else 0.0
            )
            local_start = line_offsets.get(scene_index, 0.0)
            start = scene_start + local_start
            duration = float(
                track.get("duration_seconds")
                or _probe_audio_duration_seconds(str(track.get("audio_url") or ""))
                or _estimate_line_duration_seconds(line)
            )
            end = start + duration
            line_offsets[scene_index] = local_start + duration + 0.2

        if end <= start:
            end = start + 1.0

        index += 1
        # SRT uses blank lines between cues; escape nothing special beyond
        # stripping carriage returns so a single cue stays one logical block.
        safe_text = text.replace("\r\n", "\n").replace("\r", "\n")
        blocks.append(
            f"{index}\n"
            f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n"
            f"{safe_text}\n"
        )

    return "\n".join(blocks)


def _escape_subtitles_filter_path(path: str) -> str:
    """Escape a filesystem path for ffmpeg's subtitles= filter."""
    # Prefer forward slashes; escape characters that break the filter grammar.
    escaped = os.path.abspath(path).replace("\\", "/")
    escaped = escaped.replace(":", "\\:").replace("'", "\\'")
    return escaped


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

        ffmpeg_binary = os.environ.get("MUSEFORGE_FFMPEG_BINARY") or shutil.which("ffmpeg")
        if not ffmpeg_binary:
            try:
                import imageio_ffmpeg

                ffmpeg_binary = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ffmpeg_binary = "ffmpeg"

        # White primary text, black outline, BorderStyle=3 = opaque box behind
        # text for readability on busy backgrounds.
        force_style = (
            "FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BorderStyle=3,Outline=1,Shadow=0,Alignment=2,MarginV=36"
        )
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
    ) -> List[int]:
        """Replace each speaking scene's clip with a lip-synced one, in place.

        Mutates ``scene_paths`` (the list concatenation reads from) and
        ``dialogue_tracks`` (the list the audio mixer reads from), and returns
        the scene indices that were successfully synced.

        Fail-open per scene, not per drama: if scene 2 cannot be synced, scenes
        1 and 3 still are, and scene 2 simply keeps its original clip with its
        voice mixed over the top exactly as before.
        """
        # `requested` is the per-job opt-in (the user paid for it);
        # is_lipsync_enabled() is the deployment flag. Both must hold.
        if self.demo or not requested or not is_lipsync_enabled() or not dialogue_tracks:
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

        synced: List[int] = []
        for position, (scene_index, audio_url) in enumerate(sorted(audio_by_scene.items())):
            if is_cancelled and is_cancelled():
                break
            await progress(
                "lipsync",
                f"Syncing lips to dialogue ({position + 1}/{len(audio_by_scene)})",
                88,
            )
            synced_url = await lipsync.sync(
                scene_paths[scene_index], audio_url, is_cancelled=is_cancelled
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
            if not _keeps_its_length(scene_paths[scene_index], local_path):
                # Sync Labs' own default trims the video down to the length of
                # the audio, which would let a short line silently shorten a
                # scene and break the fixed per-credit second budget the whole
                # costing model rests on. The fal backend pins sync_mode to
                # stop that; MuAPI's endpoint exposes no such knob, so the
                # guarantee is enforced here instead -- a clip that came back
                # short is discarded and the unsynced take kept.
                logger.warning(
                    "Lip-synced clip for scene %s came back shorter than the "
                    "take it replaces — keeping the original so the runtime "
                    "the customer paid for is preserved.",
                    scene_index,
                )
                continue
            scene_paths[scene_index] = local_path
            synced.append(scene_index)

        # Hand the speech over to the picture: drop the audio the mixer would
        # otherwise overlay, keep every row so subtitles are unaffected.
        for track in dialogue_tracks:
            if int(track.get("scene_index", -1)) in synced:
                audio_url = track.pop("audio_url", None)
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
            try:
                stored = await upload_video(local_path, f"{job_id}_scene_{scene['index']}")
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
            )

        final_path = await self._assemble_final_drama(
            scene_paths,
            working_dir,
            progress_callback,
            state.get("music_url"),
            previous_result.get("plan", "free"),
            is_cancelled=is_cancelled,
            dialogue_tracks=dialogue_tracks,
            director_style=previous_result.get("director_style", "cinematic_balanced"),
            transitions=plan_transitions([s["script"] for s in ordered]),
            aspect_ratio=previous_result.get("aspect_ratio", "16:9"),
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
        if dialogue_tracks:
            await add_background_music(
                graded_path,
                with_music_path,
                music_url,
                dialogue_tracks=dialogue_tracks,
                scene_paths=scene_paths,
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
        voice_gen = MuAPIVoiceGenerator(self.api_key, demo=self.demo) if dialogue_requested else None
        if voice_gen is not None:
            # Cast the whole ensemble up front, gender-matched to each
            # character's description -- otherwise the per-line hash fallback
            # can voice a mother with a male voice.
            voice_gen.cast_characters(characters)
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

            _check_cancel()
            failed_dialogue_scenes: List[int] = []
            dialogue_failure_reasons: List[str] = []
            for assembled_scene_index, scene_number, task, scene_lines in dialogue_tasks:
                try:
                    generated_tracks = await task
                    for track in generated_tracks:
                        dialogue_tracks.append(
                            {**track, "scene_index": assembled_scene_index}
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
        )
