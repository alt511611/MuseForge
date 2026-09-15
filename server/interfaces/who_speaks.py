"""Whose voice a character speaks in: the video model's, or this film's cast.

Every stage of the soundtrack turns on this one answer, which is why it is a
module and not a boolean somewhere. Answered twice, the two answers disagree,
and a film in which the picture speaks AND the mixer lays down a voice track
is a film in which every line is heard twice, slightly out of phase.

THE TRADE, AND WHY IT IS DECLINED BY DEFAULT. A take with native audio drives
its mouths from the generation that made the picture, so lip sync is free and
exact -- there is no sync pass to run and nothing to go out of step. What it
cannot do is the thing the cast exists for. The voice is chosen per
GENERATION, so one locked portrait can be three different people across three
scenes, which is what job 6f857aa0-903 delivered. And it cannot be told
otherwise: fal's published schema for Kling v3 standard and pro
image-to-video (read 2026-09-15) has no voice field anywhere, on the element
or on the request. Not a missing catalogue -- a missing field.

Kling's voice control is real and is somewhere else: v2.6 PRO takes a
request-level `voice_ids` of at most two, from fal-ai/kling-video/create-voice
(which does accept a 5-30 second sample). That endpoint has neither
multi_prompt nor elements, so reaching those voices costs the multi-shot take
and the character element lock -- the face, to buy the voice.

So the picture is rendered mute and the TTS cast does the speaking, where a
character's voice is decided once and carried between episodes
(tools/elevenlabs_voice_generator.lock_voices). Giving up a solved problem for
an unsolvable one is the wrong way round. A deployment that wants the other
side of the trade -- free perfect sync, on a film whose characters may change
voice at a cut -- sets the variable below, and every stage follows on its own:
the TTS pass, the sync pass, the mixer, what the frame prompt tells the image
model about the mouth, the wall-clock estimate and the credit quote.

This is a PREFERENCE, which is why it is here and not in
interfaces/video_backend: that registry states what an endpoint can do, and
"none of them is a preference". Kling v3 can still speak. We decline.
"""

import os

NATIVE_AUDIO_ENV = "MUSEFORGE_TAKE_NATIVE_AUDIO"

_TRUE = frozenset({"1", "true", "yes", "on"})


def picture_may_speak() -> bool:
    """Whether this deployment lets a take carry its own dialogue."""
    return (os.environ.get(NATIVE_AUDIO_ENV, "") or "").strip().lower() in _TRUE


def picture_carries_dialogue(backend, language: str) -> bool:
    """Whether THIS film's spoken lines come out of the video model.

    Three terms, and the pipeline used to ask only the first two: a backend
    that cuts its own scenes, a backend that speaks this film's LANGUAGE (an
    endpoint with English audio is not "an endpoint with native audio" to a
    Turkish drama), and a deployment that wants the trade above.
    """
    return bool(
        backend is not None and backend.speaks(language) and picture_may_speak()
    )
