"""How many tokens the image model will actually read of a prompt.

FLUX conditions on T5, which truncates its text input at 512 tokens and does
it SILENTLY -- no error, no log line, no failed render. A prompt past the cap
comes back as a finished frame that was drawn from part of its instructions,
and nothing downstream can tell that from a frame the model simply disagreed
with.

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
    """
    return _tokenizer() is not None


def count_tokens(text: str) -> int:
    """Tokens T5 will read of `text`, including the EOS it appends.

    The +1 is not padding. T5 terminates every sequence with `</s>`, so a
    prompt measured at exactly 512 pieces is 513 tokens at the encoder and
    loses its last piece -- which, in a prompt ordered by priority, is the
    cheapest clause, but only because of how this module's callers order it.
    """
    if not text:
        return 0
    sp = _tokenizer()
    if sp is None:
        return int(len(text) / FALLBACK_CHARS_PER_TOKEN) + 1
    return len(sp.encode(text)) + 1


def fits(text: str, limit: int = MAX_PROMPT_TOKENS) -> bool:
    return count_tokens(text) <= limit
