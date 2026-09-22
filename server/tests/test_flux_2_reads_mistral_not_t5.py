"""Job 5abefcaf-7a49 ran its frames on MUSEFORGE_IMAGE_PROVIDER=falai_multiref
-- fal-ai/flux-2-pro/edit, FLUX.2 -- and every clause the budget dropped was
logged as "against the 512-token T5 window". FLUX.2 does not condition on T5
at all: Black Forest Labs replaced FLUX.1's CLIP+T5-XXL pair with a single
Mistral-Small-3.2-24B text encoder, a different vocabulary entirely. The
number was even right by coincidence (Mistral's own Diffusers pipeline also
caps at 512), but it was 512 T5 pieces of a prompt about to be read by
Mistral, which is not the same measurement wearing a different label -- the
two tokenizers segment the same sentence differently.

This file is the seam: which encoder a frame prompt is actually budgeted
against has to follow the endpoint that will really receive it, not a single
module-wide assumption that everything FLUX is T5.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.t5_budget import (  # noqa: E402
    MISTRAL_FALLBACK_CHARS_PER_TOKEN,
    count_tokens,
    encoder_family,
    tokenizer_is_real,
    window_label,
)

_ENV_KEYS = (
    "MUSEFORGE_IMAGE_PROVIDER",
    "MUAPI_EDIT_MODEL",
    "FALAI_KONTEXT_MODEL",
    "FALAI_FLUX2_EDIT_MODEL",
)


def _clear(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


# --- which family the active endpoint selects ----------------------------


def test_the_unset_deployment_defaults_to_t5(monkeypatch):
    """No provider chosen at all: MuAPI's own default edit endpoint is
    flux-kontext-pro-i2i, still FLUX.1."""
    _clear(monkeypatch)
    assert encoder_family() == "t5"
    assert window_label() == "T5"


def test_falai_single_reference_is_still_kontext_t5(monkeypatch):
    """MUSEFORGE_IMAGE_PROVIDER=falai (not multiref) goes to fal-ai/flux-pro/
    kontext, FLUX.1 Pro Kontext -- unchanged by the flux-2 family existing."""
    _clear(monkeypatch)
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai")
    assert encoder_family() == "t5"


def test_falai_multiref_is_flux_2_mistral(monkeypatch):
    """THE DELIVERED CASE. falai_multiref's edit endpoint is fal-ai/
    flux-2-pro/edit -- FLUX.2, Mistral-conditioned, not T5."""
    _clear(monkeypatch)
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_multiref")
    assert encoder_family() == "mistral"
    assert window_label() == "Mistral"


def test_a_custom_flux2_edit_model_is_still_recognised(monkeypatch):
    """The marker is read off the endpoint that will actually render the
    frame, not off the provider label alone -- an operator can repoint
    FALAI_FLUX2_EDIT_MODEL without also touching MUSEFORGE_IMAGE_PROVIDER."""
    _clear(monkeypatch)
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_multiref")
    monkeypatch.setenv("FALAI_FLUX2_EDIT_MODEL", "fal-ai/flux-2-flex/edit")
    assert encoder_family() == "mistral"


def test_muapi_pointed_directly_at_flux_2_is_also_mistral(monkeypatch):
    """The default MuAPI provider is T5 only because ITS default edit model
    (flux-kontext-pro-i2i) is. Point MUAPI_EDIT_MODEL at the flux-2 family by
    hand and the budget must follow the endpoint, not the vendor label."""
    _clear(monkeypatch)
    monkeypatch.setenv("MUAPI_EDIT_MODEL", "flux-2-pro")
    assert encoder_family() == "mistral"


# --- counting follows the family, and Mistral is never "measured" --------


def test_mistral_family_never_calls_a_t5_tokenizer(monkeypatch):
    """Regardless of whether sentencepiece is installed, a Mistral-bound
    prompt must be counted on the Mistral estimate, never on T5's vocabulary
    -- the two tokenizers are not interchangeable, so falling back to
    "whichever loaded" would silently mismeasure it."""
    _clear(monkeypatch)
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_multiref")

    text = "word " * 100
    expected = int(len(text) / MISTRAL_FALLBACK_CHARS_PER_TOKEN) + 1
    assert count_tokens(text) == expected
    # Never "measured": no Mistral tokenizer is vendored, so this is always
    # an estimate, unconditionally -- not merely when something failed.
    assert tokenizer_is_real() is False


# --- the dropped-clause log names the encoder that is actually reading ---


def test_a_dropped_clause_on_falai_multiref_is_blamed_on_mistral_not_t5(
    caplog, monkeypatch
):
    """The log line a job operator actually reads. Getting the encoder name
    wrong here is what sent job 5abefcaf-7a49 looking at sentencepiece and
    the vendored T5 vocabulary for a budget problem that had nothing to do
    with either."""
    import logging

    from interfaces.character import CharacterInScene
    from pipelines.script2video import build_frame_prompt
    from interfaces.shot import StoryboardShot

    _clear(monkeypatch)
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_multiref")

    characters = [
        CharacterInScene(
            idx=i,
            name=f"Character{i}",
            static_features=(
                "a woman in her early thirties, sharp cheekbones, dark hair "
                "pulled back in a wet knot, tired grey eyes, lean build, a "
                "faded scar across her left eyebrow"
            ),
            is_visible=True,
            wardrobe=(
                "a soaked navy dock parka over a charcoal crew-neck sweater, "
                "steel-toed boots"
            ),
        )
        for i in range(8)
    ]
    shot = StoryboardShot(
        idx=0,
        visual_desc="They crouch at the container seal " + "under the sodium lamp " * 40,
        motion_desc="slow push in",
        expression_desc="jaw set, eyes narrowed against the rain",
        shot_type="medium",
        lens="35mm",
    )

    with caplog.at_level(logging.WARNING):
        build_frame_prompt(
            style="Sci-Fi",
            shot=shot,
            setting_location="a rain-soaked cargo harbour, container stacks and gantry cranes",
            setting_time_of_day="night",
            setting_era="present day",
            has_dialogue=True,
            lipsync_enabled=True,
            characters=characters,
            matched_char=characters[0],
        )

    assert "Mistral window" in caplog.text, caplog.text
    assert "T5 window" not in caplog.text, caplog.text


def test_t5_family_counting_is_unaffected(monkeypatch):
    """The default (T5) path must behave exactly as it did before the
    Mistral family existed -- same estimate ratio, same measured-or-not
    reporting."""
    _clear(monkeypatch)
    from tools import t5_budget

    text = "word " * 100
    if t5_budget.tokenizer_is_real():
        expected = len(t5_budget._tokenizer().encode(text)) + 1
    else:
        expected = int(len(text) / t5_budget.FALLBACK_CHARS_PER_TOKEN) + 1
    assert count_tokens(text) == expected
