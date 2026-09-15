"""The cast keeps a face for a whole drama and used to lose the voice at a cut.

One locked portrait carries a character through every scene. Then a take with
native audio picks its own voice per GENERATION, so job 6f857aa0-903 -- one
woman, three scenes -- rolled the model's dice three times for who she sounded
like. The failure the cast exists to prevent, moved from the face to the voice.

The endpoint's element takes a `voice_id` from the backend's own library, so
closing it means choosing one of ITS voices per character and binding the same
one every time. What this module pins is that choice: gender-matched from the
same markers the FACE was drawn from, deterministic in the character's name,
never shared by two characters inside one film, and -- the part that is not
like the TTS cast -- never invented.

The catalogue ships EMPTY on purpose. The provider does not publish the valid
ids, and this field does not refuse a wrong one: it substitutes in silence. So
an empty catalogue binds nothing and warns, which is the behaviour that was
already there; a filled one is the deployment's own answer, obtained by
tools/probe_take_voices. Nothing here writes an id down on its own authority.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces import take_voices  # noqa: E402


class _Character:
    def __init__(self, name, static_features=""):
        self.name = name
        self.static_features = static_features


MARA = _Character("Mara Voss", "woman in her mid-thirties, weathered face")
KEMAL = _Character("Kemal", "a man in his fifties, dock foreman")
NOBODY = _Character("Ari", "thirties, shaved head")


@pytest.fixture
def catalogue(monkeypatch):
    """A deployment that has probed its backend and written down the answer."""
    monkeypatch.setenv("MUSEFORGE_TAKE_FEMALE_VOICE_IDS", "fem-a,fem-b")
    monkeypatch.setenv("MUSEFORGE_TAKE_MALE_VOICE_IDS", "mal-a,mal-b")
    monkeypatch.delenv("MUSEFORGE_TAKE_VOICE_IDS", raising=False)


@pytest.fixture
def no_catalogue(monkeypatch):
    for name in (
        "MUSEFORGE_TAKE_VOICE_IDS",
        "MUSEFORGE_TAKE_FEMALE_VOICE_IDS",
        "MUSEFORGE_TAKE_MALE_VOICE_IDS",
    ):
        monkeypatch.delenv(name, raising=False)


# --- the default: nothing invented -----------------------------------------


def test_a_deployment_that_has_probed_nothing_binds_nothing(no_catalogue):
    """Today's behaviour, kept: the model chooses and the log says so."""
    assert take_voices.cast([MARA, KEMAL]) == {}


def test_the_catalogue_is_never_shipped_with_ids_in_it():
    """A guessed id is not refused, it is substituted -- so none is written.

    Read off the module rather than argued: the only ids this file may ever
    hold come from the environment.
    """
    import inspect

    source = inspect.getsource(take_voices)

    assert 'os.environ.get(variable, "")' in source
    assert "MUSEFORGE_TAKE_VOICE_IDS" in source


# --- casting ---------------------------------------------------------------


def test_a_woman_is_cast_from_the_women_s_voices(catalogue):
    assert take_voices.cast([MARA])["Mara Voss"].startswith("fem-")


def test_a_man_is_cast_from_the_men_s_voices(catalogue):
    assert take_voices.cast([KEMAL])["Kemal"].startswith("mal-")


def test_a_character_whose_gender_the_script_left_open_is_still_cast(catalogue):
    """Unlike the TTS path, which can leave them to a per-line hash.

    There is no per-line anything here: an unbound element is the model
    choosing again on every generation, which is the whole failure. A
    consistent voice of an uncertain gender beats an inconsistent one.
    """
    assert take_voices.cast([NOBODY])["Ari"] in take_voices.known_ids()


def test_the_same_character_is_cast_the_same_way_every_time(catalogue):
    assert take_voices.cast([MARA]) == take_voices.cast([MARA])


def test_two_characters_never_share_a_voice_inside_one_film(catalogue):
    """The collision worth spending a worse-matched voice to avoid."""
    voices = take_voices.cast([_Character(f"Woman {n}", "a woman") for n in range(2)])

    assert len(set(voices.values())) == 2


def test_a_cast_larger_than_the_catalogue_still_casts_everyone(catalogue):
    """Running out of voices is a duplicate, never a character left unbound."""
    voices = take_voices.cast([_Character(f"Woman {n}", "a woman") for n in range(4)])

    assert len(voices) == 4
    assert set(voices) == {f"Woman {n}" for n in range(4)}


def test_the_voice_is_keyed_by_the_name_the_element_is_built_with(catalogue):
    """script2video reads voice_ids.get(name) with the DISPLAY name.

    A casefolded key here -- which is what the TTS cast uses -- would not
    raise. It would miss, and ship a take the model voiced.
    """
    assert "Mara Voss" in take_voices.cast([MARA])


# --- returning characters --------------------------------------------------


def test_a_returning_character_keeps_the_voice_her_first_episode_gave_her(
    catalogue,
):
    voices = take_voices.cast([MARA], locked={"Mara Voss": "fem-b"})

    assert voices["Mara Voss"] == "fem-b"


def test_a_voice_from_another_provider_s_library_is_not_bound(catalogue):
    """The library's voice_id field holds whichever provider was current.

    An ElevenLabs id on a Kling element is not a wrong voice, it is an unknown
    one, and unknown here means silently substituted. Dropped and re-cast
    instead: a voice that changes between episodes can at least be heard.
    """
    voices = take_voices.cast([MARA], locked={"Mara Voss": "FGY2WhTYpPnrIDTdsKH5"})

    assert voices["Mara Voss"] in take_voices.known_ids()


def test_a_locked_voice_is_not_handed_to_a_second_character_as_well(catalogue):
    voices = take_voices.cast(
        [MARA, _Character("Deniz", "a woman")], locked={"Mara Voss": "fem-a"}
    )

    assert voices["Deniz"] != "fem-a"


# --- the catalogue itself --------------------------------------------------


def test_a_deployment_that_only_knows_which_ids_work_still_casts(monkeypatch):
    """Gendered lists fall back to the shared one: consistency first."""
    monkeypatch.setenv("MUSEFORGE_TAKE_VOICE_IDS", "any-a,any-b")
    monkeypatch.delenv("MUSEFORGE_TAKE_FEMALE_VOICE_IDS", raising=False)
    monkeypatch.delenv("MUSEFORGE_TAKE_MALE_VOICE_IDS", raising=False)

    voices = take_voices.cast([MARA, KEMAL])

    assert set(voices.values()) == {"any-a", "any-b"}


def test_a_duplicated_id_does_not_become_two_voices(monkeypatch):
    monkeypatch.setenv("MUSEFORGE_TAKE_VOICE_IDS", "a, a ,b")

    assert take_voices.catalogue() == (("a", "b"), ("a", "b"))


def test_the_catalogue_is_read_per_call_not_pinned_at_import(monkeypatch):
    """A worker whose configuration is reloaded must not keep the old cast."""
    monkeypatch.setenv("MUSEFORGE_TAKE_VOICE_IDS", "a")
    assert take_voices.known_ids() == {"a"}

    monkeypatch.setenv("MUSEFORGE_TAKE_VOICE_IDS", "b")
    assert take_voices.known_ids() == {"b"}


# --- what it costs ---------------------------------------------------------


def test_binding_a_voice_is_priced_where_the_margins_are_computed_from():
    """It was prose in `note` while nothing could set the field. Now it can.

    Only the MULTISHOT speaking backends. An endpoint that cannot cut inside
    one generation is never chosen as a scene's take (script2video.
    scene_take_backend), so no Element of its is ever built and nothing of
    its can carry a voice_id -- veo3.1 has native audio and reads elements
    and still never reaches this field.
    """
    from interfaces.video_backend import BACKENDS

    speaking = [b for b in BACKENDS.values() if b.native_audio and b.multishot]

    assert speaking, "No speaking take backend declared; nothing to pin."
    for backend in speaking:
        assert backend.voice_bound_rate > backend.rate, backend.slug
        assert backend.cost(10, voice_bound=True) > backend.cost(10), backend.slug


# --- the call site ---------------------------------------------------------


def _pipeline_source():
    import inspect

    import pipelines.idea2video as mod

    return inspect.getsource(mod.Idea2VideoPipeline.continue_from_script)


def test_a_speaking_picture_casts_its_take_from_the_backend_s_voices():
    assert "take_voices.cast(" in _pipeline_source()


def test_the_library_entry_records_the_voice_the_drama_was_spoken_in():
    """Not the TTS cast's, which on a speaking film never said a word.

    Without this a character saved off a speaking film carries either nothing
    or -- worse, before the casting was gated -- an ElevenLabs id that no
    scene of theirs was ever voiced with.
    """
    assert '"character_voices": voice_ids' in _pipeline_source()
