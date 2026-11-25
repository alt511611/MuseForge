"""Whether the cast's identity references are multi-view SHEETS.

The flag and its reasoning used to live in pipelines/idea2video, which draws
the sheets. It moved here because the RENDER step needs it too, and
pipelines/script2video cannot import from the pipeline that imports it.

What the render step needs it for (pipelines/script2video.wants_first_frame):
a sheet is evidence for an image model and a poor face for a video one. It is
a 2x2 grid of hips-up figures -- four faces, each about an eighth of the
picture's height. Nano Banana reads that as four views of one person and
draws a full-size face from it; that is the case the sheet was switched on
for. A reference-to-video endpoint handed the same grid as the ONLY picture
of the person has nothing that size to hold, and re-derives the face every
generation. Job 6efbb788 (MiniMax H3, reference mode, sheet on) delivered one
character -- Mira, alone in every frame -- as four different women: the two
reference-only shots drew two of them, and only the close-ups, which started
from a rendered frame, came near the sheet.
"""

from __future__ import annotations

import os


def is_enabled() -> bool:
    """MUSEFORGE_CHARACTER_SHEET is truthy.

    OFF by default, and the reason is a real incompatibility rather than
    caution. The original reference model was flux-pulid, an IDENTITY model
    that expects a photograph OF A FACE; a four-panel contact sheet handed to
    it is asking it to lock the identity of a collage.

    What it is for is the reference models that ask for exactly this. Kling's
    element definition takes "up to 4" views of one subject, and Nano Banana
    reads a multi-view sheet as evidence about the same person rather than as
    four people. On those a sheet is strictly more information than one front
    view -- a profile is what stops a character from being redrawn every time
    the camera moves off axis. So it is switched on WITH a backend that can
    use it, and the pairing is the operator's to make.
    """
    return os.environ.get("MUSEFORGE_CHARACTER_SHEET", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
