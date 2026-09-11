#!/usr/bin/env python
"""Prove the storyboard's system prompt actually caches. Spends real tokens.

`cache_control` is a request to cache, not a cache. A prefix under the model's
minimum cacheable size, or one byte different between calls, is accepted by the
API and then silently does nothing -- same 200, same picture, full price. The
only evidence either way is the usage meters, and code review cannot produce
them.

So this sends the SAME request twice, byte-identical, and prints all four
billed quantities for both. A healthy second call reads its prefix from the
cache and writes nothing.

    ANTHROPIC_API_KEY=sk-ant-... server/.venv/bin/python scripts/cache_probe.py

Two cheap calls at max_tokens=16: the point is the input meters, not the
answer. Exits non-zero when the second call read nothing, so it can gate a
deploy that changed how the prompt is assembled.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import anthropic  # noqa: E402

from agents.storyboard_artist import (  # noqa: E402
    StoryboardArtist,
    shots_per_scene,
    system_prompt_for,
)
from tools.anthropic_request import cached_system  # noqa: E402

MODEL = "claude-sonnet-5"


def _meters(usage):
    return (
        int(getattr(usage, "input_tokens", 0) or 0),
        int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
        int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        int(getattr(usage, "output_tokens", 0) or 0),
    )


async def main() -> int:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("ANTHROPIC_API_KEY is not set; this probe calls the real API.")
        return 2

    # The exact prompt the pipeline sends, assembled the way it assembles it.
    # A probe built from a copy of the prompt proves nothing about the caller.
    system = cached_system(
        system_prompt_for(StoryboardArtist.SYSTEM_PROMPT, shots_per_scene())
    )
    client = anthropic.AsyncAnthropic(api_key=key, max_retries=2)

    results = []
    for attempt in (1, 2):
        message = await client.messages.create(
            model=MODEL,
            max_tokens=16,
            system=system,
            messages=[{"role": "user", "content": "Reply with the word: ok"}],
        )
        regular, written, read, out = _meters(message.usage)
        results.append((written, read))
        print(
            f"call {attempt}: input={regular} cache_write={written} "
            f"cache_read={read} output={out}"
        )

    (first_write, _), (second_write, second_read) = results
    print()
    if second_read:
        print(f"OK: the second call read {second_read} tokens from cache.")
        return 0
    if not first_write:
        print(
            "FAIL: the first call wrote nothing to cache. The prefix is under "
            f"{MODEL}'s minimum cacheable size -- the breakpoint is accepted "
            "and does nothing. Remove it or make the cached prefix larger."
        )
        return 1
    print(
        "FAIL: the first call wrote the prefix and the second read none of "
        "it. The two requests are not byte-identical -- something above the "
        "breakpoint changes between calls."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
