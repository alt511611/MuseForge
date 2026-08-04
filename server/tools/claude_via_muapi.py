"""Call Claude through MuAPI's unified LLM endpoint, using the same
submit-and-poll infrastructure already used for image/video generation
(tools/muapi_client.py).

IMPORTANT CAVEAT: MuAPI's exact endpoint slug/response schema for its LLM
models isn't fully confirmed from first-party documentation at the time
this was written -- their playground page advertises "Claude via a single
API" but the precise request/response shape for text models (vs. their
well-documented image/video submit-and-poll pattern) wasn't independently
verifiable.

Because the slug was only ever a GUESS, this path is now OPT-IN: it runs
only when MUAPI_LLM_MODEL is explicitly configured. Left on by default it
was the PRIMARY path for both the screenwriter and the storyboard artist,
so every job began with a submit-and-poll round trip that could only fail,
and any weakness further down the fallback chain (a missing
ANTHROPIC_API_KEY, a quota error) landed the user on the deterministic
template -- a video that ignores their prompt entirely. A guess must not
sit in front of the path that actually works.

Every caller MUST still catch MuAPIError (or any Exception) and fall back,
since the guess can be wrong even when configured -- see
agents/screenwriter.py and agents/storyboard_artist.py.
"""

import os
from typing import Optional

from tools.muapi_client import MuAPIClient, MuAPIError

#: Empty by default -- see the module docstring. Set it (e.g.
#: MUAPI_LLM_MODEL=claude-sonnet-4-6) only once the slug is confirmed
#: against a real MuAPI account.
MUAPI_LLM_MODEL = os.environ.get("MUAPI_LLM_MODEL", "")


def is_muapi_llm_enabled() -> bool:
    """True only when an operator has explicitly named a MuAPI LLM slug."""
    return bool(os.environ.get("MUAPI_LLM_MODEL", "").strip())


async def complete_via_muapi(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 2048,
    api_key: Optional[str] = None,
) -> str:
    """Returns the raw text response, or raises MuAPIError on any failure
    (missing key, wrong endpoint slug, unexpected response shape, timeout).
    Callers must catch this and fall back."""
    model = os.environ.get("MUAPI_LLM_MODEL", "").strip() or MUAPI_LLM_MODEL
    if not model:
        raise MuAPIError(
            "MUAPI_LLM_MODEL is not configured -- MuAPI's LLM slug is a guess "
            "and this path is opt-in; using the Anthropic path instead"
        )

    key = api_key or os.environ.get("MUAPI_KEY", "")
    if not key:
        raise MuAPIError("MUAPI_KEY is not configured")

    client = MuAPIClient(api_key=key)
    payload = {
        "prompt": user_prompt,
        "system_prompt": system_prompt,
        "max_tokens": max_tokens,
    }
    text = await client.generate(model, payload)
    # generate() already returns a single string (the first output). If
    # MuAPI's actual response schema for text models differs from its
    # media-generation schema, this may be empty or malformed -- the
    # caller's except-block falls back in that case, see module docstring.
    if not text:
        raise MuAPIError("MuAPI LLM call returned no output")
    return text
