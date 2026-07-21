"""Character models for scene and drama consistency."""

from pydantic import BaseModel, Field
from typing import List, Optional, Union


class CharacterInScene(BaseModel):
    idx: int
    name: str
    static_features: str
    dynamic_features: str = ""
    is_visible: bool = True
    portrait_url: Optional[str] = None


class CharacterProfile(BaseModel):
    name: str
    description: str
    role: str = "supporting"


class DialogueLine(BaseModel):
    character: str
    line: str


class ScriptScene(BaseModel):
    action: str
    dialogue: List[DialogueLine] = Field(default_factory=list)


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
