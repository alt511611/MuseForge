"""Ask the video backend which ``voice_id`` values its elements accept.

The sibling of tools/probe_dialogue_voices, for the other voice field and the
worse failure mode. On the TTS endpoint a bad id comes back as "Invalid voice
parameter" -- late and expensive, but an ERROR. On a take's element it is not
an error at all: the endpoint substitutes a voice of its own and the drama
ships sounding like somebody else, which is only ever noticed by watching it.
There is no response to read, so the only usable signal is the audio.

That is why this probe RENDERS. Each candidate is one short generation on the
shortest duration the endpoint allows, with one element bound to the id under
test. A run therefore costs real money -- roughly the per-second rate times the
minimum duration, per candidate (interfaces/video_backend declares both) -- and
that is the price of the answer. Nothing cheaper distinguishes "accepted" from
"quietly ignored".

Run from the ``server`` directory with a key in the environment::

    FAL_KEY=... .venv/bin/python -m tools.probe_take_voices \\
        --image https://…/face.png --candidates voice_a,voice_b

What comes back accepted goes into MUSEFORGE_TAKE_VOICE_IDS (and the gendered
variants), which interfaces/take_voices reads per call -- no code change, and
nothing in this repo ever writes an id down as confirmed on its own authority.

LISTEN TO THE RESULTS. An id the library does not hold produces a video, and
this script cannot tell you it was the wrong one. The URLs it prints are the
deliverable: two candidates that sound identical are one voice answering to
two names, and both should not go in the catalogue.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from interfaces.scene_take import Element, plan_scene_take  # noqa: E402
from interfaces.video_backend import backend_for  # noqa: E402

#: What the element says, chosen to be short (the bill is per second) and to
#: carry enough voiced syllables to tell two voices apart by ear.
LINE = "This is the voice you will hear in every scene."


class _Shot:
    """The one angle a probe needs, in the shape plan_scene_take reads."""

    shot_type = "medium"
    visual_desc = "A person speaking directly to camera."
    motion_desc = "The camera holds still."


async def _probe(generator, backend, image_url: str, voice_id: str) -> str:
    """The rendered URL when the backend took the id, else why it did not."""
    take = plan_scene_take(
        backend.duration.minimum,
        [_Shot()],
        backend,
        elements=(Element(name="Probe", images=(image_url,), voice_id=voice_id),),
        start_image=image_url,
        dialogue=[f"PROBE: {LINE}"],
    )
    if take is None:
        return "REJECTED: the backend cannot cut a take at all."
    try:
        return await generator.generate_scene_take(take, generate_audio=True)
    except Exception as exc:  # the message is the whole point of the probe
        return f"REJECTED: {exc}"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image", required=True, help="Portrait URL to bind the voice to."
    )
    parser.add_argument(
        "--candidates",
        required=True,
        help="Comma-separated voice ids to try.",
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get(
            "FALAI_VIDEO_MODEL", "fal-ai/kling-video/v3/standard/image-to-video"
        ),
    )
    args = parser.parse_args()

    backend = backend_for(args.endpoint)
    if not backend.native_audio:
        print(f"{args.endpoint} has no native audio: nothing here to bind.")
        return 2

    from tools.falai_video_generator import FalAIVideoGenerator

    key = os.environ.get("FAL_KEY", "")
    if not key:
        print("FAL_KEY is not set.")
        return 2
    generator = FalAIVideoGenerator(key, multishot=True)

    candidates = [c.strip() for c in args.candidates.split(",") if c.strip()]
    per_probe = backend.cost(backend.duration.minimum)
    print(
        f"{len(candidates)} candidate(s) on {args.endpoint}, "
        f"~${per_probe:.3f} each, ~${per_probe * len(candidates):.2f} total.\n"
    )

    accepted = []
    for voice_id in candidates:
        print(f"--- {voice_id!r}")
        outcome = await _probe(generator, backend, args.image, voice_id)
        print(f"    {outcome}")
        if not outcome.startswith("REJECTED:"):
            accepted.append(voice_id)

    print("\nListen to every URL above before trusting any of it.")
    if accepted:
        print(f"MUSEFORGE_TAKE_VOICE_IDS={','.join(accepted)}")
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
