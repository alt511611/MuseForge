"""Storyboard shot models."""

from pydantic import BaseModel, Field
from typing import List, Optional


class StoryboardShot(BaseModel):
    idx: int
    visual_desc: str
    motion_desc: str
    audio_desc: str = ""
    shot_type: str = "medium shot"
    camera_movement: str = "static"
    lens: str = "50mm"
    duration_seconds: float = 5.0
    frame_url: Optional[str] = None
    video_url: Optional[str] = None

    def model_dump(self, **kwargs):
        return super().model_dump(**kwargs)


class Storyboard(BaseModel):
    scene_idx: int
    shots: List[StoryboardShot] = Field(default_factory=list)
    director_style: str = "cinematic_balanced"
