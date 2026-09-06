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
was asked for and what will run instead.

EVERY stage says which vendor it resolved to, including the ones that resolved
to the default because nothing was set. That looks like noise and is not. The
job above ran entirely on MuAPI for the plainest reason there is -- four of the
five fal.ai selectors were never added to the deployment at all, and the fifth
(voice) was, which is exactly why voice is the one stage that switched. An
operator who sets one variable and believes they have moved the pipeline gets
no contradiction from a log that only speaks when spoken to. Six lines a job,
against a stage that can bill for minutes, is what makes "which vendor rendered
this?" a question the log answers.
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

    if choice and choice not in known:
        logger.warning(
            "%s is set to %r, which is not a backend this build knows "
            "(%s) — %s will run on %r instead.",
            env_var,
            raw,
            ", ".join(known),
            label,
            default,
        )
        return default

    if not choice:
        # The line that would have answered the delivered job in one look.
        # An unset selector is the shipped default AND the shape of "I meant
        # to switch this and never did", and those two must not look the same
        # in a log.
        logger.info("%s runs on %r (%s is not set).", label, default, env_var)
        return default

    logger.info("%s runs on %r (%s=%r).", label, choice, env_var, raw)
    return choice
