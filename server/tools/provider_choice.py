"""Which vendor a stage runs on, read the same way everywhere.

Six stages pick a backend from an environment variable, and until now each
one read its own variable its own way. Three normalised the value
(``.strip().lower()``) and three compared the raw string:

    voice, lip sync, sfx     (os.environ.get(...) or "").strip().lower()
    image, video, music       os.environ.get(...) == "falai"

The three that did not normalise fall back to MuAPI on anything but an exact
lowercase match -- so ``FALAI``, ``Falai`` or a ``falai`` with the trailing
newline a dashboard paste leaves behind selects nothing, changes nothing, and
says nothing. Delivered job 1ac6d945-b53 ran every image, video and lip-sync
call on MuAPI while its VOICE went to ElevenLabs, which is exactly the split
this difference produces: the one stage that normalised its variable is the
one stage that switched.

An unrecognised value is worse than a wrong one. ``MUSEFORGE_VIDEO_PROVIDER
=fal`` is not a typo the deployment ever finds out about: it renders, it bills,
it succeeds, and it does all of that on the vendor the operator was trying to
leave. So a value that does not name a known backend is a WARNING naming what
was asked for and what will run instead, and a value that does is an INFO
line -- because "I flipped the provider and nothing changed" should be
answerable from the job log rather than by reading this file.

Silent only when the variable is unset, which is the shipped default and must
stay as quiet as it has always been.
"""

from __future__ import annotations

import logging
import os
from typing import Sequence

logger = logging.getLogger(__name__)


def resolve_provider(
    env_var: str,
    known: Sequence[str],
    default: str,
    stage: str = "",
) -> str:
    """The backend this stage runs on: normalised, validated, and logged.

    ``known`` lists every value this stage accepts, ``default`` is the one an
    unset (or unrecognised) variable resolves to. Returns a member of
    ``known``, so callers can compare against bare strings and a typo can no
    longer look like a deliberate default.
    """
    raw = os.environ.get(env_var, "")
    choice = (raw or "").strip().lower()
    label = stage or env_var

    if not choice:
        return default

    if choice not in known:
        logger.warning(
            "%s is set to %r, which is not a backend this build knows "
            "(%s) — %s will run on %r instead. Nothing else will say so.",
            env_var,
            raw,
            ", ".join(known),
            label,
            default,
        )
        return default

    # Said even when it resolves to the default, because "I set it and it
    # still ran on MuAPI" and "I set it to MuAPI" are the same log line
    # otherwise, and only one of them is a bug.
    logger.info("%s runs on %r (%s=%r).", label, choice, env_var, raw)
    return choice
