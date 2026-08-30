"""A female-led brief rendered as men, twice over, for two new reasons.

interfaces/gender exists so that "a word that counts as female for a voice
must count as female for a face". Delivered job 754796ce-c04, brief:

    "A card dealer in a basement game realises THE MAN across the table is
     copying HER own tell, move for move, and only one of them knows why."

The dealer is the protagonist. Every frame of the delivered film is elderly
men in hats; she is not in her own drama. Two independent faults:

1. THE BRIEF READING NAMED THE ANTAGONIST. gender.infer answers "earliest
   match wins", which is right for a description — one person, led by their
   defining noun — and wrong for a brief, which introduces a cast. Here the
   first marker is "the man", the other player. It returns male for a story
   about "her". _apply_brief_gender would then write "man, ..." into the
   protagonist's description: the repair, applied backwards. It did not fire
   only because the writer had already gendered her, the one case that
   function declines to touch — so this is one ungendered description away
   from making a woman a man on purpose.

2. THE PICTURE WAS NEVER TOLD. _infer_gender is called inside the two voice
   generators and nowhere else; the portrait prompt got the raw description.
   A description carries its gender in one word, often a possessive halfway
   down it — enough for the marker table, not enough for an image model
   reading a genre. That job cast her with a female voice (Laura) and drew
   her, in every frame, as an elderly man.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402
from interfaces import gender as gender_of  # noqa: E402
from interfaces.character import (  # noqa: E402
    CharacterInScene,
    CharacterProfile,
    DramaScript,
)
from pipelines.idea2video import Idea2VideoPipeline  # noqa: E402
from tools.elevenlabs_voice_generator import ElevenLabsVoiceGenerator  # noqa: E402


DELIVERED_BRIEF = (
    "A card dealer in a basement game realises the man across the table is "
    "copying her own tell, move for move, and only one of them knows why."
)


# ── 1. reading the brief ────────────────────────────────────────────────────


def test_the_delivered_brief_reads_as_the_antagonist():
    """The fault, stated. Kept as a test rather than a comment because it is
    the reason infer_brief exists and the thing that must not come back."""
    assert gender_of.infer(DELIVERED_BRIEF) == "male"
    assert gender_of.infer_brief(DELIVERED_BRIEF) == ""


def test_a_brief_that_speaks_of_one_gender_still_answers():
    """The previous delivered brief, which this must not break."""
    harbour = (
        "A dock worker on a rain-soaked cargo harbour finds a shipping "
        "container that hums with light, and the city's power dies the "
        "moment she opens it."
    )
    assert gender_of.infer_brief(harbour) == "female"
    assert gender_of.infer_brief("Two brothers bury their father.") == "male"


def test_a_brief_with_no_gender_answers_nothing_as_before():
    assert gender_of.infer_brief("A container hums with light in an empty yard.") == ""
    assert gender_of.infer_brief("") == ""
    assert gender_of.infer_brief(None) == ""


def test_descriptions_are_not_read_this_way():
    """One person can be described in two genders' words. Voice casting still
    has to answer for her, so `infer` keeps earliest-match-wins."""
    assert gender_of.infer("a woman whose brother died") == "female"
    assert gender_of.infer("man, fifties, his mother's watch") == "male"


def _script(protagonist_description: str, brief: str):
    return DramaScript(
        title="T",
        logline="L",
        user_brief=brief,
        characters=[
            CharacterProfile(
                name="Mara Voss",
                description=protagonist_description,
                role="protagonist",
            )
        ],
    )


def test_the_antagonist_s_gender_is_no_longer_written_onto_the_lead():
    """The delivered brief with an ungendered protagonist — the case that was
    one script away, and that would have made the dealer a man."""
    script = _script("fifties, sharp-eyed, dealer's hands", DELIVERED_BRIEF)
    ScreenwriterAgent._apply_brief_gender(script)

    assert script.characters[0].description == "fifties, sharp-eyed, dealer's hands"


def test_an_unambiguous_brief_still_fills_a_bare_description():
    """The repair itself is untouched: it is only the reading that narrowed."""
    script = _script(
        "thirties, weathered face",
        "A dock worker finds a container, and the power dies when she opens it.",
    )
    ScreenwriterAgent._apply_brief_gender(script)

    assert script.characters[0].description.startswith("woman, ")


# ── 2. telling the picture ──────────────────────────────────────────────────


class _RecordingImages:
    def __init__(self):
        self.prompts = []

    async def generate_image(self, prompt, aspect_ratio="1:1"):
        self.prompts.append(prompt)
        return f"https://cdn/{len(self.prompts)}.png"


def _portraits(*cast, style="Noir"):
    pipeline = Idea2VideoPipeline("test-key")
    pipeline.image_gen = _RecordingImages()
    asyncio.new_event_loop().run_until_complete(
        pipeline._lock_character_portraits(list(cast), style=style)
    )
    return pipeline.image_gen.prompts


def _char(name, features, visible=True):
    return CharacterInScene(
        idx=0,
        name=name,
        static_features=features,
        dynamic_features="",
        is_visible=visible,
    )


def test_a_gender_carried_by_a_possessive_now_leads_the_portrait():
    """The delivered description's shape: the only female word in it is a
    possessive most of the way through."""
    prompt = _portraits(
        _char("Mara Voss", "card dealer, fifties, sharp-eyed, her hands never still")
    )[0]

    assert prompt.startswith("Character portrait of a woman, Noir style.")
    assert "her hands never still" in prompt


def test_a_description_with_no_gender_has_none_invented_for_it():
    """Nothing here guesses. It only repeats what the description already
    said, where the picture can read it."""
    prompt = _portraits(_char("The Stranger", "gaunt, black hat, gloved"))[0]

    assert prompt.startswith("Character portrait, Noir style.")
    assert " of a " not in prompt


def test_the_face_and_the_voice_cannot_answer_differently():
    """The contract interfaces/gender was written for, asserted across the two
    steps that have to keep it -- read off the same string, so even a wrong
    word list is wrong in one direction only."""
    features = "card dealer, fifties, sharp-eyed, her hands never still"

    voices = ElevenLabsVoiceGenerator(api_key="k")
    voices.cast_characters([_char("Mara Voss", features)])
    voiced_female = (
        voices.voice_id_for_character("Mara Voss")
        in ElevenLabsVoiceGenerator.FEMALE_VOICE_IDS
    )

    drawn_female = "of a woman" in _portraits(_char("Mara Voss", features))[0]

    assert voiced_female and drawn_female


def test_a_man_is_still_a_man():
    prompt = _portraits(_char("Otto", "man in his sixties, heavy build"))[0]
    assert prompt.startswith("Character portrait of a man, Noir style.")


def test_a_character_the_film_never_shows_still_gets_no_portrait():
    """Unchanged: this runs before any of it."""
    assert _portraits(_char("Radio", "a voice on the line", visible=False)) == []
