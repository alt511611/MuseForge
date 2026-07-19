"""Call Claude through MuAPI's unified LLM endpoint, using the same
submit-and-poll infrastructure already used for image/video generation
(tools/muapi_client.py).

IMPORTANT CAVEAT: MuAPI's exact endpoint slug/response schema for its LLM
models isn't fully confirmed from first-party documentation at the time
this was written -- their playground page advertises "Claude via a single
API" but the precise request/response shape for text models (vs. their
well-documented image/video submit-and-poll pattern) wasn't independently
verifiable. MUAPI_LLM_MODEL is therefore an env-configurable guess
("claude-sonnet-4-5" by default) rather than a hardcoded certainty.

Because of that uncertainty, every caller of this module MUST catch
MuAPIError (or any Exception) and fall back to another path (direct
Anthropic call, then template). This module never raises past its own
call site in a way that would break generation if the guess is wrong --
see agents/screenwriter.py and agents/storyboard_artist.py for the
fallback chain.
"""

import os
from typing import Optional

from tools.muapi_client import MuAPIClient, MuAPIError

MUAPI_LLM_MODEL = os.environ.get("MUAPI_LLM_MODEL", "claude-sonnet-4-5")


async def complete_via_muapi(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
    api_key: Optional[str] = None,
) -> str:
    """Returns the raw text response, or raises MuAPIError on any failure
    (missing key, wrong endpoint slug, unexpected response shape, timeout).
    Callers must catch this and fall back."""
    key = api_key or os.environ.get("MUAPI_KEY", "")
    if not key:
        raise MuAPIError("MUAPI_KEY is not configured")

    client = MuAPIClient(api_key=key)
    payload = {
        "prompt": user_prompt,
        "system_prompt": system_prompt,
        "max_tokens": max_tokens,
    }
    text = await client.generate(MUAPI_LLM_MODEL, payload)
    # generate() already returns a single string (the first output). If
    # MuAPI's actual response schema for text models differs from its
    # media-generation schema, this may be empty or malformed -- the
    # caller's except-block falls back in that case, see module docstring.
    if not text:
        raise MuAPIError("MuAPI LLM call returned no output")
    return text
