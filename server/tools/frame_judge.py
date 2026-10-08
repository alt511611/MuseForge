"""Phase 0 of best-of-N frame selection: score ONE frame against the portraits
it was drawn from, and say so in the log. Nothing is regenerated.

Gated by MUSEFORGE_FRAME_JUDGE (default off). Fail-open on every error: this
measures the pipeline, it must never be able to stop it.

Unlike character_qa.verify_frame, which compares a frame to a TEXT description,
this one is shown the locked portraits themselves. "Is that the same woman" is
a question about two pictures.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional, Sequence

from interfaces.frame_choice import DIMENSIONS, clean_scores

logger = logging.getLogger(__name__)

MODEL = os.environ.get("MUSEFORGE_FRAME_JUDGE_MODEL", "claude-sonnet-5")

#: More than this and the images, not the question, are what is being paid for.
MAX_REFERENCES = 3


def is_frame_judge_enabled() -> bool:
    return os.environ.get("MUSEFORGE_FRAME_JUDGE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def judge_frame(
    frame_url: str,
    reference_urls: Sequence[str],
    expected_character_desc: str,
    expected_wardrobe: str,
    expected_setting: str,
    anthropic_api_key: str,
) -> Optional[Dict[str, Any]]:
    """Score ``frame_url`` 0-3 on each of ``interfaces.frame_choice.DIMENSIONS``.

    Returns ``{"scores": {...}, "note": str}``, or None when the judge could not
    run or declined -- never a made-up pass.
    """
    refs = [u for u in (reference_urls or []) if u][:MAX_REFERENCES]
    if not anthropic_api_key or not frame_url:
        return None

    text = (
        "You are judging ONE generated film still against the reference pictures "
        "it was drawn from. The reference pictures come first (the first is the "
        "locked portrait of the lead; a later one may be the empty set), then the "
        "frame to judge.\n"
        f"Lead's look: {(expected_character_desc or 'not stated').strip()}\n"
        f"Lead's outfit: {(expected_wardrobe or 'as in the reference portrait').strip()}\n"
        f"Expected setting: {(expected_setting or 'as in the set reference').strip()}\n"
        "Score each 0-3 (3 = unmistakably right, 0 = plainly wrong):\n"
        "- identity: the lead's face matches the first reference portrait.\n"
        "- outfit: the lead wears the same clothes, in colour and material.\n"
        "- setting: the place and time match the expected setting.\n"
        "- face_readable: the lead's face is visible and unobscured, mouth clear "
        "enough that its lips could be animated to speech.\n"
        "- cast_closed: no recognisable face other than the cast appears.\n"
        "note: ONE short sentence (max 15 words) naming the worst fault, or empty."
    )
    content: list = [{"type": "image", "source": {"type": "url", "url": u}} for u in refs]
    content.append({"type": "image", "source": {"type": "url", "url": frame_url}})
    content.append({"type": "text", "text": text})

    try:
        import anthropic

        from tools.anthropic_request import classify, log_usage, refusal_of

        client = anthropic.AsyncAnthropic(api_key=anthropic_api_key, max_retries=2)
        message = await client.messages.create(
            model=MODEL,
            thinking={"type": "disabled"},
            output_config={
                "effort": "low",
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            **{d: {"type": "integer"} for d in DIMENSIONS},
                            "note": {"type": "string"},
                        },
                        "required": [*DIMENSIONS, "note"],
                        "additionalProperties": False,
                    },
                },
            },
            max_tokens=512,
            messages=[{"role": "user", "content": content}],
        )
        log_usage("frame_judge", MODEL, getattr(message, "usage", None))

        declined = refusal_of(message)
        if declined:
            logger.warning("frame judge was DECLINED (category=%s); no score.", declined)
            return None

        body = next((b.text for b in message.content if b.type == "text"), "")
        data = json.loads(body)
        scores = clean_scores(data)
        if scores is None:
            logger.warning("frame judge returned an incomplete verdict; no score.")
            return None
        return {"scores": scores, "note": " ".join(str(data.get("note", "")).split()[:15])}
    except Exception as exc:
        failure = classify(exc)
        if failure.kind in ("auth", "not_found", "request"):
            logger.error(
                "frame judge cannot run at all (%s) -- no frame is being scored: %s",
                failure.kind,
                failure.detail,
            )
        else:
            logger.warning("frame judge failed for this frame (no score): %s", exc)
        return None
