"""A character sheet, cut back into the views it was drawn as.

The sheet is drawn as ONE picture: "a 2x2 grid of the SAME person, four views
-- front, three-quarter left, profile, three-quarter right"
(pipelines/idea2video.CHARACTER_SHEET_DIRECTION). The multi-shot take's
element wants those views as SEPARATE pictures -- a frontal image and up to
three more angles (interfaces/scene_take.Element), which its own docstring
calls "exactly the shape MUSEFORGE_CHARACTER_SHEET produces". It was never
handed that shape. ``Element(images=(portrait,))`` made the whole grid the
frontal view: four small figures in one frame as the picture of one face, and
no additional angles at all.

This cuts the grid into its quadrants, in reading order (front, three-quarter
left, profile, three-quarter right -- the order the sheet is asked for), and
uploads each. That is the frontal and three angles the element was designed
for, each face four times the area it had as a quarter of the grid.

Fail-open: any failure -- no key, a download, a decode, an upload -- returns
an empty tuple, and the caller sends the sheet whole, exactly as before.
"""

from __future__ import annotations

import io
import logging
import os
import tempfile
from typing import Tuple

logger = logging.getLogger(__name__)

#: Below this a quadrant is too small to be worth sending as its own view.
MIN_PANEL_PIXELS = 256

#: How far from square a picture may be and still be read as a sheet.
#:
#: Every sheet this pipeline draws is 1:1 (_lock_character_portraits asks for
#: it), and the flag cannot tell a drawn sheet from a reference PHOTO a user
#: uploaded for the same character -- both arrive as "the portrait". Cutting a
#: photograph into quarters would hand the take four fragments of one face. A
#: phone photo is 3:4, 4:3 or 9:16; a square one is the rare case this lets
#: through, and it costs that character four crops instead of one picture.
SQUARE_TOLERANCE = 0.02


def quadrants(width: int, height: int) -> Tuple[Tuple[int, int, int, int], ...]:
    """The four crop boxes of a 2x2 grid, in reading order."""
    half_w, half_h = width // 2, height // 2
    return (
        (0, 0, half_w, half_h),
        (half_w, 0, width, half_h),
        (0, half_h, half_w, height),
        (half_w, half_h, width, height),
    )


async def split_sheet(url: str, client=None) -> Tuple[str, ...]:
    """The sheet's four views as uploaded URLs, or () to send it whole."""
    if not url:
        return ()
    try:
        import httpx
        from PIL import Image

        if client is None:
            from tools.falai_common import make_fal_client

            key = (os.environ.get("FAL_KEY", "") or "").strip()
            if not key:
                return ()
            client = make_fal_client(key)

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as http:
            response = await http.get(url)
            response.raise_for_status()
            data = response.content

        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGB")
            width, height = image.size
            if abs(width / float(height) - 1.0) > SQUARE_TOLERANCE:
                return ()
            if min(width, height) // 2 < MIN_PANEL_PIXELS:
                return ()
            urls = []
            with tempfile.TemporaryDirectory(prefix="sheet_views_") as workdir:
                for index, box in enumerate(quadrants(width, height)):
                    path = os.path.join(workdir, f"view_{index}.jpg")
                    image.crop(box).save(path, quality=95)
                    urls.append(await client.upload_file(path))
        return tuple(u for u in urls if u) if all(urls) else ()
    except Exception as exc:
        logger.warning("Could not cut the character sheet into views; sending it whole: %s", exc)
        return ()
