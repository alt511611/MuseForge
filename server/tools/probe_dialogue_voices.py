"""Ask MuAPI what it actually accepts for ``voice_id``, one word at a time.

Every wrong guess about this field has cost a whole drama: the request is
accepted, five scenes are generated, and the video arrives silent with the
provider's explanation truncated in a warning. Nothing in the provider's
OpenAPI spec lists the allowed values, so the only way to know is to ask it.

Run from the ``server`` directory with a key in the environment::

    MUAPI_KEY=... python -m tools.probe_dialogue_voices

Each candidate sends ONE word to the dialogue endpoint, so a successful probe
costs a fraction of a scene; a rejected one costs nothing. Whatever comes back
accepted goes into ``MUSEFORGE_VOICE_IDS`` (and the gendered variants), which
the generator reads at import -- no code change needed to unbreak voice.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.muapi_client import MuAPIClient  # noqa: E402
from tools.muapi_voice_generator import MuAPIVoiceGenerator  # noqa: E402

#: The two forms this file has shipped. Both were written down as confirmed;
#: one of them silenced every drama for two paid renders, so the probe tries
#: them side by side rather than trusting either.
ID_FORM = MuAPIVoiceGenerator.SYSTEM_VOICE_IDS
LABEL_FORM = (
    "George - Warm",
    "Sarah - Soft",
    "Brian - Deep, Resonant and Comforting",
    "Charlotte - Clear",
    "Callum - Husky Trickster",
    "Laura - Enthusiast, Quirky Attitude",
)
#: The provider's own documented default for the sibling TTS endpoint, so a
#: run that rejects everything still says whether ANY voice works.
RACHEL = "21m00Tcm4TlvDq8ikWAM"


async def _probe(client: MuAPIClient, endpoint: str, voice_id: str) -> str:
    """"" when the provider accepted the voice, else why it did not."""
    try:
        await client.generate(
            endpoint,
            {"dialogue": [{"text": "Hello.", "voice_id": voice_id}], "stability": 0.5},
            poll_interval=2.0,
            max_polls=60,
        )
    except Exception as exc:  # the message is the whole point of the probe
        return str(exc)
    return ""


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint",
        default=MuAPIVoiceGenerator.VOICE_ENDPOINT,
        help="dialogue endpoint to probe",
    )
    parser.add_argument(
        "voices",
        nargs="*",
        help="voice values to try; default: the shipped cast, then the old "
        "display labels, then the provider's own documented default",
    )
    args = parser.parse_args()

    if not (os.environ.get("MUAPI_KEY") or "").strip():
        print("MUAPI_KEY is not set -- nothing to ask.", file=sys.stderr)
        return 2

    candidates = list(args.voices) or [ID_FORM[0], LABEL_FORM[0], RACHEL]
    client = MuAPIClient(os.environ["MUAPI_KEY"])

    accepted = []
    for voice_id in candidates:
        print(f"\n--- {voice_id!r}")
        reason = await _probe(client, args.endpoint, voice_id)
        if reason:
            print(f"    REJECTED: {reason}")
        else:
            accepted.append(voice_id)
            print("    ACCEPTED")

    print("\n" + "=" * 60)
    if not accepted:
        print("Nothing was accepted. The rejection above is the provider's own")
        print("wording -- it usually names the allowed values or the account")
        print("setting that is missing.")
        return 1
    print("Accepted:", ", ".join(repr(v) for v in accepted))
    print("Put the working form in .env, e.g.:")
    print("  MUSEFORGE_VOICE_IDS=" + ",".join(accepted))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
