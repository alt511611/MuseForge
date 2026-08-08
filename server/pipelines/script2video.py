"""Per-scene script-to-video pipeline."""

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence

import httpx

from agents.storyboard_artist import StoryboardArtist
from interfaces.camera import get_director_style
from interfaces.character import CharacterInScene
from interfaces.color_grade import get_color_grade
from interfaces.lighting import resolve_lighting
from tools.character_qa import (
    format_expected_setting,
    is_character_qa_enabled,
    verify_frame,
)
from tools.muapi_image_generator import MuAPIImageGenerator
from tools.muapi_video_generator import MuAPIVideoGenerator
from tools.muapi_client import MuAPICancelled

logger = logging.getLogger(__name__)


class PipelineCancelled(Exception):
    """Raised cooperatively when a job is cancelled mid-flight."""


def _make_video_generator(api_key: str, demo: bool):
    """Pick the video-generation backend. Defaults to the existing MuAPI
    path unchanged. Imported lazily so the default path never requires
    fal-client to be installed/importable.

    MUSEFORGE_VIDEO_PROVIDER:
      - "muapi" (default) — MuAPIVideoGenerator
      - "falai" — fal.ai Kling O3 Pro image-to-video
      - "falai_reference" — fal.ai Kling O3 Pro reference-to-video
        (one-step character-consistent video; skips separate frame gen)
    """
    provider = os.environ.get("MUSEFORGE_VIDEO_PROVIDER", "muapi")
    if provider == "falai":
        from tools.falai_video_generator import FalAIVideoGenerator

        return FalAIVideoGenerator(os.environ.get("FAL_KEY", ""), demo=demo)
    if provider == "falai_reference":
        from tools.falai_reference_video_generator import FalAIReferenceVideoGenerator

        return FalAIReferenceVideoGenerator(os.environ.get("FAL_KEY", ""), demo=demo)
    return MuAPIVideoGenerator(api_key, demo=demo)


def _make_image_generator(api_key: str, demo: bool):
    """Pick the image-generation backend. Defaults to MuAPI unchanged.
    MUSEFORGE_IMAGE_PROVIDER=falai opts into fal.ai FLUX (v1.1 text-to-image
    + flux-pro/kontext for reference). Lazy-imported.
    """
    provider = os.environ.get("MUSEFORGE_IMAGE_PROVIDER", "muapi")
    if provider == "falai":
        from tools.falai_image_generator import FalAIImageGenerator

        return FalAIImageGenerator(os.environ.get("FAL_KEY", ""), demo=demo)
    return MuAPIImageGenerator(api_key, demo=demo)


#: Craft/quality direction appended to every frame prompt.
#:
#: FLUX is a distilled, guidance-based model: it has no true classifier-free
#: guidance, so a `negative_prompt` field is either ignored or rejected
#: (a 422 would silently demote every frame to the fallback endpoint).
#: Quality is therefore steered POSITIVELY, naming the look we want rather
#: than listing artifacts to avoid. Anatomy is called out because hands and
#: eyes are where generated people break most visibly, and text because
#: spurious captions/watermarks are a common FLUX failure on cinematic prompts.
IMAGE_QUALITY_SUFFIX = (
    "Shot on 35mm film, natural filmic grain, realistic skin texture with "
    "visible pores, catchlights in the eyes, anatomically correct hands, "
    "sharp focus on the face with natural depth of field. "
    "No text, captions, subtitles, watermarks or logos anywhere in the frame."
)


def build_character_identity_clause(characters, matched_char=None) -> str:
    """Restate every on-screen character's fixed appearance in the prompt text.

    The reference image only ever binds ONE character's identity (both MuAPI
    PuLID and fal Kontext take a single reference URL), so in a two-hander
    every OTHER character was previously re-invented from scratch by the image
    model on every scene — the direct cause of "the mother and daughter look
    like different people in different scenes". Naming each character with
    their locked description gives the non-referenced ones a stable textual
    anchor across the whole drama.
    """
    visible = [c for c in (characters or []) if getattr(c, "is_visible", True)]
    described = []
    for c in visible:
        features = (getattr(c, "static_features", "") or "").strip()
        if not features:
            continue
        # Wardrobe is stated alongside the face: the reference image fixes
        # identity but not costume, so an unstated outfit drifts scene to scene.
        wardrobe = (getattr(c, "wardrobe", "") or "").strip()
        detail = f"{features}, wearing {wardrobe}" if wardrobe else features
        described.append(f"{c.name} ({detail})")
    if not described:
        return ""
    clause = (
        "Character appearance is FIXED for the entire story and must be "
        "IDENTICAL to previous scenes — same face, same age, same hair length, "
        "colour and style, same build: " + "; ".join(described) + ". "
    )
    # A character with no stated wardrobe is the outfit-drift case: the
    # reference image binds a face, not a costume, so with nothing said about
    # clothing the image model dresses them afresh every scene (observed in
    # the wild as one character appearing in three different outfits across a
    # three-scene drama). Pin the costume to the reference instead.
    if any(not (getattr(c, "wardrobe", "") or "").strip() for c in visible):
        clause += (
            "Clothing is also FIXED: every character wears the EXACT SAME "
            "outfit as in the reference image and in every other scene — same "
            "garment, same cut, same colour. Never change or restyle the "
            "costume between scenes. "
        )
    if matched_char is not None and getattr(matched_char, "name", ""):
        clause += (
            f"The attached reference image is {matched_char.name}; match that "
            f"face exactly. "
        )
    return clause


def build_screen_direction_clause(characters) -> str:
    """Deterministic 180°-rule axis for a two-hander, stated in the prompt.

    Scenes are storyboarded and rendered independently (and, by default, in
    parallel), so screen direction cannot be left to each scene's own
    judgement -- the axis is derived from character ORDER, which is identical
    for every scene of the drama: first visible character frame-left looking
    screen-right, second frame-right looking screen-left. Without this, shots
    of a conversation flip sides between scenes and the cut reads as two
    people facing away from each other. Only emitted for exactly two visible
    characters; singles have no axis to hold and ensembles need real blocking.
    """
    visible = [
        c
        for c in (characters or [])
        if getattr(c, "is_visible", True) and (getattr(c, "name", "") or "").strip()
    ]
    if len(visible) != 2:
        return ""
    left, right = visible[0].name, visible[1].name
    return (
        f"Screen direction (LOCKED for the entire story, 180-degree rule): "
        f"{left} is on frame-left facing screen-right; {right} is on "
        f"frame-right facing screen-left. Keep this orientation even when "
        f"only one of them is in frame — they look toward the other's side. "
        f"Never mirror or flip the composition. "
    )


def build_frame_prompt(
    style: str,
    shot,
    setting_location: str = "",
    setting_time_of_day: str = "",
    setting_era: str = "",
    has_dialogue: bool = False,
    lipsync_enabled: bool = False,
    characters=None,
    matched_char=None,
) -> str:
    """Build the image prompt for a shot, injecting locked setting when present.

    Empty setting fields (legacy/demo scripts) keep the old prompt shape —
    no bare "Setting: , ." fragment.

    The user's raw brief is deliberately NOT injected here. It reaches the
    storyboard artist instead (a text model that can reason about "three hard
    cuts", "24fps", "clean dry audio"); pasting it into an image prompt would
    only crowd out this shot's own description in a fixed token budget.
    """
    parts = [
        p.strip()
        for p in (setting_location, setting_time_of_day, setting_era)
        if (p or "").strip()
    ]
    if parts:
        # Prefer "location, time_of_day" when both exist (user-requested shape).
        setting_clause = (
            f"Setting: {', '.join(parts)}. This scene takes place in the "
            f"EXACT SAME physical location established in the story's opening "
            f"shot -- identical architecture, furniture, wall decor, and "
            f"lighting fixtures. Only the time-of-day lighting may shift "
            f"subtly per the story's setting_time_of_day; the room itself "
            f"must not change. "
        )
    else:
        setting_clause = ""
    # Only lit when the script actually establishes a setting. A legacy/demo
    # script that declares no location, hour or era at all keeps the exact
    # prompt shape it had before -- there is no continuity to protect across
    # scenes that were never placed anywhere.
    lighting_clause = resolve_lighting(setting_time_of_day).as_clause() if parts else ""
    # These two instructions are opposites, and which one is right depends
    # entirely on whether the mouth is about to be driven by a lip-sync pass.
    # Hiding the mouth was the correct dodge while dialogue was only ever
    # mixed OVER the picture -- a visible mouth saying nothing reads as a
    # dubbing error. With lip sync on, that same dodge destroys the feature:
    # a mouth in profile or out of frame is a mouth the sync model cannot
    # drive, so the scene is paid for and then silently unsynced.
    if not has_dialogue:
        dialogue_clause = ""
    elif lipsync_enabled:
        dialogue_clause = (
            "The speaking character's mouth is fully visible, unobscured and "
            "facing camera -- their lips will be animated to the dialogue. "
            "Do not hide the mouth behind hands, props, hair or profile. "
        )
    else:
        dialogue_clause = (
            "For this dialogue shot, the speaking character's mouth should be "
            "naturally obscured, shown in profile, or not be the focal point. "
        )
    # Emotion is stated explicitly (not left implicit in visual_desc) and
    # paired with a face-visibility requirement: flat, unreadable faces were
    # coming from both a missing expression instruction AND from frames
    # designed as backlit silhouettes where no expression could be seen.
    expression = (getattr(shot, "expression_desc", "") or "").strip().rstrip(".")
    if expression:
        expression_clause = (
            f"Facial expression and body language: {expression}. The emotion "
            f"must be clearly readable on the face. "
        )
    else:
        expression_clause = ""
    face_clause = (
        "The character's face is clearly visible and softly lit — not a "
        "silhouette, not backlit into shadow, not turned away from camera. "
    )
    identity_clause = build_character_identity_clause(characters, matched_char)
    direction_clause = build_screen_direction_clause(characters)
    # lighting_clause sits next to the setting clause because it makes the
    # same promise: the room does not change between shots, and neither does
    # the light in it.
    return (
        f"{style} style. {setting_clause}{lighting_clause}"
        f"{identity_clause}{direction_clause}"
        f"{shot.visual_desc}. "
        f"{expression_clause}{face_clause}"
        f"{dialogue_clause}Shot type: {shot.shot_type}. Lens: {shot.lens}. "
        f"{IMAGE_QUALITY_SUFFIX}"
    )


def build_motion_prompt(shot, matched_char=None) -> str:
    """Build the prompt sent to the video (image-to-video) model.

    Previously this was ``shot.motion_desc`` alone, which starved the
    animation step of everything else the storyboard decided: the designed
    camera move never reached Kling (it invented its own), and the acted
    expression wasn't carried, so a face could drift to neutral -- or to a
    different-looking person -- WITHIN a shot. Identity drift inside a shot
    happens in the video model, not the frame, so the character lock has to
    be restated here too.
    """
    parts = []
    camera = (getattr(shot, "camera_movement", "") or "").strip().rstrip(".")
    if camera:
        parts.append(f"Camera: {camera}.")
    motion = (getattr(shot, "motion_desc", "") or "").strip().rstrip(".")
    if motion:
        parts.append(f"{motion}.")
    expression = (getattr(shot, "expression_desc", "") or "").strip().rstrip(".")
    if expression:
        parts.append(
            f"The character's expression stays true to the beat: {expression}."
        )
    name = (getattr(matched_char, "name", "") or "").strip() if matched_char else ""
    subject = name or "each character"
    parts.append(
        f"Keep {subject}'s facial identity EXACTLY as in the source image "
        f"throughout the shot — no morphing, no face changes. "
        f"Preserve the source image's screen direction: characters keep "
        f"facing the same way, never mirror the composition. "
        f"Natural, subtle human motion; no warping or distortion."
    )
    return " ".join(parts)


async def download_video(url: str, path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
    return path


async def concatenate_videos(paths: List[str], out_path: str) -> str:
    """Concatenate clips with low-memory fallbacks.

    Fast path uses ffmpeg's concat demuxer and stream-copy, which does not
    decode frames. If the clips are not codec-compatible, moviepy re-encodes
    them with ``method="chain"``. Raw byte-copy remains the last-resort,
    fail-open behavior.
    """
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

    # 1) Native concat demuxer: near-zero memory because packets are copied
    # without decoding/re-encoding. This requires matching codecs/streams.
    concat_list_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            prefix="museforge_concat_",
            dir=os.path.dirname(out_path) or ".",
            delete=False,
            encoding="utf-8",
        ) as concat_file:
            concat_list_path = concat_file.name
            for path in paths:
                # ffmpeg concat-demuxer escaping for single quotes.
                escaped = os.path.abspath(path).replace("'", "'\\''")
                concat_file.write(f"file '{escaped}'\n")

        ffmpeg_binary = os.environ.get("MUSEFORGE_FFMPEG_BINARY") or shutil.which("ffmpeg")
        if not ffmpeg_binary:
            # Local dev/test environments may only have moviepy's bundled
            # imageio-ffmpeg binary; production Docker installs ffmpeg.
            try:
                import imageio_ffmpeg

                ffmpeg_binary = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ffmpeg_binary = "ffmpeg"

        process = await asyncio.create_subprocess_exec(
            ffmpeg_binary,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list_path,
            "-c",
            "copy",
            "-an",
            out_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
        if process.returncode == 0 and os.path.isfile(out_path):
            return out_path
        logger.warning(
            "ffmpeg concat stream-copy failed (exit=%s), using moviepy chain: %s",
            process.returncode,
            stderr.decode("utf-8", errors="replace")[-1000:],
        )
    except Exception as exc:
        logger.warning("ffmpeg concat unavailable, using moviepy chain: %s", exc)
    finally:
        if concat_list_path:
            try:
                os.unlink(concat_list_path)
            except OSError:
                pass

    # Remove a partial ffmpeg output before either fallback writes it.
    try:
        os.unlink(out_path)
    except OSError:
        pass

    # 2) Re-encode fallback. All generated clips share dimensions/aspect ratio,
    # so chain avoids compose's memory-heavy canvas/compositing behavior.
    clips = []
    final = None
    try:
        from moviepy import VideoFileClip, concatenate_videoclips

        clips = [VideoFileClip(p) for p in paths]
        final = concatenate_videoclips(clips, method="chain")
        final.write_videofile(
            out_path, codec="libx264", audio=False, logger=None,
            **moviepy_encode_kwargs(),
        )
        return out_path
    except Exception as exc:
        logger.warning("moviepy chain concat failed, using raw byte-copy: %s", exc)
    finally:
        if final is not None:
            try:
                final.close()
            except Exception:
                pass
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

    # 3) Preserve the existing last-resort raw byte-copy fallback.
    try:
        with open(out_path, "wb") as f:
            for p in paths:
                with open(p, "rb") as src:
                    f.write(src.read())
    except Exception as exc:
        # Keep the pipeline fail-open even if a source disappears mid-copy.
        logger.error("raw concat fallback failed: %s", exc)
    return out_path


# --- Encode quality ---------------------------------------------------------
#
# A finished drama is re-encoded several times on its way out: colour grade,
# audio mix, caption burn, watermark, aspect export. Every one of those passes
# used bare `libx264` with no rate control, which means ffmpeg's default CRF 23
# -- and the loss COMPOUNDS, so the last pass is encoding an already-degraded
# picture. CRF 18 is close to visually lossless and keeps generational loss
# negligible across the chain at a modest size cost on clips this short.
DEFAULT_VIDEO_CRF = "18"
#: x264 speed/efficiency tradeoff. "medium" is x264's own default; CRF governs
#: quality far more than preset does, so this stays fast by default.
DEFAULT_VIDEO_PRESET = "medium"
#: 4:2:0 8-bit. Sources can arrive as yuv444p/yuv422p, which Safari and most
#: hardware decoders refuse to play -- an unplayable video is the worst
#: possible "quality" outcome, so every output is normalised.
VIDEO_PIX_FMT = "yuv420p"


def video_encode_args() -> List[str]:
    """ffmpeg output args shared by every re-encode in the pipeline.

    ``-movflags +faststart`` moves the moov atom to the front so the browser
    player can start the video before the whole file has downloaded.
    """
    return [
        "-c:v",
        "libx264",
        "-crf",
        os.environ.get("MUSEFORGE_VIDEO_CRF", DEFAULT_VIDEO_CRF),
        "-preset",
        os.environ.get("MUSEFORGE_VIDEO_PRESET", DEFAULT_VIDEO_PRESET),
        "-pix_fmt",
        VIDEO_PIX_FMT,
        "-movflags",
        "+faststart",
    ]


def moviepy_encode_kwargs() -> Dict[str, Any]:
    """The same settings for moviepy's ``write_videofile``.

    moviepy takes ``preset`` as its own argument and passes the rest through
    ``ffmpeg_params``; duplicating -preset in both places makes ffmpeg error.
    """
    args = video_encode_args()
    preset = args[args.index("-preset") + 1]
    passthrough: List[str] = []
    skip_next = False
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg in ("-c:v", "-preset"):
            skip_next = True
            continue
        passthrough.append(arg)
    return {"preset": preset, "ffmpeg_params": passthrough}


def is_dynamic_reference_enabled() -> bool:
    """Opt-in flag for chaining each character's identity reference forward
    to their most recently generated frame (ViMax "previous timeline").

    OFF by default. Chaining preserves short-range outfit/pose continuity,
    but each generated frame is only an APPROXIMATION of its reference, so
    feeding frame N in as the reference for frame N+1 lets identity error
    compound scene over scene -- a random walk away from the original face.
    That is what produced the reported "the mother and daughter look like
    different people in different scenes", and it silently defeats the
    product's headline "locked portrait, reused everywhere" guarantee.
    Anchoring every scene to the locked portrait instead bounds the error.
    """
    return os.environ.get("MUSEFORGE_DYNAMIC_REFERENCE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def is_scene_transitions_enabled() -> bool:
    """Opt-in flag for crossfade transitions between scenes. Off by
    default: moviepy's "compose" method (required to overlap/blend
    adjacent clips) decodes and holds more in memory than the default
    ffmpeg stream-copy / "chain" paths in concatenate_videos() -- exactly
    the OOM risk that function's fallback ladder was built to avoid."""
    return os.environ.get("MUSEFORGE_SCENE_TRANSITIONS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def concatenate_videos_with_transitions(
    paths: List[str], out_path: str, transition_duration: float = 0.5,
    transitions: Optional[Sequence[float]] = None,
) -> str:
    """Concatenate clips, dissolving only at the boundaries that earn it.

    ``transitions`` gives one overlap duration per boundary (see
    interfaces/transitions.plan_transitions); 0.0 means a straight cut, which
    is film's default. When it is omitted the old behaviour applies -- the
    same ``transition_duration`` at every boundary.

    A plan of all cuts needs no compositing at all, so it hands straight back
    to the cheap ffmpeg stream-copy path rather than paying the memory cost of
    moviepy's "compose" mode for nothing.

    Fails open to plain concatenate_videos() on ANY error, so a bad transition
    render never blocks the job.
    """
    if len(paths) < 2:
        return await concatenate_videos(paths, out_path)

    if transitions is None:
        overlaps = [float(transition_duration)] * (len(paths) - 1)
    else:
        overlaps = [max(0.0, float(t)) for t in transitions][: len(paths) - 1]
        overlaps += [0.0] * (len(paths) - 1 - len(overlaps))

    if not any(overlaps):
        return await concatenate_videos(paths, out_path)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    clips = []
    faded_clips = []
    final = None
    try:
        from moviepy import VideoFileClip, concatenate_videoclips
        from moviepy.video.fx import CrossFadeIn, CrossFadeOut

        from moviepy import CompositeVideoClip

        clips = [VideoFileClip(p) for p in paths]
        # Per-boundary overlaps rule out concatenate_videoclips(padding=...),
        # which takes ONE padding value for the whole sequence. The timeline
        # is laid out explicitly instead: each clip starts where the previous
        # one ends, pulled back by however much this particular boundary
        # overlaps.
        starts = [0.0]
        for idx, clip in enumerate(clips[:-1]):
            starts.append(starts[idx] + float(clip.duration or 0) - overlaps[idx])

        for idx, clip in enumerate(clips):
            faded = clip
            # Fade in only where the boundary BEFORE this clip dissolves, and
            # out only where the boundary after it does — fading at a hard cut
            # would dip to black on a join that is meant to be invisible.
            if idx > 0 and overlaps[idx - 1] > 0:
                faded = faded.with_effects([CrossFadeIn(overlaps[idx - 1])])
            if idx < len(clips) - 1 and overlaps[idx] > 0:
                faded = faded.with_effects([CrossFadeOut(overlaps[idx])])
            faded_clips.append(faded.with_start(starts[idx]))

        final = CompositeVideoClip(faded_clips, size=clips[0].size)
        final.write_videofile(
            out_path, codec="libx264", audio=False, logger=None,
            **moviepy_encode_kwargs(),
        )
        return out_path
    except Exception as exc:
        logger.warning(
            "Crossfade transition concat failed, falling back to plain concat: %s", exc
        )
    finally:
        if final is not None:
            try:
                final.close()
            except Exception:
                pass
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

    try:
        os.unlink(out_path)
    except OSError:
        pass
    return await concatenate_videos(paths, out_path)


def _grade_strength(preset_strength: float) -> float:
    """Resolve grade blend strength in [0, 1].

    Each ColorGrade preset carries a strength tuned to how aggressive its own
    chain is. MUSEFORGE_GRADE_STRENGTH overrides that globally when an
    operator wants to dial the whole product's look up or down.

    Fails open to the preset value on anything unparseable rather than letting
    a typo'd env var break rendering.
    """
    raw = os.environ.get("MUSEFORGE_GRADE_STRENGTH", "").strip()
    if not raw:
        return max(0.0, min(1.0, preset_strength))
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        logger.warning(
            "Invalid MUSEFORGE_GRADE_STRENGTH=%r, using preset strength %s",
            raw,
            preset_strength,
        )
        return max(0.0, min(1.0, preset_strength))


def build_grade_filter_chain(grade) -> str:
    """Render a ColorGrade into the ffmpeg -vf chain that applies it.

    Below full strength the graded image is blended back over the ungraded
    original so the look never fully overwrites skin tones and facial detail.
    """
    strength = _grade_strength(grade.strength)
    if strength >= 0.999:
        return grade.filter_chain
    # ffmpeg's blend takes the FIRST input as the top layer, and all_opacity
    # is the weight of that top layer:
    #     result = opacity * top + (1 - opacity) * bottom
    # Here top is the UNGRADED stream, so the opacity that keeps `strength`
    # worth of grade is (1 - strength) -- not `strength`.
    ungraded_opacity = 1.0 - strength
    return (
        "split[grade_a][grade_b];"
        f"[grade_a]{grade.filter_chain}[graded];"
        f"[grade_b][graded]blend=all_mode=normal:all_opacity={ungraded_opacity:.3f}"
    )


async def apply_color_grade(
    video_path: str, output_path: str, director_style: str = "cinematic_balanced"
) -> str:
    """Color-grade the drama according to its DIRECTOR STYLE -- pure ffmpeg,
    no extra API calls or cost.

    Each DirectorStyle names a grade (DirectorStyle.color_grade); that name
    resolves to a ColorGrade preset with its own filter chain and strength.
    Noir Mystery therefore finishes monochrome, Anime Expressive finishes
    vivid, and Slow Cinematic gets the desaturated teal-and-orange look --
    instead of every style receiving one hardcoded cross-process grade.

    Fails open: if the filter chain errors (e.g. unsupported build of
    ffmpeg), the original video is copied through ungraded rather than
    failing the job, matching add_watermark()/add_background_music()'s
    existing fallback pattern.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    def _copy_through() -> str:
        if os.path.abspath(video_path) != os.path.abspath(output_path):
            with open(video_path, "rb") as src:
                data = src.read()
            with open(output_path, "wb") as dst:
                dst.write(data)
        return output_path

    grade = get_color_grade(get_director_style(director_style).color_grade)
    filter_chain = build_grade_filter_chain(grade)
    logger.info(
        "Color grading with %r (%s) for director style %r",
        grade.label,
        grade.filter_chain,
        director_style,
    )

    ffmpeg_binary = os.environ.get("MUSEFORGE_FFMPEG_BINARY") or shutil.which("ffmpeg")
    if not ffmpeg_binary:
        try:
            import imageio_ffmpeg

            ffmpeg_binary = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg_binary = "ffmpeg"

    try:
        process = await asyncio.create_subprocess_exec(
            ffmpeg_binary,
            "-y",
            "-i",
            video_path,
            "-vf",
            filter_chain,
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
            "Color grade ffmpeg filter failed (exit=%s), shipping ungraded video: %s",
            process.returncode,
            stderr.decode("utf-8", errors="replace")[-1000:],
        )
    except Exception as exc:
        logger.warning("Color grade unavailable, shipping ungraded video: %s", exc)

    try:
        os.unlink(output_path)
    except OSError:
        pass
    return _copy_through()


class Script2VideoPipeline:
    def __init__(self, api_key: str, demo: bool = False):
        self.api_key = api_key
        self.demo = demo
        self.image_gen = _make_image_generator(api_key, demo)
        self.video_gen = _make_video_generator(api_key, demo)
        self.storyboard_artist = StoryboardArtist(demo=demo)

    async def run(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: str = "",
        style: str = "Cinematic",
        working_dir: str = "/tmp/museforge_scene",
        progress_callback: Optional[Callable] = None,
        scene_idx: int = 0,
        total_scenes: int = 1,
        character_portraits: Optional[Dict[str, str]] = None,
        director_style: str = "cinematic_balanced",
        aspect_ratio: str = "16:9",
        is_cancelled: Optional[Callable[[], bool]] = None,
        plan: str = "free",
        setting_location: str = "",
        setting_time_of_day: str = "",
        setting_era: str = "",
        location_plate_url: Optional[str] = None,
        has_dialogue: bool = False,
        lipsync_enabled: bool = False,
        last_frame_by_character: Optional[Dict[str, str]] = None,
        scene_emotion: str = "",
        scene_dialogue: str = "",
        scene_direction: str = "",
        scene_tension: int = 0,
        scene_duration: float = 0.0,
        character_direction: str = "",
        theme: str = "",
        visual_motif: str = "",
        user_brief: str = "",
    ) -> Dict[str, Any]:
        os.makedirs(working_dir, exist_ok=True)
        portraits = character_portraits or {}
        # Shared, mutable across scenes (owned by the caller) so a later
        # scene can reference an earlier scene's generated frame instead of
        # only ever the locked portrait. A fresh dict when the caller
        # doesn't pass one keeps single-scene callers/tests unaffected.
        if last_frame_by_character is None:
            last_frame_by_character = {}
        # Snapshot taken BEFORE this scene's shots start, not read live --
        # shots within the same scene run concurrently, so reading the live
        # dict mid-scene would let a sibling shot's just-finished frame leak
        # in as a reference for a character that otherwise never had one
        # (e.g. no locked portrait at all), which is a within-scene change,
        # not the intended "next scene builds on the previous one" effect.
        # Each new scene call gets a fresh snapshot of whatever the dict
        # looked like once the PREVIOUS scene fully finished.
        reference_snapshot = dict(last_frame_by_character)

        def _check_cancel():
            if is_cancelled and is_cancelled():
                raise PipelineCancelled("Job cancelled")

        async def progress(stage: str, message: str, pct: float, data=None):
            if progress_callback:
                await progress_callback(stage, message, pct, data)

        _check_cancel()
        await progress("storyboard", f"Designing storyboard for scene {scene_idx + 1}", 10)
        shots = await self.storyboard_artist.design_storyboard(
            script,
            characters,
            user_requirement,
            director_style,
            setting_location=setting_location,
            setting_time_of_day=setting_time_of_day,
            setting_era=setting_era,
            is_finale=(scene_idx == total_scenes - 1),
            scene_emotion=scene_emotion,
            scene_dialogue=scene_dialogue,
            scene_direction=scene_direction,
            scene_tension=scene_tension,
            scene_duration=scene_duration,
            character_direction=character_direction,
            theme=theme,
            visual_motif=visual_motif,
            user_brief=user_brief,
        )

        shot_videos: List[Optional[str]] = [None] * len(shots)
        shot_meta: List[Optional[Dict[str, Any]]] = [None] * len(shots)
        completed_count = 0
        progress_lock = asyncio.Lock()

        # Frame + video generation for each shot are independent of every
        # OTHER shot (only frame->video within the same shot is
        # sequential) -- run shots concurrently instead of one-at-a-time.
        # Kling video generation alone can take 1-3+ minutes; 3 shots done
        # sequentially could take 10-15 minutes, while running them
        # concurrently caps wall-clock time near the slowest single shot.
        # Semaphore caps concurrent MuAPI requests so a multi-shot scene
        # doesn't fire a burst of simultaneous calls at the provider.
        semaphore = asyncio.Semaphore(int(os.environ.get("MUSEFORGE_SHOT_CONCURRENCY", "2")))
        qa_enabled = is_character_qa_enabled() and not self.demo
        dynamic_reference_enabled = is_dynamic_reference_enabled()
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
        expected_setting = format_expected_setting(
            setting_location, setting_time_of_day, setting_era
        )

        async def _process_shot(i: int, shot) -> None:
            nonlocal completed_count
            async with semaphore:
                qa_result: Dict[str, Any] = {}
                try:
                    _check_cancel()

                    reference_url = None
                    matched_char = None
                    shot_text = f"{shot.visual_desc} {shot.motion_desc}".lower()
                    visible_chars = [c for c in characters if c.is_visible]

                    # Found via a real report of character-swap between
                    # scenes: previously this ALWAYS used visible_chars[0]
                    # (the first character in the list) as the reference
                    # portrait for every single shot, regardless of which
                    # character the shot's own text actually describes.
                    # Now: pick whichever known character's name appears
                    # FIRST (by text position, i.e. narrative order --
                    # "Sam looks at Maria" -> Sam is the subject) in this
                    # shot's own visual_desc/motion_desc.
                    named_matches = [
                        (shot_text.find(c.name.lower()), c)
                        for c in visible_chars
                        if c.name.lower() in shot_text
                    ]
                    if named_matches:
                        named_matches.sort(key=lambda pair: pair[0])
                        matched_char = named_matches[0][1]
                    elif location_plate_url:
                        # No character name appears in this shot's text at all
                        # -- an establishing shot, an insert, an object. The
                        # old fallback handed it visible_chars[0]'s PORTRAIT,
                        # which is the wrong anchor twice over: it pushes a
                        # face into a shot the storyboard deliberately wrote
                        # without one, and it leaves the room itself
                        # re-invented from the text every time. The locked set
                        # plate is the right reference for exactly these shots.
                        reference_url = location_plate_url
                    elif visible_chars:
                        # No plate available (no location in the script, or
                        # plate generation failed) -- keep the original
                        # first-visible-character fallback rather than
                        # dropping to an unreferenced frame.
                        matched_char = visible_chars[0]

                    if matched_char:
                        # Default: always anchor to the character's LOCKED
                        # portrait, so identity error stays bounded instead
                        # of compounding across scenes (see
                        # is_dynamic_reference_enabled). Opting in restores
                        # the previous chain-forward behavior, where the most
                        # recently generated frame wins -- only populated from
                        # the second shot/scene onward, so the very first
                        # reference for any character is the portrait either way.
                        locked_portrait = portraits.get(matched_char.name)
                        if dynamic_reference_enabled:
                            dynamic_reference = reference_snapshot.get(matched_char.name)
                            reference_url = dynamic_reference or locked_portrait
                        else:
                            reference_url = locked_portrait or reference_snapshot.get(
                                matched_char.name
                            )

                    # Belt-and-braces: design_storyboard already repairs a
                    # missing/neutral expression, but the frame prompt is the
                    # thing that actually decides whether the scene reads as
                    # emotional, so the guarantee is re-applied at the point
                    # of use -- it also covers shots that reached here from
                    # any other path.
                    StoryboardArtist._ensure_expression([shot], scene_emotion)

                    frame_prompt = build_frame_prompt(
                        style,
                        shot,
                        setting_location=setting_location,
                        setting_time_of_day=setting_time_of_day,
                        setting_era=setting_era,
                        has_dialogue=has_dialogue,
                        lipsync_enabled=lipsync_enabled,
                        characters=characters,
                        matched_char=matched_char,
                    )

                    # fal.ai reference-to-video binds character identity in a
                    # SINGLE call (elements + prompt), so the separate
                    # PuLID/Kontext frame step is skipped when that provider
                    # is selected AND we have a character reference.
                    # Requires a matched CHARACTER, not just any reference: the
                    # fal.ai path binds the reference as a character element,
                    # so feeding it the empty location plate would ask the
                    # model to cast a room as the person in the shot.
                    one_step_reference_video = (
                        getattr(self.video_gen, "uses_character_reference_to_video", False)
                        and bool(matched_char)
                        and bool(reference_url)
                    )

                    async with progress_lock:
                        await progress(
                            "frames" if not one_step_reference_video else "video",
                            (
                                f"Generating frame {i + 1}/{len(shots)}"
                                if not one_step_reference_video
                                else f"Reference-to-video shot {i + 1}/{len(shots)}"
                            ),
                            20 + i * 5,
                        )

                    char_desc = matched_char.static_features if matched_char else ""
                    qa_result = {"character_ok": True, "setting_ok": True}
                    frame_url = None

                    if one_step_reference_video:
                        # Portrait (or last dynamic frame) is the element
                        # reference; motion/visual become the video prompt.
                        # Store the reference as frame_url for meta/downstream
                        # dynamic-reference chaining.
                        frame_url = reference_url
                        shot.frame_url = frame_url
                        video_prompt = (
                            f"{frame_prompt} "
                            f"{build_motion_prompt(shot, matched_char)}"
                        )
                    else:
                        # Frame generation + optional QA happen BEFORE video
                        # animation (the expensive, slow step) so a rejected
                        # frame is retried without wasting money on animating
                        # a frame we're about to throw away.
                        if reference_url:
                            frame_url = await self.image_gen.generate_image_with_reference(
                                frame_prompt, reference_url, aspect_ratio, is_cancelled=is_cancelled
                            )
                        else:
                            frame_url = await self.image_gen.generate_image(
                                frame_prompt, aspect_ratio, is_cancelled=is_cancelled
                            )

                        shot.frame_url = frame_url

                        # Audit & targeted repair (adapted from Virginia Tech's
                        # "Audit & Repair" technique): on QA failure, fix the
                        # SPECIFIC reported issue with ONE corrective re-send
                        # rather than blindly regenerating the whole frame from
                        # scratch repeatedly. Only character-referenced shots can
                        # be repaired this way (flux-pulid needs the reference
                        # image); a single repair attempt, fail-open throughout.
                        if qa_enabled and frame_url and anthropic_key:
                            _check_cancel()
                            qa_result = await verify_frame(
                                frame_url=frame_url,
                                expected_character_desc=char_desc,
                                expected_setting=expected_setting,
                                anthropic_api_key=anthropic_key,
                            )
                            qa_failed = not qa_result.get(
                                "character_ok", True
                            ) or not qa_result.get("setting_ok", True)
                            issue = (qa_result.get("issue") or "").strip()
                            if qa_failed and reference_url and issue:
                                _check_cancel()
                                repair_prompt = (
                                    f"{frame_prompt} IMPORTANT CORRECTION: {issue}"
                                )
                                try:
                                    frame_url = await self.image_gen.generate_image_with_reference(
                                        repair_prompt,
                                        reference_url,
                                        aspect_ratio,
                                        is_cancelled=is_cancelled,
                                    )
                                    shot.frame_url = frame_url
                                except Exception as exc:
                                    # Fail-open: keep the original (flagged) frame
                                    # rather than blocking the shot on a failed
                                    # repair attempt.
                                    logger.warning(
                                        "QA repair regeneration failed for shot %s, "
                                        "keeping original frame: %s",
                                        i,
                                        exc,
                                    )
                        video_prompt = build_motion_prompt(shot, matched_char)

                    # Record this shot's final frame (post-repair, if any)
                    # as the new "most recent" reference for its character
                    # -- the NEXT shot/scene featuring them will prefer this
                    # over the original locked portrait.
                    if matched_char and frame_url:
                        last_frame_by_character[matched_char.name] = frame_url

                    _check_cancel()
                    async with progress_lock:
                        await progress("video", f"Animating shot {i + 1}/{len(shots)}", 50 + i * 5)

                    video_url = await self.video_gen.generate_video_from_image(
                        prompt=video_prompt,
                        image_url=frame_url if not one_step_reference_video else reference_url,
                        duration=int(getattr(shot, "duration_seconds", 5.0)),
                        aspect_ratio=aspect_ratio,
                        plan=plan,
                        is_cancelled=is_cancelled,
                    )
                except MuAPICancelled as exc:
                    # Translate the low-level "stopped polling mid-wait"
                    # signal into the pipeline-level cancellation exception
                    # that jobs.py already knows how to handle cleanly (as
                    # a clean "cancelled" job state, not a generic error).
                    raise PipelineCancelled(str(exc)) from exc
                shot.video_url = video_url
                meta = shot.model_dump() if hasattr(shot, "model_dump") else dict(vars(shot))
                # Record which character was actually used as the reference
                # for this shot -- lets a future "inconsistency" report be
                # diagnosed from real data (was the wrong character matched,
                # or did MuAPI itself drift?) instead of guessing blind.
                meta["reference_character"] = matched_char.name if matched_char else None
                # Which lock actually anchored this shot. Without it, a
                # "the room keeps changing" report cannot be told apart from
                # "the wrong character was matched" after the fact.
                meta["reference_kind"] = (
                    "character"
                    if matched_char
                    else ("location" if reference_url else None)
                )

                # QA/repair already ran above (before video generation) so a
                # detected issue could actually be fixed in the frame that
                # gets animated, instead of just reported after the fact.
                # Final QA outcome after all retry attempts (fail-open:
                # we always proceed with whichever frame we ended up with,
                # even if QA never passed -- this NEVER fails the job,
                # it only flags the shot for visibility).
                if qa_enabled and frame_url and anthropic_key and qa_result:
                    if not qa_result.get("character_ok", True):
                        meta["character_qa_warning"] = True
                    if not qa_result.get("setting_ok", True):
                        meta["setting_qa_warning"] = True
                    if qa_result.get("issue"):
                        meta["qa_issue"] = qa_result["issue"]

                shot_meta[i] = meta

                if not self.demo:
                    local_path = os.path.join(working_dir, f"shot_{i}.mp4")
                    await download_video(video_url, local_path)
                    shot_videos[i] = local_path

                async with progress_lock:
                    completed_count += 1
                    await progress(
                        "video",
                        f"Completed shot {completed_count}/{len(shots)}",
                        50 + int(completed_count / len(shots) * 40),
                    )

        await asyncio.gather(*[_process_shot(i, shot) for i, shot in enumerate(shots)])

        shot_meta = [m for m in shot_meta if m is not None]
        shot_videos = [v for v in shot_videos if v is not None]

        primary_url = shot_meta[-1]["video_url"] if shot_meta else None

        if self.demo:
            await progress(
                "scene_complete", f"Scene {scene_idx + 1} complete", 100, {"url": primary_url}
            )
            return {"path": None, "url": primary_url, "shots": shot_meta}

        output_path = os.path.join(working_dir, "scene_output.mp4")
        if len(shot_videos) == 1:
            output_path = shot_videos[0]
        elif len(shot_videos) > 1:
            await concatenate_videos(shot_videos, output_path)

        await progress("scene_complete", f"Scene {scene_idx + 1} complete", 100, {"path": output_path})
        return {"path": output_path, "url": primary_url, "shots": shot_meta}
