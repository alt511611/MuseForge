"""Per-scene script-to-video pipeline."""

import asyncio
import logging
import os
import shutil
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import httpx

from agents.storyboard_artist import StoryboardArtist
from interfaces.camera import get_director_style
from interfaces.character import CharacterInScene
from interfaces.color_grade import get_color_grade
from interfaces.lighting import resolve_lighting
from interfaces.visual_style import PHOTOREAL_RENDER
from interfaces.visual_style import resolve as resolve_visual_style
from tools.character_qa import (
    format_expected_setting,
    is_character_qa_enabled,
    verify_frame,
)
from tools.muapi_image_generator import MuAPIImageGenerator
from tools.muapi_video_generator import MuAPIVideoGenerator
from tools.muapi_client import MuAPICancelled
from tools.video_model_router import classify_shot

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
#:
#: It is also per-STYLE, because one shared suffix cannot serve eight looks:
#: asking for "Anime style" and then for "realistic skin texture with visible
#: pores" in the same prompt is an instruction to undo the style in the same
#: breath as requesting it. Every photoreal style still gets this exact text
#: (see interfaces/visual_style.PHOTOREAL_RENDER) — the name is kept as an
#: alias so nothing that already imports it moves.
IMAGE_QUALITY_SUFFIX = PHOTOREAL_RENDER

#: MuAPI rejects a `positivePrompt` outside 2..3000 characters with a 400 --
#: and it does so at GENERATION time, not on submit, so the job burns the
#: submit round trip and dies mid-render with an opaque provider error.
#:
#: This bites precisely when the product is working properly: a real script
#: names several characters with described faces AND wardrobe, and every one
#: of them is restated in the identity clause of every frame. Three or four
#: richly described characters clear 3000 characters on their own. It went
#: unnoticed while the screenwriter was failing to the deterministic template,
#: whose one undescribed "Alex" produced a short prompt every time.
MAX_IMAGE_PROMPT_CHARS = 3000


def fit_image_prompt(segments: list, limit: int = MAX_IMAGE_PROMPT_CHARS) -> str:
    """Assemble a prompt that respects the provider's character budget.

    `segments` is a list of `(priority, text)` in the order they should READ.
    Priority 0 is required; higher numbers are dropped first. Order and
    priority are deliberately separate: an image model weights the opening of
    the prompt, so "Cinematic style. Maya walks the pier." has to stay at the
    front even though the quality suffix that trails it is the first thing
    worth losing.

    Dropping whole clauses by priority beats a blind truncation, which would
    cut mid-word and could sever the character lock -- the frame would still
    render, just of somebody else.
    """
    kept = [(prio, text) for prio, text in segments if text]
    while sum(len(t) for _, t in kept) > limit:
        droppable = [p for p, _ in kept if p > 0]
        if not droppable:
            break
        worst = max(droppable)
        idx = next(i for i, (p, _) in enumerate(kept) if p == worst)
        _, dropped = kept.pop(idx)
        logger.warning(
            "Frame prompt over %d chars — dropping %d chars of lower-priority "
            "direction (%.60s...)", limit, len(dropped), dropped,
        )
    prompt = "".join(t for _, t in kept)
    if len(prompt) > limit:
        # Even the required segments are too long: a single enormous
        # visual_desc. Cut on a word boundary so it doesn't end mid-token.
        logger.warning(
            "Frame prompt still over %d chars after dropping every optional "
            "clause (%d) — truncating.", limit, len(prompt),
        )
        prompt = prompt[:limit].rsplit(" ", 1)[0]
    return prompt


def _describe_characters(visible, limit=None) -> list:
    """One "Name (looks)" entry per visible character, compacted to fit.

    Three levels, applied only as far as needed: full detail; drop wardrobe
    (the global "clothing is FIXED" sentence still covers costume drift);
    then trim each description to its opening clauses, which is where a face
    is actually described.
    """

    def render(with_wardrobe=True, feature_chars=None):
        out = []
        for c in visible:
            features = (getattr(c, "static_features", "") or "").strip()
            if not features:
                continue
            if feature_chars and len(features) > feature_chars:
                features = features[:feature_chars].rsplit(",", 1)[0].rstrip(" ,")
            # Wardrobe is stated alongside the face: the reference image
            # fixes identity but not costume, so an unstated outfit drifts
            # scene to scene.
            wardrobe = (getattr(c, "wardrobe", "") or "").strip() if with_wardrobe else ""
            detail = f"{features}, wearing {wardrobe}" if wardrobe else features
            out.append(f"{c.name} ({detail})")
        return out

    described = render()
    if limit is None:
        return described

    for attempt in (
        lambda: render(with_wardrobe=False),
        lambda: render(with_wardrobe=False, feature_chars=90),
        lambda: render(with_wardrobe=False, feature_chars=45),
    ):
        if sum(len(d) + 2 for d in described) <= limit:
            break
        described = attempt()
    return described


#: The fixed sentences build_character_identity_clause wraps around the
#: per-character descriptions. Named separately because their combined length
#: is the reserve build_frame_prompt has to hold back for them: while it was a
#: hand-tuned constant, every sentence added here silently ate into the
#: SETTING's share of the budget, and one addition finally pushed the setting
#: clause out of a crowded prompt altogether — the one clause that promises
#: the room does not change between scenes.
_APPEARANCE_LOCK = (
    "Character appearance is FIXED for the entire story and must be "
    "IDENTICAL to previous scenes — same face, same age, same hair length, "
    "colour and style, same build: "
)
_COSTUME_LOCK_NAMED = (
    "Costume is LOCKED for the whole story: each character wears only "
    "the outfit named above, in every scene — same garment, same cut, "
    "same colour, never restyled, swapped or changed. "
)
_COSTUME_LOCK_REFERENCED = (
    "Clothing is also FIXED: every character wears the EXACT SAME "
    "outfit as in the reference image and in every other scene — same "
    "garment, same cut, same colour. Never change or restyle the "
    "costume between scenes. "
)
# The costume lock above only forbids CHANGING what was named. Adding
# something that was never named slips straight past it -- and an
# occupational setting invites exactly that: a harbour drama came back with
# the same worker in a beanie, then an orange hard hat, then a black one,
# because "docks" reads to an image model as "put a helmet on him" and no
# sentence in the prompt said otherwise. Headwear is called out by name
# because it sits on the face, so a hat that appears and disappears reads as
# a different person even when the face is held.
_NO_UNNAMED_ITEMS = (
    "Wear NOTHING that is not named above: no hat, cap, beanie, helmet, "
    "hard hat, hood, mask, goggles, glasses, headset, scarf or badge "
    "unless the character's own outfit names one — and if it does, it is "
    "worn in every scene, never taken off or replaced. "
)
_REFERENCE_NOTE = (
    "The attached reference image is {name}; match that face exactly. Take "
    "ONLY the identity from it — the face, hair and build. Its pose, its "
    "framing and its gaze into the lens belong to a portrait, not to this "
    "shot: stage this shot from its own description instead. "
)

#: What the identity clause costs before a single character is described.
#: Measured, not guessed, so the reserve tracks the sentences automatically.
IDENTITY_CLAUSE_OVERHEAD = (
    len(_APPEARANCE_LOCK)
    + max(len(_COSTUME_LOCK_NAMED), len(_COSTUME_LOCK_REFERENCED))
    + len(_NO_UNNAMED_ITEMS)
    + len(_REFERENCE_NOTE.format(name="X" * 40))
)


def build_character_identity_clause(characters, matched_char=None, limit=None) -> str:
    """Restate every on-screen character's fixed appearance in the prompt text.

    The reference image only ever binds ONE character's identity (both MuAPI
    PuLID and fal Kontext take a single reference URL), so in a two-hander
    every OTHER character was previously re-invented from scratch by the image
    model on every scene — the direct cause of "the mother and daughter look
    like different people in different scenes". Naming each character with
    their locked description gives the non-referenced ones a stable textual
    anchor across the whole drama.

    `limit` caps the per-character detail so a crowded scene cannot push the
    whole prompt past the provider's character budget. It compacts rather
    than drops: a shorter anchor for everyone beats a full description for
    the first few and nothing for the rest, because an un-anchored character
    is exactly the one the image model re-invents.
    """
    visible = [c for c in (characters or []) if getattr(c, "is_visible", True)]
    described = _describe_characters(visible, limit)
    if not described:
        return ""
    clause = _APPEARANCE_LOCK + "; ".join(described) + ". "
    # Costume drift is its own failure, separate from face drift: the
    # reference image binds a face, not an outfit, so the image model dresses
    # everyone afresh each scene unless told not to (observed in the wild as
    # one character appearing in three different outfits across a three-scene
    # drama, and as a protagonist whose yellow overalls became a yellow slicker
    # and then a yellow hooded jacket). The lock is therefore ALWAYS stated;
    # only what it pins to changes — the named garments when they survived into
    # the clause above, the reference image when they did not.
    wardrobe_named = any(", wearing " in d for d in described) and all(
        (getattr(c, "wardrobe", "") or "").strip() for c in visible
    )
    clause += _COSTUME_LOCK_NAMED if wardrobe_named else _COSTUME_LOCK_REFERENCED
    clause += _NO_UNNAMED_ITEMS
    if matched_char is not None and getattr(matched_char, "name", ""):
        clause += _REFERENCE_NOTE.format(name=matched_char.name)
    return clause


def build_cast_closure_clause(characters) -> str:
    """Name the whole cast and forbid anyone else appearing in the frame.

    Nothing else in a frame prompt says how MANY people are in this story, so
    a populated location (a harbour, a station, a market) invites the image
    model to invent featured strangers, and a scene whose description mentions
    a second person invites it to duplicate the protagonist rather than draw
    someone new. Both were visible in the same delivered drama: a lone dock
    worker who arrived at the container beside a near-copy of herself.

    Emitted separately from the identity clause because it ranks BELOW the
    locked setting: a stray extra is a blemish, a room that changes between
    scenes breaks the film.
    """
    named = [
        (getattr(c, "name", "") or "").strip()
        for c in (characters or [])
        if getattr(c, "is_visible", True)
        and (getattr(c, "name", "") or "").strip()
        and (getattr(c, "static_features", "") or "").strip()
    ]
    if not named:
        return ""
    return (
        f"The cast is closed: {'only ' if len(named) == 1 else ''}"
        + ", ".join(named)
        + f" appear{'s' if len(named) == 1 else ''} in this story. Add no other "
        "featured or recognisable person, and never show the same character "
        "twice in one frame. Background figures only if the shot description "
        "asks for them, and then distant and unfocused. "
    )


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
    world_change: str = "",
    world_state: str = "",
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
    # The drama's ONE sanctioned break in the continuity lock (see
    # ScriptScene.world_change): the scene where the brief's event happens,
    # and every scene after it, which inherits the changed world.
    change_now = (world_change or "").strip()
    change_before = (world_state or "").strip()
    if parts:
        # Prefer "location, time_of_day" when both exist (user-requested shape).
        setting_clause = (
            f"Setting: {', '.join(parts)}. This scene takes place in the "
            f"EXACT SAME physical location established in the story's opening "
            f"shot -- identical architecture, furniture, wall decor, and "
            f"lighting fixtures. "
        )
        if change_now or change_before:
            # WITHOUT this the next sentence ("only the time-of-day lighting
            # may shift subtly") vetoes the event: a story whose climax IS a
            # blackout was rendered under the opening scene's streetlamps,
            # because the continuity clause is specific, imperative and comes
            # after the shot description. The set must still not change --
            # the same architecture, now in a different state.
            setting_clause += (
                f"The FIXTURES and architecture are unchanged, but their "
                f"STATE is not: {change_now or change_before}. Render the "
                f"location in that state -- this is the story's event and it "
                f"must be plainly visible in the frame, not implied. "
            )
        else:
            setting_clause += (
                f"Only the time-of-day lighting may shift subtly per the "
                f"story's setting_time_of_day; the room itself must not "
                f"change. "
            )
    else:
        setting_clause = ""
    # Only lit when the script actually establishes a setting. A legacy/demo
    # script that declares no location, hour or era at all keeps the exact
    # prompt shape it had before -- there is no continuity to protect across
    # scenes that were never placed anywhere.
    #
    # Suppressed once the world has changed: the plan is derived from the
    # story's time of day ("night harbour -> sodium streetlamps"), which is
    # exactly the thing a blackout removes. Keeping it would put the lamps
    # back on in the same prompt that asks for them to be out.
    lighting_clause = (
        resolve_lighting(setting_time_of_day).as_clause()
        if parts and not (change_now or change_before)
        else ""
    )
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
        # ...but "visible to camera" is not "staring down the lens", and
        # without this second sentence the model reads them as the same
        # thing. Every reference portrait is a frontal headshot with the eyes
        # on the lens, so the identity anchor pulls the same way: a delivered
        # drama had both workers stopping mid-scene to look dead at the
        # viewer, which reads as a poster, not a film. The eyeline has to be
        # aimed at something INSIDE the story for a shot to be a shot.
        "The character does NOT look into the lens: no eye contact with the "
        "camera, no posing for it, no addressing the viewer. Their gaze stays "
        "inside the scene — on the other character, or on the object they are "
        "handling — as if the camera were not there. "
    )
    # Budget for the identity clause: whatever is left after the shot itself
    # and its framing, minus room for the setting clause. Everything else is
    # optional and trimmed by fit_image_prompt below.
    # Everything that must survive alongside it is subtracted by its real
    # length: the identity clause's own fixed sentences (measured, see
    # IDENTITY_CLAUSE_OVERHEAD — a hand-tuned constant here silently shrank
    # every time one of those sentences grew) plus the style prefix and the
    # framing line. Guessing at any of it instead of measuring is what let a
    # crowded scene push the SETTING out of the prompt — the one clause that
    # promises the room does not change between scenes.
    identity_budget = (
        MAX_IMAGE_PROMPT_CHARS
        - len(shot.visual_desc)
        - len(setting_clause)
        - len(lighting_clause)
        - IDENTITY_CLAUSE_OVERHEAD
        - 200  # style prefix, shot type and lens line
    )
    identity_clause = build_character_identity_clause(
        characters, matched_char, limit=max(identity_budget, 200)
    )
    cast_clause = build_cast_closure_clause(characters)
    direction_clause = build_screen_direction_clause(characters)
    # (priority, text) in READING order. Priority 0 is required: the style,
    # the shot itself, its framing, and the character lock -- without the
    # first there is no frame, without the last the frame renders a stranger,
    # which is the failure this whole product exists to prevent.
    #
    # Everything else is dropped worst-priority-first when a crowded scene
    # pushes the prompt past the provider's budget. The quality suffix goes
    # first because it is pure polish; the setting and its lighting go last
    # because they make the continuity promise that the room (and the light
    # in it) does not change between shots.
    return fit_image_prompt([
        (0, f"{style} style. "),
        (1, setting_clause),
        # One rank BELOW the setting, though the two are a pair: within a
        # priority the drop falls on whichever clause reads first, which
        # meant a crowded prompt lost the place itself and kept its lamp
        # plan. Which room the scene is in outranks how it is lit.
        (2, lighting_clause),
        (0, identity_clause),
        (3, direction_clause),
        (0, f"{shot.visual_desc}. "),
        (2, expression_clause),
        (2, face_clause),
        (2, cast_clause),
        (3, dialogue_clause),
        (0, f"Shot type: {shot.shot_type}. Lens: {shot.lens}. "),
        (4, resolve_visual_style(style).render_note),
    ])


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
        # The frame can be staged correctly and the video model still turn a
        # head to the lens mid-shot -- it is animating a still, and "look at
        # the viewer" is the strongest attractor a portrait-trained model has.
        f"Nobody turns to look at the camera or acknowledges it; eyelines "
        f"stay inside the scene. "
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


# --- Delivery geometry ------------------------------------------------------
#
# The requested aspect ratio is honoured at GENERATION time: every frame is
# rendered at that ratio and Kling image-to-video inherits the frame's shape,
# so a 9:16 job is shot vertically rather than cropped out of a 16:9 master
# afterwards (that crop is what /api/jobs/{id}/export does, and it throws away
# the edges of the picture). This pass exists only to GUARANTEE the promise:
# providers occasionally hand back a clip whose shape drifted from the frame
# it animated, and a drama whose scenes disagree about their dimensions cannot
# even be stream-copy concatenated. Conforming rides along inside the colour
# grade's encode, so it costs no additional generation loss.

#: Delivery resolution per supported ratio -- the ceiling, not a floor (see
#: resolve_output_dimensions).
TARGET_RESOLUTIONS: Dict[str, Tuple[int, int]] = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}


def _even_dimension(value: float) -> int:
    """Round a pixel dimension DOWN to the nearest even number.

    yuv420p halves both axes, so x264 refuses odd dimensions outright, and
    fitting a ratio inside an arbitrary source produces fractional sizes
    routinely.
    """
    return max(2, int(value) // 2 * 2)


def is_exact_resolution_enabled() -> bool:
    """Force delivery at exactly TARGET_RESOLUTIONS, upscaling when the
    provider returned something smaller. OFF by default: upscaling invents no
    detail, it only spends bitrate to claim a resolution the pixels do not
    have. Turn on when a distributor demands literal 1080x1920 files.
    """
    return os.environ.get("MUSEFORGE_EXACT_RESOLUTION", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def resolve_output_dimensions(
    source_width: int, source_height: int, aspect_ratio: str
) -> Optional[Tuple[int, int]]:
    """Dimensions the delivered video should have for ``aspect_ratio``.

    The ratio is always exact. The resolution is the largest rectangle of that
    ratio that fits inside the source, capped at the canonical delivery size --
    so a 9:16 job ships 9:16 without ever being upscaled past what was really
    generated. Returns None for a ratio we do not deliver, which leaves the
    video untouched.
    """
    target = TARGET_RESOLUTIONS.get((aspect_ratio or "").strip())
    if not target:
        return None
    target_w, target_h = target
    if source_width <= 0 or source_height <= 0 or is_exact_resolution_enabled():
        return target

    ratio = target_w / target_h
    if source_width / source_height > ratio:
        # Source is wider than the target: height is the binding constraint.
        height = float(source_height)
        width = height * ratio
    else:
        width = float(source_width)
        height = width / ratio
    if width > target_w:
        width, height = float(target_w), float(target_h)
    return _even_dimension(width), _even_dimension(height)


def build_geometry_filters(
    source_width: int, source_height: int, aspect_ratio: str
) -> List[str]:
    """ffmpeg filters that conform a clip to the delivered geometry.

    Scale-to-cover then centre-crop: a clip that already has the right shape
    is only ever resized, and one that drifted loses its edges rather than
    gaining letterbox bars -- black bars in a vertical feed read as a broken
    upload. Returns [] when the clip is already correct, so the caller can
    skip the work entirely.
    """
    dimensions = resolve_output_dimensions(source_width, source_height, aspect_ratio)
    if not dimensions:
        return []
    width, height = dimensions
    if (source_width, source_height) == (width, height):
        return []
    return [
        f"scale={width}:{height}:force_original_aspect_ratio=increase",
        f"crop={width}:{height}",
        "setsar=1",
    ]


def _probe_dimensions(video_path: str) -> Tuple[int, int]:
    """(width, height) of ``video_path``, or (0, 0) when it cannot be read."""
    try:
        from moviepy import VideoFileClip

        with VideoFileClip(video_path) as clip:
            width, height = clip.size or (0, 0)
            return int(width), int(height)
    except Exception as exc:
        logger.warning("Could not probe %s for delivery geometry: %s", video_path, exc)
        return 0, 0


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
        from moviepy import VideoFileClip
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
    video_path: str,
    output_path: str,
    director_style: str = "cinematic_balanced",
    aspect_ratio: Optional[str] = None,
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

    # Conform the delivered geometry in the SAME encode as the grade -- the
    # master is graded exactly once, so folding the scale/crop in here costs
    # nothing extra and guarantees the job ships in the ratio it was ordered
    # in even if a provider handed back a differently-shaped clip.
    if aspect_ratio:
        source_width, source_height = _probe_dimensions(video_path)
        geometry = build_geometry_filters(source_width, source_height, aspect_ratio)
        if geometry:
            logger.info(
                "Conforming %sx%s master to %s delivery geometry (%s)",
                source_width,
                source_height,
                aspect_ratio,
                geometry[0],
            )
            filter_chain = ",".join(geometry + [filter_chain])

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
        story_so_far: str = "",
        not_yet: str = "",
        world_change: str = "",
        world_state: str = "",
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
            # Same style string the frame prompt gets, so the shot is
            # DESIGNED for the look it will be rendered in.
            style=style,
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
            story_so_far=story_so_far,
            not_yet=not_yet,
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
                        world_change=world_change,
                        world_state=world_state,
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

                    # Which model animates this shot depends on what KIND of
                    # shot it is, not just on the plan: a talking close-up and
                    # a chase fail in different ways, and an empty-set plate
                    # needs neither's strengths. See tools/video_model_router.
                    shot_profile = classify_shot(
                        motion_desc=getattr(shot, "motion_desc", "") or "",
                        visual_desc=getattr(shot, "visual_desc", "") or "",
                        camera_movement=getattr(shot, "camera_movement", "") or "",
                        shot_type=getattr(shot, "shot_type", "") or "",
                        has_dialogue=has_dialogue,
                        scene_tension=scene_tension,
                        has_character=matched_char is not None,
                    )
                    video_url = await self.video_gen.generate_video_from_image(
                        prompt=video_prompt,
                        image_url=frame_url if not one_step_reference_video else reference_url,
                        duration=int(getattr(shot, "duration_seconds", 5.0)),
                        aspect_ratio=aspect_ratio,
                        plan=plan,
                        is_cancelled=is_cancelled,
                        shot_profile=shot_profile,
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
                # Recorded so "why does this shot look wrong?" can be answered
                # from the job record -- which model profile handled it -- rather
                # than by re-deriving the classification from the prompt text.
                meta["shot_profile"] = shot_profile
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
