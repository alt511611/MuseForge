"""Storyboard shot models."""

from pydantic import BaseModel, Field
from typing import List, Optional


class StoryboardShot(BaseModel):
    idx: int
    visual_desc: str
    motion_desc: str
    # Explicit facial-expression / body-language beat for this shot. Kept as
    # its own field (rather than relying on it being buried inside
    # visual_desc) so build_frame_prompt can always surface the emotion to
    # the image model -- a report of "scene looks neutral/emotionless"
    # traced back to expression never reliably reaching the frame prompt.
    expression_desc: str = ""
    # Where the expression LANDS by the end of the shot. Filled deterministically
    # from interfaces/acting, never by the LLM: it is the target of the
    # start-to-end frame interpolation (see the end-frame path in
    # pipelines/script2video), so it has to be the same beat on every render of
    # the same scene -- a re-shoot that re-acts the film is not a re-shoot.
    expression_peak_desc: str = ""
    audio_desc: str = ""
    shot_type: str = "medium shot"
    camera_movement: str = "static"
    lens: str = "50mm"
    # Seconds REQUESTED from the video model. Under flat per-generation
    # billing this is not what the scene costs and not what it delivers --
    # see interfaces/shot_plan.
    duration_seconds: float = 5.0
    # Seconds that reach the timeline, when that is less than what was
    # generated. 0 means "deliver the whole clip", which is every shot in a
    # single-angle scene and therefore the overwhelming majority of them.
    deliver_seconds: float = 0.0
    # "master" or "reaction". Decides which model animates the shot and
    # whether the scene is left alone by the post-cut pacing pass -- a scene
    # that bought a real second angle must not also be cut into digital ones.
    role: str = "master"
    frame_url: Optional[str] = None
    video_url: Optional[str] = None

    def model_dump(self, **kwargs):
        return super().model_dump(**kwargs)


class Storyboard(BaseModel):
    scene_idx: int
    shots: List[StoryboardShot] = Field(default_factory=list)
    director_style: str = "cinematic_balanced"
