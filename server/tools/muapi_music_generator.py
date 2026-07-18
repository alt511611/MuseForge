"""MuAPI instrumental background-music generation.

Music generation is a best-effort, optional add-on: if it fails for any
reason (missing endpoint support, API error, timeout), callers should catch
`MuAPIError` (or any exception) and continue the pipeline without music
rather than failing the whole job. See `Idea2VideoPipeline._assemble_final_drama`.
"""

import logging
import os

from tools.muapi_client import MuAPIClient, MuAPIError

logger = logging.getLogger(__name__)

# Real internal cost of one music generation call, expressed in MuseForge
# credits. This is tracked separately from what's charged to the user
# (server/api.py currently charges a flat +1 credit surcharge for
# music_enabled, independent of this constant) so the two can be tuned
# independently as real usage data comes in.
MUSIC_CREDIT_COST = 2

DEMO_MUSIC_URL = ""  # no audio track in demo mode — silent video is fine


class MuAPIMusicGenerator:
    # NOT independently confirmed against MuAPI's first-party docs (unlike
    # flux-dev-image, which was via an exact curl example). "stable-audio-2"
    # is a real Stability AI model (confirmed to exist on Replicate/
    # Stability's own API), chosen because it's purpose-built for
    # instrumental music/sound rather than vocal songs (unlike Suno, which
    # MuAPI also lists but defaults to full songs with vocals). Whether
    # MuAPI hosts it under this exact slug is unconfirmed -- if this fails
    # consistently, check MuAPI's own playground/docs for the correct
    # slug and set MUAPI_MUSIC_MODEL, no code change needed.
    MUSIC_ENDPOINT = os.environ.get("MUAPI_MUSIC_MODEL", "stable-audio-2")

    def __init__(self, api_key: str, demo: bool = False):
        self.demo = demo
        self.client = MuAPIClient(api_key)

    async def generate_instrumental(
        self,
        mood: str,
        duration: int = 30,
    ) -> str:
        """Generate a short instrumental track matching the drama's mood.

        Returns an empty string in demo mode (no music, no error). Raises
        MuAPIError on failure — callers must catch this and continue without
        music rather than crash the job.
        """
        if self.demo:
            return DEMO_MUSIC_URL
        prompt = f"Instrumental background music, {mood} mood, cinematic, no vocals, no lyrics."
        payload = {"prompt": prompt, "duration": duration}
        try:
            return await self.client.generate(self.MUSIC_ENDPOINT, payload, poll_interval=3.0, max_polls=100)
        except MuAPIError as exc:
            logger.warning("Music generation failed, continuing without music: %s", exc)
            raise
