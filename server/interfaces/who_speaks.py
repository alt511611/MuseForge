"""Whose voice a character speaks in: the video model's, or this film's cast.

Every stage of the soundtrack turns on this one answer, which is why it is a
module and not a boolean somewhere. Answered twice, the two answers disagree,
and a film in which the picture speaks AND the mixer lays down a voice track
is a film in which every line is heard twice, slightly out of phase.

THE TRADE, AND WHY IT IS STILL DECLINED BY DEFAULT. A take with native audio
drives its mouths from the generation that made the picture, so lip sync is
free and exact -- there is no sync pass to run and nothing to go out of step.
What it used to cost was the thing the cast exists for: the voice was chosen
per GENERATION, so one locked portrait could be three different people across
three scenes, which is what job 6f857aa0-903 delivered.

THAT PART HAS CHANGED, AND THE REASONING BELOW USED TO REST ON IT. Read on
2026-09-15, fal's schema for Kling v3 image-to-video had no voice field
anywhere, on the element or on the request -- not a missing catalogue, a
missing field -- and "unsolvable" was a fair word for it. Read again on
2026-09-17, KlingV3ComboElementInput declares `voice_id`, bound per element,
with ids from fal-ai/kling-video/create-voice (which takes a 5-30 second
sample). A multi-shot take with locked faces AND chosen voices is now one
request. The face no longer has to be sold to buy the voice.

So what remains is a real trade rather than a refusal, and it is declined on
its terms, not because the other side is impossible:

  * LANGUAGE. Kling speaks English and Chinese, and its own schema says other
    languages "are automatically translated to English". That is not a
    degraded product, it is a different film, so picture_carries_dialogue
    below gates on it whatever the deployment prefers.
  * COST. Audio off is $0.084 a second; audio on is $0.126; audio on with
    voice control is $0.154. On a 30-second drama that is $2.52 against
    $4.62, where the lip-sync pass it replaces costs about $0.11.
  * THE CAST IS NOT FREE TO MOVE. A character's voice is decided once and
    carried between episodes by tools/elevenlabs_voice_generator.lock_voices.
    The equivalent on this side is creating a voice per character through
    create-voice and persisting the id to the character library. Turning the
    variable below on WITHOUT that gets the old failure back: audio, and a
    voice the take picked for itself.

What it buys is the 30% of wall-clock the sync pass takes (250s of an 822s
render on job a8d0766b-421) and the end of a sync pass that returns 2.6s of a
9s take. A deployment that wants that side sets the variable below, and every
stage follows on its own: the TTS pass, the sync pass, the mixer, what the
frame prompt tells the image model about the mouth, the wall-clock estimate
and the credit quote. Until the voice ids are persisted, it is the trade
without its best half.

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
