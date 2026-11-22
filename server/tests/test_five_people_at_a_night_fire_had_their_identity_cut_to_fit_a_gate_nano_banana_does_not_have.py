"""Five people at a night fire had their descriptions cut to fit a gate Nano
Banana does not have, and the log never said so.

Delivered job d7fde8c8-37f8-4741-9ead-8606ec90a2d9. Two crowded frames came
back from the storyboard at 3066 and 3169 characters and the log answered
each with the same line:

    Frame prompt at 3169 against the 3000-char provider budget — dropping
    262 chars of lower-priority direction

3000 is MuAPI's validator, and it binds the FLUX families that MuAPI serves.
Nano Banana is a Gemini model on fal, whose `prompt` field accepts 50,000
characters, so for a frame bound there the gate was a number copied from a
different vendor -- and #161 had corrected only HALF of that: the token window
became 2048 for Gemini while the character gate stayed 3000. That gate is also
what sizes the identity reserve (`identity_budget` in build_frame_prompt), so a
scene of three or more described characters -- face, wardrobe, wet clothes, a
fire's light on each -- had its identity sentence squeezed toward the 150-char
floor to fit it.

What that costs is the reported drift: "a bald man in a leather jacket" and "a
long-haired woman in a bandana" are what a prompt says when the shortening
reached the faces. And it could not be confirmed from the log, because neither
the reserve nor the token loop printed a word. Both are covered here: the
limits follow the provider family, and a shortened identity sentence is now a
line with both ends of the shortening in it.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.character import CharacterInScene  # noqa: E402
from interfaces.shot import StoryboardShot  # noqa: E402
from pipelines.script2video import (  # noqa: E402
    MAX_IMAGE_PROMPT_CHARS,
    build_frame_prompt,
    fit_image_prompt,
)
from tools.t5_budget import (  # noqa: E402
    GEMINI_MAX_PROMPT_CHARS,
    GEMINI_MAX_PROMPT_TOKENS,
    MAX_PROMPT_CHARS,
    MAX_PROMPT_TOKENS,
    count_tokens,
    max_prompt_chars,
    max_prompt_tokens,
)

#: Five people at a night camp, each described the way a screenwriter does it:
#: a face that is more than a line and a garment that is more than a colour.
CAST = [
    (
        "Deniz",
        "man in his early thirties, lean and sunburnt, close-cropped dark hair, "
        "a split lip healing at one corner, wary brown eyes that never settle",
        "salt-stiffened grey canvas jacket, soaked through, sleeves rolled to "
        "the elbow over a torn navy undershirt",
    ),
    (
        "Mara",
        "woman in her late twenties, long chestnut hair knotted back with a "
        "frayed red bandana, freckled, a small silver ring through one nostril",
        "oversized yellow oilskin coat gone dark with rain, rope belt, bare "
        "forearms wrapped in strips of cloth",
    ),
    (
        "Kemal",
        "heavyset man in his fifties, completely bald, thick grey beard cut "
        "square, a keloid scar crossing his left cheek",
        "brown leather jacket cracked at the shoulders, wet wool trousers, one "
        "boot laced with wire",
    ),
    (
        "Yusuf",
        "boy of about fourteen, wide dark eyes, ears too large for his head, "
        "chapped cheeks, hair flattened by the rain",
        "a man's army sweater hanging to his knees, sleeves pushed up, a "
        "plastic bag tied around one wet shoe",
    ),
    (
        "Arif",
        "old man in his seventies, white stubble, deep creases around the "
        "mouth, cloudy left eye, a hearing aid held on with tape",
        "threadbare tweed waistcoat over a collarless shirt, a blanket "
        "around the shoulders pinned with a fishhook",
    ),
]

SETTING = (
    "a gravel beach at night, a driftwood fire throwing orange light across "
    "five wet faces, the black sea breathing behind them"
)


def _characters():
    return [
        CharacterInScene(
            idx=i, name=n, static_features=d, dynamic_features="",
            wardrobe=w, is_visible=True,
        )
        for i, (n, d, w) in enumerate(CAST)
    ]


def _night_scene_prompt():
    characters = _characters()
    shot = StoryboardShot(
        idx=0,
        visual_desc=(
            "The five of them close around the fire, steam lifting off their "
            "clothes, Deniz on his heels at the front, Mara's hand cupped "
            "around the last match, Kemal hunched behind her, Yusuf watching "
            "the dark over her shoulder and old Arif wrapped in his blanket."
        ),
        motion_desc="slow push-in",
        expression_desc="exhausted, guarded",
        shot_type="wide shot",
        lens="35mm",
    )
    return build_frame_prompt(
        style="Cinematic",
        shot=shot,
        setting_location=SETTING,
        setting_time_of_day="night",
        setting_era="present day",
        has_dialogue=False,
        lipsync_enabled=False,
        characters=characters,
        matched_char=characters[0],
    )


@pytest.fixture
def gemini(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_nanobanana")


# ── the limits follow the family ────────────────────────────────────────────


def test_gemini_reads_4000_tokens_and_8000_characters(gemini):
    assert max_prompt_tokens() == GEMINI_MAX_PROMPT_TOKENS == 4000
    assert max_prompt_chars() == GEMINI_MAX_PROMPT_CHARS == 8000


@pytest.mark.parametrize(
    "provider, endpoint",
    [
        ("muapi", None),
        ("falai", None),
        ("falai_multiref", None),
    ],
)
def test_every_other_family_keeps_its_old_limits(monkeypatch, provider, endpoint):
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", provider)
    assert max_prompt_tokens() == MAX_PROMPT_TOKENS == 512
    assert max_prompt_chars() == MAX_PROMPT_CHARS == MAX_IMAGE_PROMPT_CHARS == 3000


def test_the_default_gate_is_read_when_the_prompt_is_fitted_not_when_the_module_loads(
    monkeypatch,
):
    """`limit=MAX_IMAGE_PROMPT_CHARS` as a default argument froze the FLUX gate
    at import, so a provider switch could never reach it."""
    long_tail = "an optional direction that runs on and on and on. " * 120
    segments = [(0, "Cinematic style. Deniz on the beach. "), (6, long_tail)]

    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "muapi")
    assert len(fit_image_prompt(segments)) <= 3000

    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "falai_nanobanana")
    gemini_prompt = fit_image_prompt(segments)
    assert 3000 < len(gemini_prompt) <= 8000
    assert count_tokens(gemini_prompt) <= 4000


# ── the identity sentence is not cut ────────────────────────────────────────


def test_a_five_character_night_scene_keeps_every_face_and_garment_whole(
    gemini, caplog
):
    """The reported drift, at the cast that produced it. Every character's
    description and wardrobe must be in the prompt word for word -- not a
    compacted "bald man, leather jacket"."""
    with caplog.at_level(logging.INFO, logger="pipelines.script2video"):
        prompt = _night_scene_prompt()

    for name, features, wardrobe in CAST:
        assert features in prompt, f"{name}'s description was cut"
        assert wardrobe in prompt, f"{name}'s wardrobe was cut"

    assert len(prompt) <= 8000
    assert count_tokens(prompt) <= 4000
    assert "Identity clause shrunk" not in caplog.text, caplog.text
    assert "provider budget" not in caplog.text, (
        "a Gemini frame was still dropping clauses against MuAPI's gate"
    )


def test_the_same_scene_on_flux_is_still_compacted_and_says_so(
    monkeypatch, caplog
):
    """The limits are per family, so the 3000-char gate still binds MuAPI --
    and a shortened identity sentence there is no longer silent."""
    monkeypatch.setenv("MUSEFORGE_IMAGE_PROVIDER", "muapi")
    with caplog.at_level(logging.INFO, logger="pipelines.script2video"):
        prompt = _night_scene_prompt()

    assert len(prompt) <= 3000
    assert count_tokens(prompt) <= 512

    shrunk = [r for r in caplog.records if "Identity clause shrunk" in r.getMessage()]
    assert shrunk, "five described characters did not fit and nothing was logged"
    message = shrunk[0].getMessage()
    assert "for 5 character(s)" in message
    assert "512-token T5 window" in message
    # Both ends of the shortening are in the line, so it can be read as a
    # claim: from N to M, with M smaller.
    before, after = (
        int(x) for x in message.split("shrunk from ")[1].split(" chars")[0].split(" to ")
    )
    assert after < before
