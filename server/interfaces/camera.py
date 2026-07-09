"""Director style presets for cinematic shot guidance."""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class DirectorStyle:
    label: str
    default_lens: str
    storyboard_guidance: str
    color_grade: str = "neutral"
    pacing: str = "medium"


DIRECTOR_STYLES: Dict[str, DirectorStyle] = {
    "slow_cinematic": DirectorStyle(
        label="Slow Cinematic",
        default_lens="50mm",
        storyboard_guidance=(
            "Use slow, deliberate pacing with long takes and minimal cuts. "
            "Favor wide establishing shots, gentle push-ins, and locked-off frames. "
            "Let silence and negative space breathe between beats."
        ),
        color_grade="desaturated_teal_orange",
        pacing="slow",
    ),
    "cinematic_balanced": DirectorStyle(
        label="Cinematic Balanced",
        default_lens="35mm",
        storyboard_guidance=(
            "Balance wide and medium shots with purposeful cuts. "
            "Mix static frames with subtle camera movement. "
            "Maintain visual rhythm without rushing the narrative."
        ),
        color_grade="natural",
        pacing="medium",
    ),
    "dynamic_action": DirectorStyle(
        label="Dynamic Action",
        default_lens="24mm",
        storyboard_guidance=(
            "Fast cuts, handheld energy, dutch angles for tension. "
            "Use whip pans, crash zooms, and tracking shots. "
            "Keep the viewer on edge with rapid visual changes."
        ),
        color_grade="high_contrast",
        pacing="fast",
    ),
    "intimate_closeup": DirectorStyle(
        label="Intimate Close-Up",
        default_lens="85mm",
        storyboard_guidance=(
            "Prioritize close-ups and extreme close-ups on faces and hands. "
            "Shallow depth of field, soft lighting, emotional micro-expressions. "
            "The camera should feel like it's inside the character's world."
        ),
        color_grade="warm_soft",
        pacing="slow",
    ),
    "noir_mystery": DirectorStyle(
        label="Noir Mystery",
        default_lens="40mm",
        storyboard_guidance=(
            "High-contrast chiaroscuro lighting, deep shadows, venetian blind patterns. "
            "Low angles, silhouettes, rain-slicked surfaces. "
            "Every frame should feel like a clue."
        ),
        color_grade="noir_bw",
        pacing="medium",
    ),
    "anime_expressive": DirectorStyle(
        label="Anime Expressive",
        default_lens="28mm",
        storyboard_guidance=(
            "Bold compositions, speed lines, dramatic reaction shots. "
            "Exaggerated camera angles and vibrant color blocking. "
            "Emotional beats land with visual punctuation."
        ),
        color_grade="vivid_saturated",
        pacing="medium",
    ),
}


def get_director_style(name: str) -> DirectorStyle:
    return DIRECTOR_STYLES.get(name, DIRECTOR_STYLES["cinematic_balanced"])
