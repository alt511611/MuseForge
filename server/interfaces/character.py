"""Character models for scene and drama consistency."""

from pydantic import BaseModel, Field
from typing import List, Optional, Union


class CharacterInScene(BaseModel):
    idx: int
    name: str
    static_features: str
    dynamic_features: str = ""
    # Costume, carried separately from static_features (face/build/age) so it
    # can be restated in every frame prompt. The identity reference image
    # binds a face, not an outfit.
    wardrobe: str = ""
    is_visible: bool = True
    portrait_url: Optional[str] = None


class CharacterProfile(BaseModel):
    name: str
    description: str
    role: str = "supporting"
    # Wardrobe kept SEPARATE from `description` (face/build/age). The identity
    # reference image binds a face, not an outfit, so wardrobe has to be
    # restated as text in every frame prompt or the costume changes between
    # scenes even when the face holds.
    wardrobe: str = ""
    # Performance direction. want = the external goal the character pursues on
    # screen; need = the internal truth they're avoiding; arc = how they change
    # across the drama. These drive how a beat is PLAYED (what the face does),
    # which is what separates a director's script from a plot summary.
    want: str = ""
    need: str = ""
    arc: str = ""


class DialogueLine(BaseModel):
    character: str
    line: str


#: Narrative function a scene serves. Drives shot scale and duration: setup
#: wants width and air, a climax wants a close-up and time to land.
DRAMATIC_FUNCTIONS = (
    "setup",
    "inciting_incident",
    "rising_action",
    "turning_point",
    "climax",
    "resolution",
)


class ScriptScene(BaseModel):
    action: str
    dialogue: List[DialogueLine] = Field(default_factory=list)
    # Short emotional-beat tag for this scene (e.g. "tearful relief",
    # "cold resentment", "joyful reunion") -- feeds the storyboard artist
    # so shot design (facial expression, body language) matches the story
    # instead of defaulting to a neutral/expressionless read of the action line.
    emotion: str = ""
    # Where this scene sits in the story's shape (see DRAMATIC_FUNCTIONS).
    dramatic_function: str = ""
    # THE most load-bearing field for shot selection: what actually CHANGES in
    # this scene. A scene without a turn is a scene with nothing to film. The
    # storyboard artist draws this moment rather than the surrounding business.
    turn: str = ""
    # What a camera sees become different about the PLACE in this scene, set
    # on the climax scene alone ("every light in the city goes out"). The
    # drama locks one setting and one lighting plan for continuity, which is
    # right for four scenes out of five and fatal for the fifth: a brief whose
    # whole point is "the city's power dies the moment she opens it" rendered
    # under the same streetlights as the opening shot, so the event the film
    # exists for was never on screen. This field is the one sanctioned break
    # in that lock -- and, once it has happened, the state every later scene
    # inherits.
    world_change: str = ""
    # What the characters mean underneath what they say. Drives the played
    # expression when it contradicts the spoken line -- the difference between
    # a face that illustrates dialogue and one that acts against it.
    subtext: str = ""
    # Physical blocking: who is where, what they do with their hands, the
    # object the scene turns on. Gives the frame concrete staging instead of
    # two people abstractly "talking".
    staging: str = ""
    # Dramatic tension 1-10. Shapes the tension curve across the drama and
    # informs shot scale/duration for this beat.
    tension: int = 0


class DramaScript(BaseModel):
    title: str
    logline: str
    # Keep accepting legacy string scenes so stored/demo scripts and existing
    # approve-script payloads remain valid while new scripts carry dialogue.
    scenes: List[Union[str, ScriptScene]] = Field(default_factory=list)
    characters: List[CharacterProfile] = Field(default_factory=list)
    mood: str = "cinematic"
    estimated_duration_seconds: int = 30
    # Once-per-drama setting lock (not per-scene) — injected into every
    # frame/storyboard prompt for time/place consistency.
    setting_location: str = ""
    setting_time_of_day: str = ""
    setting_era: str = ""
    # The controlling idea the drama argues, in one sentence. Keeps every
    # scene pulling in the same direction instead of being three unrelated
    # vignettes that happen to share a room.
    theme: str = ""
    # How this script was produced: "llm" when a model actually wrote it,
    # "template" when every provider failed and the deterministic fallback
    # ran. The fallback ignores the user's idea almost entirely (generic
    # setting, a character named "Alex"), so shipping that silently makes
    # the product look broken for reasons the user cannot see.
    generated_by: str = "llm"
    # The user's prompt, VERBATIM. The script is a lossy re-telling of it --
    # the screenwriter rewrites the brief into its own dramatic structure and
    # drops anything its schema has no field for (a named prop, a required
    # wardrobe item, a demanded cut count, a camera rule). Carrying the
    # original text forward lets the storyboard and frame prompts honour those
    # specifics instead of rendering whatever survived the rewrite.
    user_brief: str = ""
    # One recurring visual element (an object, a gesture, a quality of light)
    # deliberately restaged across scenes. This is what makes a set of shots
    # read as a single film rather than a slideshow.
    visual_motif: str = ""
    # The unanswered question the last frame leaves behind. Written only in
    # micro-drama mode (see interfaces/micro_drama), where a drama that ties
    # itself off has given nobody a reason to come back. Empty in cinematic
    # mode, which resolves on purpose.
    cliffhanger: str = ""
