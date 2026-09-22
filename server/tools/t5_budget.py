"""How many tokens the image model will actually read of a prompt.

FLUX.1 conditions on T5, which truncates its text input at 512 tokens and
does it SILENTLY -- no error, no log line, no failed render. A prompt past
the cap comes back as a finished frame that was drawn from part of its
instructions, and nothing downstream can tell that from a frame the model
simply disagreed with.

FLUX.2 (fal-ai/flux-2-pro/edit, MuAPI's flux-2-pro family) does not condition
on T5 at all -- see encoder_family() below and MISTRAL_FALLBACK_CHARS_PER_TOKEN
for what changes when the active image endpoint is that family instead.

This module exists because the alternative was arithmetic over character
counts, and that arithmetic was wrong in both directions. Job 01a0a502's
frames were assumed to be at 3.5 characters per token and are at 3.98; the
window they were being sized against was ~250 characters too tight, while the
prompts themselves were 198 tokens too long. A budget that is wrong in both
directions at once cannot be corrected by choosing a better constant -- it has
to be measured.

THE VOCABULARY IS VENDORED, at assets/t5_spiece.model: the same
`spiece.model` published for google/t5-v1_1-xxl, which is the text encoder
FLUX.1 uses. It is checked in (773 KB, Apache-2.0) rather than fetched, so a
render sized against it does not depend on a network call, a cache directory,
or a hub that is up. A tokenizer that sometimes loads is a budget that
sometimes applies.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

#: T5's sequence cap, which is what FLUX conditions on.
MAX_PROMPT_TOKENS = 512

#: The vendored vocabulary. Same file google/t5-v1_1-xxl publishes.
SPIECE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets",
    "t5_spiece.model",
)

#: Measured on this repo's own delivered prompts (job 01a0a502: 2828
#: characters, 710 tokens). Used ONLY when the tokenizer cannot be loaded, and
#: deliberately pessimistic against that measurement -- a fallback that
#: under-counts hands back exactly the silent overrun this module exists to
#: end, so it errs toward calling a prompt too long rather than too short.
FALLBACK_CHARS_PER_TOKEN = 3.6

#: FLUX.2 (fal-ai/flux-2-pro/edit and MuAPI's flux-2-pro family) does not
#: condition on T5 at all -- Black Forest Labs replaced the CLIP+T5-XXL pair
#: FLUX.1 used with a single Mistral-Small-3.2-24B-Instruct text encoder, a
#: different model reading a different (BPE) vocabulary. Counting a
#: FLUX.2-bound prompt against the vendored T5 SentencePiece model is not an
#: approximation of the real count -- the two tokenizers segment the same
#: sentence differently, so the number produced is a measurement of an
#: encoder the prompt is not going to. Job 5abefcaf-7a49 ran its frames on
#: MUSEFORGE_IMAGE_PROVIDER=falai_multiref (fal-ai/flux-2-pro/edit) and
#: still had every clause budgeted and logged as "the 512-token T5 window".
#:
#: No Mistral tokenizer is vendored the way T5's is (see SPIECE_PATH) --
#: Tekken's vocabulary is not checked into this repo -- so a FLUX.2-bound
#: prompt is always ESTIMATED, never measured. The ratio below is a plain
#: chars-per-token estimate for BPE tokenization of English prose (roughly
#: what GPT/tiktoken-family tokenizers average), shaded pessimistic for the
#: same reason FALLBACK_CHARS_PER_TOKEN is: a ratio that under-counts chars
#: per token cuts a clause a little early rather than overrunning silently.
MISTRAL_FALLBACK_CHARS_PER_TOKEN = 3.5

#: Endpoint slugs (bare, or the tail after a vendor prefix like
#: "fal-ai/flux-2-pro/edit") that select the FLUX.2 / Mistral family. Read
#: off tools/muapi_image_generator.py's and tools/falai_image_generator.py's
#: own endpoint tables -- this module does not import either (both pull in
#: tools.provider_choice and, transitively, a paid client) so the marker
#: list is kept here as the single fact both would otherwise have to agree
#: on separately.
_MISTRAL_ENDPOINT_MARKERS = ("flux-2-pro", "flux-2-flex", "flux-2-dev")


def _reference_endpoint() -> str:
    """The endpoint that will actually receive a frame prompt.

    Frame prompts carry the character and costume locks, which only the
    REFERENCE/edit call reads (build_character_identity_clause and friends
    in pipelines/script2video.py) -- so this mirrors the resolution
    tools/muapi_image_generator.py and tools/falai_image_generator.py do
    for THAT call, not the plain text-to-image one. Reads the same env vars
    directly rather than importing either generator, both of which pull in
    tools.provider_choice and a paid HTTP client this module has no other
    reason to load.
    """
    provider = os.environ.get("MUSEFORGE_IMAGE_PROVIDER", "").strip().lower()
    if provider == "falai_multiref":
        return os.environ.get("FALAI_FLUX2_EDIT_MODEL", "fal-ai/flux-2-pro/edit")
    if provider == "falai":
        return os.environ.get("FALAI_KONTEXT_MODEL", "fal-ai/flux-pro/kontext")
    return os.environ.get("MUAPI_EDIT_MODEL", "flux-kontext-pro-i2i")


def encoder_family() -> str:
    """"mistral" or "t5" -- which text encoder the active image provider's
    reference/edit endpoint conditions on, and therefore which budget this
    frame prompt is actually being measured against."""
    endpoint = _reference_endpoint().strip().lower()
    if any(marker in endpoint for marker in _MISTRAL_ENDPOINT_MARKERS):
        return "mistral"
    return "t5"


def window_label() -> str:
    """"T5" or "Mistral", for a log line that says which window this is."""
    return "Mistral" if encoder_family() == "mistral" else "T5"


_lock = threading.Lock()
_processor = None
_load_failed = False


def _tokenizer():
    """The SentencePiece processor, loaded once, or None if it cannot be.

    Failure is logged once and then remembered: a missing tokenizer is a
    deployment fact, not a transient one, and re-attempting it on every frame
    of every film would bury the one line that explains the degraded budget.
    """
    global _processor, _load_failed
    if _processor is not None or _load_failed:
        return _processor
    with _lock:
        if _processor is not None or _load_failed:
            return _processor
        try:
            import sentencepiece as spm

            _processor = spm.SentencePieceProcessor(model_file=SPIECE_PATH)
        except Exception as exc:
            _load_failed = True
            logger.error(
                "T5 tokenizer unavailable (%s): frame prompts will be budgeted "
                "from an estimate of %.2f chars/token instead of measured. "
                "Install sentencepiece and check %s.",
                exc,
                FALLBACK_CHARS_PER_TOKEN,
                SPIECE_PATH,
            )
    return _processor


def tokenizer_is_real() -> bool:
    """Whether the budget is being measured rather than estimated.

    Exposed so a caller can say which of the two it did -- the difference
    decides whether dropping a clause is a measurement acting or a guess
    acting, and those deserve different log lines.

    False for the Mistral family unconditionally: there is no vendored
    Mistral tokenizer to measure with (see MISTRAL_FALLBACK_CHARS_PER_TOKEN),
    so a FLUX.2-bound prompt is estimated every time, not merely when
    something failed to load.
    """
    return encoder_family() == "t5" and _tokenizer() is not None


def count_tokens(text: str) -> int:
    """Tokens the active image encoder will read of `text`.

    Branches on encoder_family(): FLUX.2's Mistral encoder has no vendored
    tokenizer, so that family is always a chars-per-token estimate; FLUX.1's
    T5 is measured with the vendored vocabulary when it loads, and estimated
    the same way otherwise. The two fallback ratios are calibrated
    separately (FALLBACK_CHARS_PER_TOKEN vs MISTRAL_FALLBACK_CHARS_PER_TOKEN)
    because they stand in for different tokenizers.

    The +1 on the T5 path is not padding. T5 terminates every sequence with
    `</s>`, so a prompt measured at exactly 512 pieces is 513 tokens at the
    encoder and loses its last piece -- which, in a prompt ordered by
    priority, is the cheapest clause, but only because of how this module's
    callers order it.
    """
    if not text:
        return 0
    if encoder_family() == "mistral":
        return int(len(text) / MISTRAL_FALLBACK_CHARS_PER_TOKEN) + 1
    sp = _tokenizer()
    if sp is None:
        return int(len(text) / FALLBACK_CHARS_PER_TOKEN) + 1
    return len(sp.encode(text)) + 1


def fits(text: str, limit: int = MAX_PROMPT_TOKENS) -> bool:
    return count_tokens(text) <= limit
