"""Upload finished videos to Supabase Storage and return a signed URL.

Uses the same httpx + service-key pattern as server/auth.py / server/jobs.py.
No extra SDKs (no boto3, no supabase-py).

Demo mode / missing env → return the local path unchanged (no network).
Upload failure → log and return the local path (fail-open).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
STORAGE_BUCKET = os.environ.get("MUSEFORGE_STORAGE_BUCKET", "videos")
SIGNED_URL_TTL_SECONDS = int(os.environ.get("MUSEFORGE_SIGNED_URL_TTL", str(7 * 24 * 3600)))


def _is_demo() -> bool:
    return os.environ.get("MUSEFORGE_DEMO", "").lower() in ("1", "true", "yes")


def _storage_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_SERVICE_KEY)


def _headers(content_type: Optional[str] = None) -> dict:
    h = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    if content_type:
        h["Content-Type"] = content_type
    return h


async def upload_video(local_path: str, job_id: str) -> str:
    """Upload ``local_path`` to the private ``videos`` bucket as ``{job_id}.mp4``.

    Returns a signed HTTPS URL on success. In demo mode, when Supabase is not
    configured, or on any upload/sign failure, returns ``local_path`` unchanged
    (fail-open, logged).
    """
    if not local_path or not os.path.isfile(local_path):
        logger.error("upload_video: local file missing: %s", local_path)
        return local_path or ""

    if _is_demo() or not _storage_configured():
        # Match tools/muapi_uploader.py — no network in demo / local-dev.
        return local_path

    object_path = f"{job_id}.mp4"
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{STORAGE_BUCKET}/{object_path}"
    sign_url = f"{SUPABASE_URL}/storage/v1/object/sign/{STORAGE_BUCKET}/{object_path}"

    try:
        file_bytes = Path(local_path).read_bytes()
        async with httpx.AsyncClient(timeout=120.0) as client:
            upload_resp = await client.post(
                upload_url,
                content=file_bytes,
                headers={
                    **_headers("video/mp4"),
                    "x-upsert": "true",
                },
            )
            upload_resp.raise_for_status()

            sign_resp = await client.post(
                sign_url,
                json={"expiresIn": SIGNED_URL_TTL_SECONDS},
                headers=_headers("application/json"),
            )
            sign_resp.raise_for_status()
            data = sign_resp.json()
            signed = data.get("signedURL") or data.get("signedUrl") or ""
            if not signed:
                raise ValueError(f"No signedURL in response: {data}")

            if signed.startswith("http"):
                return signed
            # Supabase returns a path like /object/sign/...?token=...
            if not signed.startswith("/"):
                signed = "/" + signed
            if signed.startswith("/storage/v1"):
                return f"{SUPABASE_URL}{signed}"
            return f"{SUPABASE_URL}/storage/v1{signed}"

    except Exception as exc:
        logger.error(
            "upload_video failed for job %s (keeping local path): %s",
            job_id,
            exc,
        )
        return local_path
