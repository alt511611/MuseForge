"""What the drama LOOKS like — the visual style, in one place.

The style the user picks (Cinematic, Noir, Anime, …) used to be two words
glued to the front of an image prompt and nothing else. Two consequences,
both visible in delivered work:

  * the storyboard step was never told the style at all, so "Noir" and
    "Romance" produced identical shot design and differed only in the image
    model's reading of one word;
  * every frame carried the same photoreal quality suffix — "Shot on 35mm
    film … realistic skin texture with visible pores" — which for Anime is
    an instruction to undo the style in the same breath as asking for it.

So each style now owns two things: a `render_note` (how the picture is
made — the suffix that replaces the blanket photoreal one) and a `shot_note`
(how the shot is composed — a line the storyboard artist actually sees).

Deliberately conservative: styles whose look genuinely IS photoreal keep the
exact suffix they have always had, byte for byte, so nothing about an
existing Cinematic drama moves. A style only diverges where the shared text
was actively wrong for it.
"""

from dataclasses import dataclass
from typing import Dict

#: Always last, in every style: the image models will happily caption a frame.
_NO_TEXT = (
    "No text, captions, subtitles, watermarks or logos anywhere in the frame."
)

#: The look every live drama has been rendered with. Unchanged on purpose --
#: it is correct for a live-action film, and it is what "Cinematic" means.
PHOTOREAL_RENDER = (
    "Shot on 35mm film, natural filmic grain, realistic skin texture with "
    "visible pores, catchlights in the eyes, anatomically correct hands, "
    "sharp focus on the face with natural depth of field. " + _NO_TEXT
)

ANIME_RENDER = (
    "Hand-drawn 2D anime artwork: clean confident ink linework, flat cel "
    "shading with hard-edged light and shadow, expressive stylised eyes, "
    "painted background art, anatomically correct hands. Not photorealistic "
    "— no film grain, no skin pores, no photographic texture. " + _NO_TEXT
)


@dataclass(frozen=True)
class VisualStyle:
    label: str
    #: Appended to the image prompt: how the picture is MADE.
    render_note: str = PHOTOREAL_RENDER
    #: Given to the storyboard artist: how the shot is COMPOSED. Empty for
    #: Cinematic, which is the neutral house style the prompt already assumes
    #: — a note there would only restate what it does by default.
    shot_note: str = ""

    @property
    def is_photoreal(self) -> bool:
        """True when this style renders as live action.

        Used to leave photoreal styles completely untouched where a look note
        would otherwise be added: they already render correctly, and the only
        thing a redundant note can do is move a picture that was right.
        """
        return self.render_note == PHOTOREAL_RENDER


STYLES: Dict[str, VisualStyle] = {
    "cinematic": VisualStyle(label="Cinematic"),
    "noir": VisualStyle(
        label="Noir",
        shot_note=(
            "hard-edged shadow and strong key/fill contrast, low or canted "
            "angles, tight framing, a practical light source inside the frame"
        ),
    ),
    "sci-fi": VisualStyle(
        label="Sci-Fi",
        shot_note=(
            "clean geometry and scale contrast between the figure and the "
            "architecture around them, cold practical light sources in frame"
        ),
    ),
    "fantasy": VisualStyle(
        label="Fantasy",
        shot_note=(
            "painterly depth with distinct foreground, middle and far layers, "
            "atmospheric haze, the figure placed small against the world"
        ),
    ),
    "horror": VisualStyle(
        label="Horror",
        shot_note=(
            "negative space that could be hiding something, off-centre "
            "framing, foreground occlusion, the camera held a beat too close"
        ),
    ),
    "romance": VisualStyle(
        label="Romance",
        shot_note=(
            "shallow focus and closer framing on faces and hands, warm "
            "practical light, the distance between two people as the subject"
        ),
    ),
    "documentary": VisualStyle(
        label="Documentary",
        shot_note=(
            "observational eye-level framing as if the moment were unstaged "
            "and the camera merely present, available light, no posing"
        ),
    ),
    "anime": VisualStyle(
        label="Anime",
        render_note=ANIME_RENDER,
        shot_note=(
            "bold graphic composition with a strong silhouette read, "
            "decisive angles, generous negative space around the subject"
        ),
    ),
}

#: An unknown or empty style renders exactly as before rather than erroring:
#: a legacy job, a demo script, or a style added to the client before the
#: server knows about it must still produce a picture.
DEFAULT = VisualStyle(label="Cinematic")


def resolve(name: str) -> VisualStyle:
    """The look for a style name, case- and whitespace-insensitively."""
    return STYLES.get((name or "").strip().casefold(), DEFAULT)
