"""Character models for scene and drama consistency."""

from pydantic import BaseModel, Field
from typing import List, Optional


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


class DramaScript(BaseModel):
    title: str
    logline: str
    scenes: List[str] = Field(default_factory=list)
    characters: List[CharacterProfile] = Field(default_factory=list)
    mood: str = "cinematic"
    estimated_duration_seconds: int = 30
