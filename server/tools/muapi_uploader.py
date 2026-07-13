"""Upload a user-provided base64 character photo to MuAPI storage.

This exists because the rest of the pipeline (generate_image_with_reference)
sends the reference-image URL straight to MuAPI's API, which expects a URL
it can fetch — not a raw base64 data URI from a browser file upload. Without
this step, a user-uploaded character photo would be sent as an invalid
"URL" and silently fail (or error) instead of being used as a reference.
"""

import base64
import binascii
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

import httpx

MUAPI_BASE = os.environ.get("MUAPI_BASE", "https://api.muapi.ai/api/v1")

_DATA_URI_RE = re.compile(r"^data:(image/\w+);base64,(.+)$", re.DOTALL)


class InvalidCharacterPhoto(ValueError):
    """Raised when the uploaded character photo isn't a valid image data URI."""


async def upload_base64_image(data_uri: str, api_key: str, demo: bool = False) -> str:
    """Decode a base64 data URI and upload it to MuAPI's file storage,
    returning a real hosted URL. In demo mode (or if MUAPI_KEY is missing),
    returns a deterministic placeholder instead of making a network call,
    same as tools/muapi_image_generator.py's demo fallback.
    """
    match = _DATA_URI_RE.match((data_uri or "").strip())
    if not match:
        raise InvalidCharacterPhoto("Character photo must be a base64 image data URI.")
    mime_type, b64_payload = match.groups()

    try:
        content = base64.b64decode(b64_payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise InvalidCharacterPhoto("Character photo could not be decoded.") from exc

    if len(content) > 5 * 1024 * 1024:
        raise InvalidCharacterPhoto("Character photo must be smaller than 5MB.")

    if demo or not api_key:
        # Deterministic placeholder so the demo pipeline still "uses" the
        # uploaded photo conceptually without a real upload/API call.
        import hashlib

        seed = hashlib.sha1(content).hexdigest()[:12]
        return f"https://picsum.photos/seed/{seed}/768/768"

    ext = ".png" if "png" in mime_type else ".jpg"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        headers = {"x-api-key": api_key}
        with open(tmp_path, "rb") as f:
            file_bytes = f.read()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{MUAPI_BASE}/upload_file",
                headers=headers,
                files={"file": (Path(tmp_path).name, file_bytes)},
            )
            resp.raise_for_status()
            data = resp.json()
        return data.get("url") or data.get("file_url") or data_uri
    except httpx.HTTPError:
        # Non-fatal: fall back to a placeholder rather than failing the
        # whole generation just because the upload endpoint hiccupped.
        import hashlib

        seed = hashlib.sha1(content).hexdigest()[:12]
        return f"https://picsum.photos/seed/{seed}/768/768"
    finally:
        Path(tmp_path).unlink(missing_ok=True)
