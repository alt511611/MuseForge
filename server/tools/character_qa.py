"""Optional Claude-vision QA for character + setting consistency.

Gated by MUSEFORGE_CHARACTER_QA_ENABLED (default off). Fail-open on any
error so generation is never blocked by QA.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


def is_character_qa_enabled() -> bool:
    return os.environ.get("MUSEFORGE_CHARACTER_QA_ENABLED", "").lower() in (
        "1",
        "true",
        "yes",
    )


def format_expected_setting(
    location: str = "",
    time_of_day: str = "",
    era: str = "",
) -> str:
    """Join non-empty setting parts into a single expected-setting string."""
    return ", ".join(p.strip() for p in (location, time_of_day, era) if (p or "").strip())


def _truncate_issue(issue: str, max_words: int = 15) -> str:
    """Defensively cap the issue text -- the prompt asks for <=15 words but
    nothing stops a model from ignoring that, and this string gets appended
    verbatim into a downstream image-generation prompt."""
    words = (issue or "").strip().split()
    return " ".join(words[:max_words])


async def verify_frame(
    frame_url: str,
    expected_character_desc: str,
    expected_setting: str,
    anthropic_api_key: str,
) -> Dict[str, Any]:
    """Ask Claude vision whether the frame matches character + setting.

    Returns ``{"character_ok": bool, "setting_ok": bool, "issue": str}``.
    ``issue`` is a short (<=15 word) description of what's wrong, populated
    only when either flag is false -- callers use it to target a repair
    regeneration instead of blindly retrying with the same prompt.
    On missing key / network / parse failure: both flags True, issue ""
    (fail-open).
    """
    if not anthropic_api_key or not frame_url:
        return {"character_ok": True, "setting_ok": True, "issue": ""}

    char_hint = (expected_character_desc or "").strip() or "the main character"
    setting_hint = (expected_setting or "").strip() or "the established setting"

    user_text = (
        "You are checking a generated film still for consistency.\n"
        f"Expected character: {char_hint}\n"
        f"Expected setting (location / time / era): {setting_hint}\n"
        "Reply ONLY with JSON: "
        '{"character_ok": true|false, "setting_ok": true|false, "issue": "string"}\n'
        "character_ok=true if the person roughly matches the description. "
        "setting_ok=true if the place/time of day roughly matches. "
        "When unsure, prefer true. "
        "If either flag is false, set issue to ONE short sentence (max 15 "
        "words) describing the SPECIFIC visual problem, e.g. "
        "\"the character's coat color doesn't match the reference\". "
        "If both flags are true, set issue to an empty string."
    )

    try:
        import httpx

        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 256,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "url",
                                        "url": frame_url,
                                    },
                                },
                                {"type": "text", "text": user_text},
                            ],
                        }
                    ],
                },
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"]
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return {"character_ok": True, "setting_ok": True, "issue": ""}
            data = json.loads(match.group())
            character_ok = bool(data.get("character_ok", True))
            setting_ok = bool(data.get("setting_ok", True))
            issue = _truncate_issue(data.get("issue", "")) if not (character_ok and setting_ok) else ""
            return {
                "character_ok": character_ok,
                "setting_ok": setting_ok,
                "issue": issue,
            }
    except Exception as exc:
        logger.warning("character/setting QA failed (fail-open): %s", exc)
        return {"character_ok": True, "setting_ok": True, "issue": ""}
