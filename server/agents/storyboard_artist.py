"""Storyboard artist agent — designs shots from script with director style guidance."""

import json
import logging
import os
import re
from typing import List, Optional

from interfaces import acting
from interfaces.camera import get_director_style
from interfaces.character import CharacterInScene
from interfaces.shot import StoryboardShot
from interfaces.shot_plan import plan_scene_shots, split_scene_seconds
from interfaces.visual_style import resolve as resolve_visual_style
from tools.claude_via_muapi import complete_via_muapi, is_muapi_llm_enabled

logger = logging.getLogger(__name__)

#: How many shots a scene is allowed to be made of.
#:
#: ONE, and this is the single biggest reason a finished drama does not feel
#: like a film. A film is made of shots: two people talking are covered from
#: two angles, and the cut between them is the grammar the whole medium runs
#: on. This ships every scene as one continuous take from one generated
#: frame, so an eight-second exchange is eight seconds of one framing --
#: measured on a delivered drama as a mean frame-to-frame difference of 8 for
#: its whole length, which is a photograph that moves slightly.
#:
#: It is a COST cap, not a craft decision: each extra shot is another frame
#: generation plus another image-to-video call, so coverage roughly doubles
#: or triples what a scene costs to make. interfaces/pacing's internal cuts
#: exist as the free substitute -- they punch in on the frame we already
#: have, which buys rhythm but not a second angle.
#:
#: Raise it to buy real coverage. The storyboard is asked for exactly this
#: many shots, so the value reaches the model as well as the slice.
DEFAULT_SHOTS_PER_SCENE = 1


def shots_per_scene() -> int:
    """The configured shot count, clamped to something a scene can hold."""
    raw = os.environ.get("MUSEFORGE_SHOTS_PER_SCENE", "").strip()
    if not raw:
        return DEFAULT_SHOTS_PER_SCENE
    try:
        return max(1, min(4, int(raw)))
    except ValueError:
        logger.warning(
            "MUSEFORGE_SHOTS_PER_SCENE=%r is not a number; using %d.",
            raw,
            DEFAULT_SHOTS_PER_SCENE,
        )
        return DEFAULT_SHOTS_PER_SCENE


#: The two sentences in SYSTEM_PROMPT that hard-code a shot count, and what
#: they have to become when the scene is allowed coverage. Rewritten rather
#: than contradicted by a clause appended below them: a prompt that says "you
#: only get ONE shot" at the top and "cover it in three" at the bottom leaves
#: the model to choose, and this codebase has already paid for that once --
#: the costume lock and the reference note disagreed about clothing, and the
#: model dressed the cast afresh every scene.
_SINGLE_SHOT_SENTENCES = (
    (
        "Design exactly 1 shot for the given scene script.",
        "Design exactly {count} shots for the given scene script.",
    ),
    (
        "CHOOSE THE RIGHT MOMENT. You only get ONE shot for this scene, so it "
        "must capture the",
        "CHOOSE THE RIGHT MOMENTS. You get {count} shots for this scene, and "
        "together they must capture the",
    ),
    (
        "Respond ONLY with valid JSON array containing a single shot object:",
        "Respond ONLY with valid JSON array containing {count} shot objects, "
        "in playing order:",
    ),
)


def coverage_clause(count: int) -> str:
    """What to tell the storyboard when a scene may hold more than one shot."""
    if count <= 1:
        return ""
    return (
        f"\n\nCOVER THE SCENE IN {count} SHOTS. Make them DIFFERENT shots: "
        f"change the shot_type and the angle between them the way coverage "
        f"does — a wide that establishes, then the closer framing the beat "
        f"actually plays in, and on a two-hander cut to whoever is speaking "
        f"or reacting. Two shots of the same size from the same angle are one "
        f"shot with a join in it. Their duration_seconds must SUM to the "
        f"scene's length: divide it between them rather than giving each the "
        f"whole scene."
    )


def system_prompt_for(base: str, count: int) -> str:
    """``base`` rewritten for a scene that may hold ``count`` shots.

    Returned unchanged at a count of one, so every existing deployment sends
    a byte-identical prompt.
    """
    if count <= 1:
        return base
    prompt = base
    for original, replacement in _SINGLE_SHOT_SENTENCES:
        if original not in prompt:
            # The prompt was edited and this sentence moved. Better to leave
            # it alone and let the appended clause carry the instruction than
            # to silently half-rewrite the brief.
            logger.warning(
                "Storyboard prompt no longer contains %.40s...; coverage is "
                "requested by the appended clause alone.",
                original,
            )
            continue
        prompt = prompt.replace(original, replacement.format(count=count))
    return prompt + coverage_clause(count)


class StoryboardArtist:
    SYSTEM_PROMPT = """You are a master storyboard artist for cinematic productions.
Design exactly 1 shot for the given scene script. Apply the director's style guidance.

THE USER'S BRIEF OUTRANKS EVERYTHING BELOW. When the brief is given it is the
production's specification: honour its named props, wardrobe, location, framing,
lens and camera rules exactly, and never design a shot that contradicts it. If the
brief says the camera is locked off, "camera_movement" is "static locked-off tripod,
no camera movement" — not a push-in. If the brief names what is in frame (a desk, a
notepad, a watch), name those things in "visual_desc" so they actually get rendered.
Only where the brief is silent do the guidelines below decide.

CHOOSE THE RIGHT MOMENT. You only get ONE shot for this scene, so it must capture the
scene's DRAMATIC PEAK — the single beat that carries the scene's emotional turn (the
look that lands, the touch, the break, the decision). Do NOT storyboard set-up,
arrival, walking, waiting, or scene-setting business when an emotional beat exists in
the scene; a viewer seeing only your shot must understand what emotionally happened.
If the scene has dialogue, stage the moment around the most important line.
When the director's notes name THE TURN, that is the moment — film it, not the
business around it. Honour the given staging (positions, hands, the object the scene
turns on) instead of inventing different blocking.

NAME EVERY PERSON IN FRAME. Refer to anyone visible in "visual_desc" by their given
NAME, in the first clause that mentions them — "Margit walks the alley", never "the
old bookseller walks the alley" or "she walks the alley". The name is not a style
choice: the render step picks each character's locked reference portrait by finding
their name in this text, so a person described only by role or pronoun gets NO face
to match and the model invents a stranger — a different actor at every cut. Use the
name first, then describe; pronouns are fine once the name has been given in the
same shot.

DO NOT FILM THE FUTURE. The notes tell you what has ALREADY happened in earlier scenes
and what has NOT happened yet. Your shot shows the world exactly as it stands at THIS
point in the story: never show a later scene's event, its aftermath or its changed state
(a container already open, the lights already out, a wound not yet taken, a character not
yet arrived), and never undo something an earlier scene established. When the scene IS
the event, show the event itself happening on camera — that is the shot.

MATCH SHOT SCALE TO THE BEAT. Let the scene's dramatic function and tension pick the
framing: setup and resolution can breathe in wide or medium; rising_action and
turning_point tighten to medium; climax and any tension of 8+ belong in a close-up
where the face fills the frame. High tension also earns more screen time.

PLAY THE SUBTEXT, NOT THE LINE. When the notes give subtext that contradicts the
dialogue, the expression must play the subtext — a character insisting they are fine
while their face says otherwise is the shot worth making.

RESPECT THE 180° LINE. Screen direction is LOCKED for the whole drama: in any
two-character conversation the FIRST character listed always occupies frame-left
looking screen-RIGHT, and the SECOND always occupies frame-right looking
screen-LEFT — in every scene, including singles and over-the-shoulder shots (a
character alone in frame still looks toward where the other one is). Never cross
the line or mirror the composition between scenes; reversed eyelines make a
conversation read as two people facing away from each other.

SHOW THE EMOTION ON THE FACE. The scene's emotional beat is given to you. "expression_desc"
must state the concrete, visible facial expression AND body language for the character(s)
in frame (e.g. "eyes brimming with tears, trembling chin, shoulders finally dropping as
she exhales"). Never write "neutral", "calm", "expressionless", or a blank value unless
the scene is genuinely emotionless. Repeat the key expression inside visual_desc too.

SHOW THE CHANGE ON THE FACE, NOT FROM ACROSS THE STREET. When the notes name
what changes about the place — the lights dying, the water rising, the fire
taking — that change is mandatory AND it does not license a wide shot. Both
instructions are live at once, and this is how they resolve: film the change
in the SAME frame as the character, through what it does to them. The light
that used to be on their face is gone and one source is left; the glow moves
across their features; the darkness starts behind their shoulder. A blackout
filmed by retreating to a wide is a picture of a location — technically
correct, dramatically nothing, and the one moment in your drama where nobody
can see a face is the moment it turns. If the change genuinely cannot be read
without distance, take the wide AND keep a character large in the foreground.

KEEP FACES READABLE. Faces must be clearly visible and lit well enough to read the
expression — soft key light on the face. Do NOT design pure silhouettes, backlit
shapes, faces turned away from camera, or faces hidden by shadow; those destroy the
emotional read. Prefer medium or close-up framing for emotional beats so the face fills
enough of the frame to be legible.

NEVER PLAY TO THE LENS. Readable is not the same as facing the viewer. No character
looks into the camera, acknowledges it, or poses for it — write every eyeline as aimed
at something inside the story (the other character, the object in their hands, the
thing they have just noticed off-screen). A row of characters staring down the lens is
a poster, not a scene, and it is the single fastest way to make a drama look generated.

If a locked Setting is provided, EVERY shot MUST stay in that place and time of day —
do not invent a different location or lighting for this scene. The ONE exception is a
scene whose director's notes name what changes about the place: then that change is
mandatory and must be visible in the shot, and everything else about the location still
holds.
For duration_seconds do NOT blindly assign 5 to every shot — pick between 3 and 15
based on the scene's importance: 4-6 for short transition/action shots, 8-12 for
emotional/establishing moments, 13-15 for very important finales.
Respond ONLY with valid JSON array containing a single shot object:
[{"idx": 0, "visual_desc": "...", "motion_desc": "...", "expression_desc": "...",
  "audio_desc": "...", "shot_type": "wide|medium|close-up", "camera_movement": "...",
  "lens": "50mm", "duration_seconds": 8}]
(duration_seconds is an example — vary 3-15 by scene; do not always use 5.)"""

    #: One shot's JSON is small, but the director's notes make the RESPONSE
    #: longer than the old default allowed. Same lesson as the screenwriter:
    #: both provider paths must share the budget.
    #:
    #: Raised for adaptive thinking: on Sonnet 5 it is on by default and
    #: `max_tokens` caps thinking plus text together, so 2048 left the shot
    #: list itself with whatever thinking did not use.
    MAX_SHOT_TOKENS = 6000

    def __init__(self, api_key: Optional[str] = None, demo: bool = False):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.muapi_key = os.environ.get("MUAPI_KEY", "")
        self.demo = demo

    # Non-finale scenes are capped well below the model's max so a run of
    # "important" scenes can't each independently land on 13-15s -- that
    # both defeats the intended variety and multiplies total Kling render
    # time and cost, which scale with generated seconds.
    NON_FINALE_MAX_DURATION = 9.0
    FINALE_MAX_DURATION = 15.0

    # When the script carries a dramatic tension, the cap follows the BEAT
    # rather than being one flat ceiling every scene drifts up to. A quiet
    # setup gets ~5s and a climax ~10s, which is both better filmmaking (a
    # varied rhythm instead of uniform blocks) and cheaper: a run of scenes
    # can no longer each sit at the flat maximum.
    TENSION_MIN_DURATION = 5.0
    TENSION_MAX_DURATION = 10.0
    # A finale needs room to land even when its tension is low (a quiet
    # resolution is still the ending), so it gets extra headroom.
    FINALE_EXTRA_DURATION = 3.0
    FINALE_MIN_DURATION = 8.0

    @classmethod
    def duration_cap(cls, is_finale: bool, tension: int = 0) -> float:
        """Maximum shot length for a scene, in seconds.

        Without a tension value (legacy scripts) this is exactly the previous
        flat behavior. With one, the cap scales linearly across the tension
        range so screen time is spent where the drama is.
        """
        if not tension:
            return cls.FINALE_MAX_DURATION if is_finale else cls.NON_FINALE_MAX_DURATION
        tension = max(1, min(10, int(tension)))
        span = cls.TENSION_MAX_DURATION - cls.TENSION_MIN_DURATION
        cap = cls.TENSION_MIN_DURATION + ((tension - 1) / 9.0) * span
        if is_finale:
            cap = max(cap + cls.FINALE_EXTRA_DURATION, cls.FINALE_MIN_DURATION)
            return min(cap, cls.FINALE_MAX_DURATION)
        return min(cap, cls.NON_FINALE_MAX_DURATION)

    async def design_storyboard(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: str = "",
        director_style: str = "cinematic_balanced",
        # The drama's visual style (Noir, Anime, Documentary...). It reached
        # the image model as a two-word prefix and stopped there, so shot
        # DESIGN was identical for every style the product sells: a noir and
        # a romance were the same frames with a different word in front of
        # them. Defaulted so every existing caller keeps working unchanged.
        style: str = "Cinematic",
        setting_location: str = "",
        setting_time_of_day: str = "",
        setting_era: str = "",
        is_finale: bool = False,
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
        # The framing this scene must use, decided across the whole drama so
        # consecutive scenes cannot repeat a setup (interfaces/shot_plan).
        scene_shot_scale: str = "",
        # Whether this scene will be lip-synced. Not a prompt input: it decides
        # whether the scene may buy a second ANGLE, because the lip-sync pass
        # drives a mouth across the whole scene clip and cannot see a cut in
        # the middle of it (see interfaces/shot_plan.plan_scene_shots).
        lipsync_enabled: bool = False,
    ) -> List[StoryboardShot]:
        preset = get_director_style(director_style)

        # Demo mode must stay fast and free of real network calls --
        # matches MuAPIImageGenerator/MuAPIVideoGenerator's demo behavior.
        if self.demo:
            return self._finish_shots(
                self._design_template(
                    script, characters, preset, scene_emotion, scene_shot_scale
                ),
                scene_emotion,
                is_finale,
                scene_tension,
                scene_duration,
                characters=characters,
                lipsync_enabled=lipsync_enabled,
                scene_shot_scale=scene_shot_scale,
            )

        prompt = self._build_prompt(
            script=script,
            characters=characters,
            user_requirement=user_requirement,
            guidance=preset.storyboard_guidance,
            default_lens=preset.default_lens,
            style=style,
            setting_location=setting_location,
            setting_time_of_day=setting_time_of_day,
            setting_era=setting_era,
            scene_emotion=scene_emotion,
            scene_dialogue=scene_dialogue,
            scene_direction=scene_direction,
            character_direction=character_direction,
            theme=theme,
            visual_motif=visual_motif,
            user_brief=user_brief,
            story_so_far=story_so_far,
            not_yet=not_yet,
            scene_shot_scale=scene_shot_scale,
        )

        # 1) MuAPI first, but opt-in only -- its LLM slug is a guess, so it
        #    does not stand in front of the Anthropic path unless
        #    MUAPI_LLM_MODEL is set (see tools/claude_via_muapi.py).
        if self.muapi_key and is_muapi_llm_enabled():
            try:
                content = await complete_via_muapi(
                    system_prompt_for(self.SYSTEM_PROMPT, shots_per_scene()),
                        prompt,
                        max_tokens=self.MAX_SHOT_TOKENS * shots_per_scene(),
                )
                data = json.loads(re.search(r"\[[\s\S]*\]", content).group())
                shots = [StoryboardShot(**s) for s in data]
                if shots:
                    # Cost cap, now configurable -- see
                    # DEFAULT_SHOTS_PER_SCENE. This path was previously
                    # missing the cap already applied to the direct-Anthropic
                    # fallback below, silently defeating the cost fix since
                    # MuAPI is the PRIMARY path, tried first.
                    return self._finish_shots(
                        shots[:shots_per_scene()],
                        scene_emotion,
                        is_finale,
                        scene_tension,
                        scene_duration,
                        characters=characters,
                        lipsync_enabled=lipsync_enabled,
                        scene_shot_scale=scene_shot_scale,
                    )
            except Exception as exc:
                raw_snippet = locals().get("content", "<no content received>")
                logger.warning(
                    f"MuAPI LLM call failed, falling back: {exc} | "
                    f"Raw response (first 500 chars): {str(raw_snippet)[:500]!r}"
                )

        # 2) Fall back to a direct Anthropic call if a key is configured.
        if self.api_key:
            shots = await self._design_with_claude(
                script,
                characters,
                user_requirement,
                preset.storyboard_guidance,
                preset.default_lens,
                style=style,
                setting_location=setting_location,
                setting_time_of_day=setting_time_of_day,
                setting_era=setting_era,
                scene_emotion=scene_emotion,
                scene_dialogue=scene_dialogue,
                scene_direction=scene_direction,
                character_direction=character_direction,
                theme=theme,
                visual_motif=visual_motif,
                user_brief=user_brief,
                story_so_far=story_so_far,
                not_yet=not_yet,
                scene_shot_scale=scene_shot_scale,
            )
            if shots:
                # Cost cap, now configurable -- see DEFAULT_SHOTS_PER_SCENE.
                return self._finish_shots(
                    shots[:shots_per_scene()],
                    scene_emotion,
                    is_finale,
                    scene_tension,
                    scene_duration,
                    characters=characters,
                    lipsync_enabled=lipsync_enabled,
                    scene_shot_scale=scene_shot_scale,
                )

        # 3) Last resort: deterministic template, never crashes generation.
        return self._finish_shots(
            self._design_template(
                    script, characters, preset, scene_emotion, scene_shot_scale
                ),
            scene_emotion,
            is_finale,
            scene_tension,
            scene_duration,
            characters=characters,
            lipsync_enabled=lipsync_enabled,
            scene_shot_scale=scene_shot_scale,
        )

    @classmethod
    def _clamp_durations(
        cls,
        shots: List[StoryboardShot],
        is_finale: bool,
        tension: int = 0,
        budget: float = 0.0,
    ) -> List[StoryboardShot]:
        """Set each shot's length.

        With a `budget` (the drama's fixed second allowance, already split by
        tension in interfaces/second_budget) the scene is SET to it rather
        than merely capped: the provider bills per second, so leaving the
        model free to come in under budget makes the job's cost -- and its
        margin -- unpredictable at the moment credits are charged. The budget
        is the whole point; honouring it exactly is what makes the promise
        "N credits buys M seconds" true.

        The budget belongs to the SCENE, and a scene may be more than one shot
        (MUSEFORGE_SHOTS_PER_SCENE). Setting each shot to it delivered the
        budget once per shot: measured on a delivered job with coverage of 2,
        scenes budgeted 8 / 10 / 12 seconds ran 16.08 / 20.08 / 24.08 and the
        drama billed for 30 seconds ran 60. So the budget is DIVIDED here --
        which is what coverage_clause already asks the model for in the prompt
        ("their duration_seconds must SUM to the scene's length"), and what
        this method used to overwrite the moment it answered.

        Without a budget (legacy callers, single-scene tests) this keeps the
        previous cap-only behaviour.
        """
        if budget and budget > 0:
            shares = split_scene_seconds(
                budget, [shot.duration_seconds for shot in shots]
            )
            for shot, share in zip(shots, shares):
                shot.duration_seconds = float(share)
            return shots
        cap = cls.duration_cap(is_finale, tension)
        for shot in shots:
            shot.duration_seconds = min(float(shot.duration_seconds or 0), cap)
        return shots

    # Expressions that mean "no emotion on the face" -- exactly what the
    # user-reported flat/neutral scenes looked like. When a shot comes back
    # with one of these (or with nothing at all), we substitute the scene's
    # own emotional beat so the frame prompt still carries an expression.
    _EMPTY_EXPRESSIONS = {
        "",
        "neutral",
        "none",
        "n/a",
        "calm",
        "expressionless",
        "neutral expression",
        "no expression",
    }

    @classmethod
    def _ensure_expression(
        cls, shots: List[StoryboardShot], scene_emotion: str
    ) -> List[StoryboardShot]:
        """Guarantee every shot carries a usable expression beat.

        The LLM is instructed to fill expression_desc, but it is the single
        thing that makes a scene read as emotional, so it is not left to
        chance: a missing/neutral value falls back to the scene's emotion tag.
        """
        emotion = (scene_emotion or "").strip()
        if not emotion:
            return shots
        for shot in shots:
            # getattr/setattr rather than attribute access: shots may be
            # plain objects from callers/tests that predate expression_desc.
            current = (getattr(shot, "expression_desc", "") or "").strip()
            if current.lower().rstrip(".") in cls._EMPTY_EXPRESSIONS:
                try:
                    shot.expression_desc = emotion
                except AttributeError:
                    # Immutable/slotted shot object -- the frame prompt just
                    # falls back to its face-visibility clause.
                    pass
        return shots

    @classmethod
    def _apply_acting_beats(
        cls, shots: List[StoryboardShot], scene_emotion: str
    ) -> List[StoryboardShot]:
        """Give every shot an onset and a PEAK, deterministically.

        Runs after ``_ensure_expression``, and does two different jobs:

        * ``expression_desc`` gains an anatomical floor from
          interfaces/acting -- "cold resentment" on its own is drawn as a face
          doing nothing, which is the flat, generated look this exists to kill.
          An agent that already wrote something specific keeps its own words
          (see acting.onset_expression).
        * ``expression_peak_desc`` is set unconditionally. Nothing else fills
          it: the LLM is never asked for the peak, because the peak has to be
          identical across re-renders of the same scene or a retake silently
          re-acts the film. It is the target of the start-to-end frame
          interpolation, and it is also what tells the video model where the
          performance is GOING even when no end frame is rendered.
        """
        for shot in shots:
            try:
                written = (getattr(shot, "expression_desc", "") or "").strip()
                shot.expression_desc = acting.onset_expression(scene_emotion, written)
                shot.expression_peak_desc = acting.peak_expression(scene_emotion)
            except AttributeError:
                # Immutable/slotted shot objects from older callers and tests:
                # the shot simply animates without a staged peak, exactly as
                # it did before this existed.
                continue
        return shots

    @classmethod
    def _finish_shots(
        cls,
        shots: List[StoryboardShot],
        scene_emotion: str,
        is_finale: bool,
        tension: int = 0,
        budget: float = 0.0,
        characters: Optional[List[CharacterInScene]] = None,
        lipsync_enabled: bool = False,
        scene_shot_scale: str = "",
    ) -> List[StoryboardShot]:
        """Every path's last step: expression, acting beats, angles, durations.

        Written once because it was previously written three times and the
        three had already drifted -- the template path never got
        ``_ensure_expression`` at all, so a key-less run produced shots whose
        only emotional content was whatever the scene tag happened to say.
        """
        cls._ensure_expression(shots, scene_emotion)
        cls._apply_acting_beats(shots, scene_emotion)
        cls._note_scale_drift(shots, scene_shot_scale)
        shots = cls._clamp_durations(shots, is_finale, tension, budget)
        return cls._apply_shot_plan(
            shots, scene_emotion, tension, characters or [], lipsync_enabled, budget
        )

    @classmethod
    def _note_scale_drift(cls, shots: List[StoryboardShot], planned: str) -> None:
        """Log when the designer ignored the planned framing. Never overrides.

        The plan is binding in the prompt and NOT enforced in code, on purpose:
        the user's brief outranks everything (it may demand a locked-off wide),
        and the agent is the only party that has read it. Silently rewriting
        ``shot_type`` would also leave a shot whose description composes for
        one framing and whose field claims another.

        So drift is made visible instead. A model that starts ignoring this is
        a model that has quietly reintroduced eighteen seconds of one setup,
        and that should show up in a log rather than in a delivered drama.
        """
        planned = (planned or "").strip().lower()
        if not planned or not shots:
            return
        actual = (getattr(shots[0], "shot_type", "") or "").strip().lower()
        if actual and actual != planned:
            logger.info(
                "Shot designer chose %r over the planned %r for this scene.",
                actual,
                planned,
            )

    @classmethod
    def _apply_shot_plan(
        cls,
        shots: List[StoryboardShot],
        scene_emotion: str,
        tension: int,
        characters: List[CharacterInScene],
        lipsync_enabled: bool = False,
        budget: float = 0.0,
    ) -> List[StoryboardShot]:
        """Give a peak scene a second angle, and set generate/deliver lengths.

        The reaction shot is DERIVED, not asked for. Sending the model a
        second prompt would cost another LLM round trip on the critical path
        and would answer differently on every render of the same scene -- and
        the answer is not open anyway: the cutaway is a close-up of the face
        that is listening, playing the same beat from the other side. What the
        agent decides (the moment, the staging, the emotion) is inherited from
        the master shot it is cut against, which is also what keeps the two
        halves of the cut describing one continuous event.
        """
        if not shots:
            return shots
        master = shots[0]
        # The plan is the SCENE's, so it is made from the scene's budget --
        # which is no longer the same number as the master's own length once
        # coverage has divided that budget between several shots. Falling back
        # to the master's length keeps every budget-less caller (legacy paths,
        # single-scene tests) on exactly the arithmetic it had before.
        plan = plan_scene_shots(
            float(budget or 0.0)
            or float(getattr(master, "duration_seconds", 0.0) or 0.0),
            tension=tension,
            lipsync_enabled=lipsync_enabled,
        )
        master.role = plan[0].role
        master.deliver_seconds = plan[0].deliver_seconds
        if len(plan) < 2:
            return shots

        # The cutaway replaces whatever coverage the designer proposed, so the
        # master carries the whole scene again and is generated for it -- the
        # share _clamp_durations gave it was a share of a cut that no longer
        # happens there.
        master.duration_seconds = plan[0].generate_seconds
        reaction = cls._build_reaction_shot(master, scene_emotion, characters)
        reaction.duration_seconds = plan[1].generate_seconds
        reaction.deliver_seconds = plan[1].deliver_seconds
        reaction.role = plan[1].role
        return [master, reaction]

    #: Who the cutaway is ON. A drama with two people in the scene cuts to the
    #: OTHER one -- that is what a reaction shot is, and the pipeline can hold
    #: their face because every character carries a locked portrait. With only
    #: one person on screen there is nobody to cut to, so the cut goes tighter
    #: on the same face instead, which is a cut-in rather than a reverse but
    #: still a change of framing bought with a real generation.
    @classmethod
    def _build_reaction_shot(
        cls,
        master: StoryboardShot,
        scene_emotion: str,
        characters: List[CharacterInScene],
    ) -> StoryboardShot:
        visible = [c for c in characters if getattr(c, "is_visible", True)]
        master_text = f"{master.visual_desc} {master.motion_desc}".lower()
        # The subject of the master is whoever it names first; the reaction is
        # anyone else. Named explicitly in visual_desc because that is what the
        # frame step matches on to pick the right locked portrait
        # (script2video.on_screen_name_matches) -- get the name wrong here and
        # the cut lands on a stranger.
        subject = next(
            (c for c in visible if (c.name or "").lower() in master_text), None
        )
        other = next((c for c in visible if c is not subject), None)

        peak = (getattr(master, "expression_peak_desc", "") or "").strip()
        if other is not None:
            who = other.name
            visual = (
                f"Tight close-up on {who}'s face as they take in what has just "
                f"happened. {who} is listening, not speaking."
            )
            expression = (
                f"{who} reacting in the moment: {peak}" if peak else f"{who} reacting"
            )
        else:
            who = subject.name if subject is not None else "the character"
            visual = (
                f"Extreme close-up on {who}'s eyes and mouth as the moment "
                f"lands. Nothing else in frame."
            )
            expression = peak or "the moment landing on the face"

        return StoryboardShot(
            idx=master.idx + 1,
            visual_desc=visual,
            # A cutaway holds. Movement in a two-second insert reads as a
            # camera error, not as energy.
            motion_desc=(
                "Almost still: the smallest involuntary movement only — a "
                "blink, a swallow, the breath catching."
            ),
            expression_desc=expression,
            expression_peak_desc=peak,
            audio_desc=getattr(master, "audio_desc", "") or "",
            shot_type="extreme close-up",
            camera_movement="static",
            # Longer glass compresses and isolates: the lens a cutaway is
            # actually shot on, and visibly different from the master's.
            lens="85mm",
        )

    def _build_prompt(
        self,
        *,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: str,
        guidance: str,
        default_lens: str,
        style: str = "Cinematic",
        setting_location: str = "",
        setting_time_of_day: str = "",
        setting_era: str = "",
        scene_emotion: str = "",
        scene_dialogue: str = "",
        scene_direction: str = "",
        character_direction: str = "",
        theme: str = "",
        visual_motif: str = "",
        user_brief: str = "",
        story_so_far: str = "",
        not_yet: str = "",
        scene_shot_scale: str = "",
    ) -> str:
        """The user turn for a shot-design call, for EITHER provider path.

        Written once because it was written twice: the two paths carried
        byte-identical prompt assembly, and a clause added to one of them
        silently did nothing on the other. That is not hypothetical -- the
        story-state block (which stops scene 1 being staged as the story's
        payoff) was added to the MuAPI path alone and was therefore dead on
        the DEFAULT path, since MuAPI's LLM route is opt-in.
        """
        char_desc = ", ".join(
            f"{c.name}: {c.static_features}" for c in characters if c.is_visible
        )
        return (
            f"{self._format_user_brief_block(user_brief)}"
            f"Scene script: {script}\n"
            f"{self._format_scale_line(scene_shot_scale)}"
            f"{self._format_emotion_line(scene_emotion)}"
            f"{self._format_direction_block(scene_direction)}"
            f"{self._format_story_state(story_so_far, not_yet)}"
            f"{self._format_dialogue_line(scene_dialogue)}"
            f"Characters: {char_desc}\n"
            f"{self._format_character_direction_block(character_direction)}"
            f"{self._format_setting_line(setting_location, setting_time_of_day, setting_era)}"
            f"{self._format_through_line(theme, visual_motif)}"
            f"{self._format_visual_style(style)}"
            f"Director guidance: {guidance}\nDefault lens: {default_lens}\n"
            f"User requirements: {user_requirement or 'none'}"
        )

    #: How much of the user's prompt is carried into the shot-design call.
    #: The API caps an idea at 2000 characters, so this passes it whole; the
    #: bound exists only so a future cap increase cannot blow the token budget.
    MAX_BRIEF_CHARS = 2000

    @classmethod
    def _format_user_brief_block(cls, user_brief: str = "") -> str:
        """The user's own words, at the TOP of the prompt and marked binding.

        The scene action line is a lossy re-telling: it survives the
        screenwriter's rewrite, the brief's concrete specifics (props on the
        desk, the exact sweater, "locked-off tripod, zero camera movement")
        do not. Restating them here is what stops the shot being designed
        against a description the user never wrote.
        """
        brief = (user_brief or "").strip()
        if not brief:
            return ""
        if len(brief) > cls.MAX_BRIEF_CHARS:
            brief = brief[: cls.MAX_BRIEF_CHARS].rstrip() + " […]"
        return (
            "USER'S ORIGINAL BRIEF — BINDING, outranks every other instruction "
            "below. Honour its wardrobe, props, location, framing and camera "
            "rules exactly; never design a shot that contradicts it:\n"
            f"{brief}\n\n"
        )

    @staticmethod
    def _format_scale_line(scene_shot_scale: str = "") -> str:
        """The framing this scene must use, decided across the whole drama.

        Binding, and it outranks this prompt's own "match shot scale to the
        beat" guidance for one reason that guidance cannot see: scenes are
        designed independently and in parallel, so nothing else in the system
        knows what the PREVIOUS scene looked like. Repetition is only visible
        from outside a scene (see interfaces/shot_plan.plan_shot_scales).
        """
        scale = (scene_shot_scale or "").strip()
        if not scale:
            return ""
        return (
            f"FRAMING FOR THIS SCENE — BINDING: {scale}. This was chosen "
            f"across the whole drama so that no two consecutive scenes repeat "
            f"the same setup; a shot that is right on its own but identical to "
            f"the one before it makes two scenes read as one long take. Set "
            f'"shot_type" to exactly this, and compose for it.\n'
        )

    @staticmethod
    def _format_emotion_line(scene_emotion: str = "") -> str:
        emotion = (scene_emotion or "").strip()
        if not emotion:
            return ""
        return (
            f"Scene emotional beat (MUST be visible on the character's face "
            f"and body in this shot): {emotion}\n"
        )

    @staticmethod
    def _format_direction_block(scene_direction: str = "") -> str:
        """The scene's dramatic function, turn, subtext, staging and tension.

        The turn is the single most important input to shot selection: it
        names the moment that must be filmed.
        """
        direction = (scene_direction or "").strip()
        if not direction:
            return ""
        return f"DIRECTOR'S NOTES FOR THIS SCENE:\n{direction}\n"

    @staticmethod
    def _format_story_state(story_so_far: str = "", not_yet: str = "") -> str:
        """Where this scene sits in the story: what is done, what is not.

        Scenes are storyboarded independently (and, by default, in parallel),
        so nothing else tells this call that it is designing scene 1 of 4. Left
        blind, the model reaches for the most striking image in the brief and
        stages the story's payoff in the opening shot — observed in the wild as
        a drama that opens on the container already hanging open and glowing,
        then spends four scenes building up to it. The turns of the LATER
        scenes are what must not appear yet; the turns of the earlier ones are
        what must still be true.
        """
        blocks = []
        if (story_so_far or "").strip():
            blocks.append(
                "ALREADY HAPPENED in earlier scenes — still true in this shot:\n"
                f"{story_so_far.strip()}"
            )
        if (not_yet or "").strip():
            blocks.append(
                "HAS NOT HAPPENED YET — must NOT appear in this shot, in any "
                "form, including its aftermath or changed state:\n"
                f"{not_yet.strip()}"
            )
        return "\n".join(blocks) + "\n" if blocks else ""

    @staticmethod
    def _format_character_direction_block(character_direction: str = "") -> str:
        direction = (character_direction or "").strip()
        if not direction:
            return ""
        return (
            "Character performance (what each is playing underneath):\n"
            f"{direction}\n"
        )

    @staticmethod
    def _format_through_line(theme: str = "", visual_motif: str = "") -> str:
        """Drama-wide theme and recurring visual motif.

        Restaging the motif is what makes a set of independently generated
        shots read as one film instead of a slideshow.
        """
        parts = []
        if (theme or "").strip():
            parts.append(f"Theme (the idea every shot should serve): {theme.strip()}")
        if (visual_motif or "").strip():
            parts.append(
                f"Recurring visual motif — restage it in this shot where it "
                f"fits naturally: {visual_motif.strip()}"
            )
        return "\n".join(parts) + "\n" if parts else ""

    @staticmethod
    def _format_dialogue_line(scene_dialogue: str = "") -> str:
        dialogue = (scene_dialogue or "").strip()
        if not dialogue:
            return ""
        return (
            f"Scene dialogue (what is actually said in this moment — stage the "
            f"shot around the most important line):\n{dialogue}\n"
        )

    @staticmethod
    def _format_visual_style(style: str = "") -> str:
        """The drama's look, as a composition instruction.

        The style used to stop at the image model, which meant it could
        change how a frame was PAINTED but never how it was FRAMED — a noir
        and a romance were designed as the same shot with a different word
        in front of it. Cinematic emits nothing: it is the neutral house
        style this prompt already describes, and a note there would only
        restate the default at the cost of tokens.
        """
        look = resolve_visual_style(style)
        if not look.shot_note:
            return ""
        return (
            f"Visual style — compose the shot for it, not just its subject: "
            f"{look.label}. Favour {look.shot_note}. Keep this within the "
            f"director guidance and the locked setting below; it decides "
            f"framing and light, never the place or who is in it.\n"
        )

    @staticmethod
    def _format_setting_line(
        setting_location: str = "",
        setting_time_of_day: str = "",
        setting_era: str = "",
    ) -> str:
        parts = [
            p.strip()
            for p in (setting_location, setting_time_of_day, setting_era)
            if (p or "").strip()
        ]
        if not parts:
            return ""
        return (
            "Setting (LOCKED for entire drama — do not change): "
            + ", ".join(parts)
            + "\n"
        )

    async def _design_with_claude(
        self,
        script: str,
        characters: List[CharacterInScene],
        user_requirement: str,
        guidance: str,
        default_lens: str,
        style: str = "Cinematic",
        setting_location: str = "",
        setting_time_of_day: str = "",
        setting_era: str = "",
        scene_emotion: str = "",
        scene_dialogue: str = "",
        scene_direction: str = "",
        character_direction: str = "",
        theme: str = "",
        visual_motif: str = "",
        user_brief: str = "",
        story_so_far: str = "",
        not_yet: str = "",
        scene_shot_scale: str = "",
    ) -> List[StoryboardShot]:
        try:
            import anthropic

            prompt = self._build_prompt(
                script=script,
                characters=characters,
                user_requirement=user_requirement,
                guidance=guidance,
                default_lens=default_lens,
                style=style,
                setting_location=setting_location,
                setting_time_of_day=setting_time_of_day,
                setting_era=setting_era,
                scene_emotion=scene_emotion,
                scene_dialogue=scene_dialogue,
                scene_direction=scene_direction,
                character_direction=character_direction,
                theme=theme,
                visual_motif=visual_motif,
                user_brief=user_brief,
                story_so_far=story_so_far,
                not_yet=not_yet,
                scene_shot_scale=scene_shot_scale,
            )
            # Same migration as agents/screenwriter.py, for the same two
            # reasons. (1) Sonnet 5 runs adaptive thinking by default, so
            # `content[0]` is a thinking block -- the old
            # `content[0]["text"]` raised `KeyError: 'text'` on every call
            # and silently dropped every scene to the template shot list.
            # Filter blocks by type; never index by position. (2) The old
            # flat 60s httpx deadline with no retries turned a slow or busy
            # upstream into the same silent template fallback.
            client = anthropic.AsyncAnthropic(api_key=self.api_key, max_retries=2)
            async with client.messages.stream(
                model="claude-sonnet-5",
                # Thinking and text share this budget, so the pre-thinking
                # 2048 now leaves very little for the shot list itself.
                max_tokens=self.MAX_SHOT_TOKENS,
                system=system_prompt_for(self.SYSTEM_PROMPT, shots_per_scene()),
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                message = await stream.get_final_message()

            if message.stop_reason == "max_tokens":
                logger.error(
                    "Anthropic storyboard response hit max_tokens "
                    f"({self.MAX_SHOT_TOKENS}) and is truncated mid-JSON; "
                    "falling back to the template shot list."
                )
                return []

            content = next(
                (b.text for b in message.content if b.type == "text"), ""
            )
            match = re.search(r"\[[\s\S]*\]", content)
            if not match:
                logger.error(
                    "Anthropic storyboard response contained no shot list, "
                    f"falling back to template | stop_reason="
                    f"{message.stop_reason} | first 500 chars: {content[:500]!r}"
                )
                return []
            data = json.loads(match.group())
            return [StoryboardShot(**s) for s in data]
        except Exception as exc:
            detail = ""
            resp = getattr(exc, "response", None)
            if resp is not None:
                try:
                    detail = f" | status={resp.status_code} body={resp.text[:500]}"
                except Exception:
                    pass
            logger.error(
                f"Anthropic storyboard call failed, falling back to template: "
                f"{type(exc).__name__}: {exc}{detail}"
            )
            return []

    def _design_template(
        self,
        script: str,
        characters: List[CharacterInScene],
        preset,
        scene_emotion: str = "",
        scene_shot_scale: str = "",
    ) -> List[StoryboardShot]:
        """The deterministic fallback. It honours the framing plan too.

        Not an afterthought: this path runs in demo mode and whenever no LLM
        answers, and a fallback that hardcodes "medium shot" for every scene
        reintroduces the exact defect the plan exists to prevent -- three
        scenes of identical framing -- in the one mode where nothing can be
        blamed on a model.
        """
        char_name = next((c.name for c in characters if c.is_visible), "Character")
        emotion = (scene_emotion or "").strip()
        emotion_clause = f", {emotion}" if emotion else ""
        return [
            StoryboardShot(
                idx=0,
                visual_desc=f"{char_name} — {script[:120]}{emotion_clause}",
                motion_desc=f"{preset.pacing} camera movement, {preset.storyboard_guidance[:80]}",
                expression_desc=emotion,
                audio_desc="ambient atmospheric sound",
                shot_type=(scene_shot_scale or "medium shot"),
                camera_movement="slow push-in" if preset.pacing == "slow" else "tracking shot",
                lens=preset.default_lens,
                duration_seconds=5.0,
            )
        ]
