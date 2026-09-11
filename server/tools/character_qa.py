"""Optional Claude-vision QA for character + setting consistency.

Gated by MUSEFORGE_CHARACTER_QA_ENABLED (default off). Fail-open on any
error so generation is never blocked by QA.
"""

from __future__ import annotations

import json
import logging
import os
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
        "character_ok=true if the person roughly matches the description. "
        "setting_ok=true if the place/time of day roughly matches. "
        "When unsure, prefer true.\n"
        # `issue` is not a report. It is appended verbatim to the frame
        # prompt as "IMPORTANT CORRECTION: ..." and re-sent to the image
        # model (see script2video's audit-and-repair), so it is read by a
        # diffusion model, which has no NOT: "the coat colour doesn't match"
        # names the wrong coat and asks for it again. The correction has to
        # say what the picture should CONTAIN.
        "If either flag is false, set issue to ONE short instruction (max 15 "
        "words) saying what the frame should show instead -- it is sent "
        "straight back to the image model as a correction, so write what IS "
        "wanted, never what is wrong. Write \"her coat is moss green\", not "
        "\"the coat colour doesn't match\". "
        "If both flags are true, set issue to an empty string."
    )

    try:
        import anthropic

        from tools.anthropic_request import classify, log_usage, refusal_of

        client = anthropic.AsyncAnthropic(api_key=anthropic_api_key, max_retries=2)
        message = await client.messages.create(
            model="claude-sonnet-5",
            # Thinking off, deliberately. This is a two-boolean visual check
            # that runs once per generated frame, so latency and cost per
            # call matter more than deliberation. It also has to be explicit:
            # Sonnet 5 thinks by default, and since `max_tokens` covers
            # thinking plus text, the old 256 left nothing for the answer.
            thinking={"type": "disabled"},
            # The same argument as the line above, said in the parameter the
            # current API has for it. Thinking being off does not by itself
            # ask for a short answer -- effort governs the overall spend, and
            # the answer wanted here is two booleans and at most a fifteen
            # word sentence. This is the highest-VOLUME call in the pipeline:
            # one per generated frame, where the others are one per job and
            # one per scene.
            output_config={
                "effort": "low",
                # The answer's SHAPE is now the API's guarantee rather than a
                # sentence in the prompt and a regex underneath it. The
                # "Reply ONLY with JSON" line and the brace-hunting
                # `re.search` were the two halves of one workaround for
                # something the Messages API does natively.
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "character_ok": {"type": "boolean"},
                            "setting_ok": {"type": "boolean"},
                            "issue": {"type": "string"},
                        },
                        "required": ["character_ok", "setting_ok", "issue"],
                        "additionalProperties": False,
                    },
                },
            },
            max_tokens=512,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "url", "url": frame_url},
                        },
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )
        # Select the text block by type. Reading content[0] blindly is what
        # made this check die with `KeyError: 'text'` -- and because the QA
        # fails open, it died silently and every frame passed unchecked.
        log_usage("frame_qa", "claude-sonnet-5", getattr(message, "usage", None))

        # A refusal is an HTTP 200 with no answer in it. Fail-open is right
        # here -- a QA that cannot run must not block a frame -- but it has
        # to be LOUD: this reads as "every frame passed" in the results and
        # is nothing of the kind.
        declined = refusal_of(message)
        if declined:
            logger.error(
                "character/setting QA was DECLINED (category=%s); the frame "
                "is passing UNCHECKED, not verified.", declined,
            )
            return {"character_ok": True, "setting_ok": True, "issue": ""}

        text = next((b.text for b in message.content if b.type == "text"), "")
        # output_config.format guarantees this block is valid JSON matching
        # the schema, so there is nothing to hunt for and nothing to forgive.
        data = json.loads(text)
        character_ok = bool(data.get("character_ok", True))
        setting_ok = bool(data.get("setting_ok", True))
        issue = _truncate_issue(data.get("issue", "")) if not (character_ok and setting_ok) else ""
        return {
            "character_ok": character_ok,
            "setting_ok": setting_ok,
            "issue": issue,
        }
    except Exception as exc:
        # Fail-open is deliberate and stays. What was wrong was the LEVEL: a
        # warning, once per frame, identical for a malformed JSON reply and
        # for a key that will reject every frame of every job. A failure that
        # cannot fix itself is an error, and it says so -- otherwise the QA
        # reports a whole film verified while never having run.
        failure = classify(exc)
        if failure.kind in ("auth", "not_found", "request"):
            logger.error(
                "character/setting QA cannot run at all (%s) -- every frame "
                "is passing UNCHECKED: %s", failure.kind, failure.detail,
            )
        elif failure.retryable:
            logger.warning(
                "character/setting QA failed this frame (%s, worth retrying), "
                "frame passing unchecked: %s", failure.kind, failure.detail,
            )
        else:
            logger.warning("character/setting QA failed (fail-open): %s", exc)
        return {"character_ok": True, "setting_ok": True, "issue": ""}
