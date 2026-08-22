"""A saved character comes back in the same clothes, not just the same face.

The Pro character library exists for one promise: this is the same person as
last time. It stored the face (``static_features``), the locked portrait, and
— since a later migration — the voice they were cast with. Not the outfit.

Which is the one field a portrait cannot carry. The codebase says so wherever
wardrobe appears: "the identity reference image binds a face, not an outfit,
so wardrobe has to be restated as text in every frame prompt or the costume
changes between scenes even when the face holds". Across EPISODES the same
thing is true and worse: episode two's screenwriter has never heard of the
outfit, invents a new one, and every frame prompt in that drama then restates
the invention. Same face, same voice, different coat.

Six links in the chain and the wardrobe fell out of all of them: the save
request, the row, the reuse payload, the merge that restores a library
character, and the preset block the screenwriter is briefed with.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent, _preset_line  # noqa: E402


JACKET = "a yellow high-visibility rain jacket over a navy work fleece"


# ── what the writer is told ─────────────────────────────────────────────────


def test_a_preset_character_is_briefed_with_their_outfit():
    line = _preset_line("Mara", "woman in her late thirties", JACKET)
    assert JACKET in line
    assert "WARDROBE (locked" in line
    assert "do not restyle" in line


def test_a_preset_with_no_saved_outfit_reads_as_it_always_did():
    """Rows saved before the column existed, and uploads that never had one."""
    assert _preset_line("Mara", "woman in her late thirties") == (
        "- Mara: woman in her late thirties"
    )
    assert _preset_line("Mara", "woman in her late thirties", "  ") == (
        "- Mara: woman in her late thirties"
    )


def test_both_provider_paths_brief_it_the_same_way():
    """The MuAPI route is tried FIRST, so a preset block improved only on the
    Anthropic fallback would do nothing on the primary path."""
    import inspect

    for method in (
        ScreenwriterAgent.write_script,
        ScreenwriterAgent._write_with_claude,
    ):
        assert "_preset_line(" in inspect.getsource(method), method.__name__


# ── what the pipeline restores ──────────────────────────────────────────────


def test_the_library_outfit_overrides_what_this_script_invented():
    from interfaces.character import CharacterInScene

    character = CharacterInScene(
        idx=0,
        name="Mara",
        static_features="a woman, thirties",
        wardrobe="a grey hooded sweatshirt",  # what episode two dreamed up
    )
    library = {"Mara": {"static_features": "a woman in her late thirties", "wardrobe": JACKET}}

    # The merge, as pipelines/idea2video runs it.
    lib = library.get(character.name)
    if lib.get("static_features"):
        character.static_features = str(lib["static_features"])
    if lib.get("wardrobe"):
        character.wardrobe = str(lib["wardrobe"])

    assert character.wardrobe == JACKET


def test_the_merge_in_the_pipeline_actually_reads_it():
    """Guard the real code path, not just the shape of the operation."""
    import inspect

    from pipelines.idea2video import Idea2VideoPipeline

    source = inspect.getsource(Idea2VideoPipeline.continue_from_script)
    assert 'lib.get("wardrobe")' in source
    assert "char.wardrobe = str(lib[\"wardrobe\"])" in source


def test_a_library_row_without_an_outfit_leaves_the_script_s_own_alone():
    """Rows saved before the migration have no wardrobe, and the script's own
    is better than nothing at all."""
    from interfaces.character import CharacterInScene

    character = CharacterInScene(
        idx=0, name="Mara", static_features="a woman", wardrobe="a grey hooded sweatshirt"
    )
    lib = {"static_features": "a woman in her late thirties", "wardrobe": ""}

    if lib.get("static_features"):
        character.static_features = str(lib["static_features"])
    if lib.get("wardrobe"):
        character.wardrobe = str(lib["wardrobe"])

    assert character.wardrobe == "a grey hooded sweatshirt"


# ── and the round trip that stores it ───────────────────────────────────────


def test_the_save_request_accepts_an_outfit():
    from api import CharacterCreateRequest

    req = CharacterCreateRequest(
        name="Mara",
        static_features="a woman in her late thirties",
        portrait_url="https://cdn/mara.png",
        wardrobe=JACKET,
    )
    assert req.wardrobe == JACKET
    # ...and stays optional, so an older client can still save a character.
    assert (
        CharacterCreateRequest(
            name="Mara", static_features="a woman", portrait_url="https://cdn/m.png"
        ).wardrobe
        == ""
    )


def test_an_unmigrated_deployment_still_saves_the_character():
    """The column is new. Losing the outfit costs a later episode its
    continuity; failing the insert loses the character entirely."""
    import inspect

    import api

    source = inspect.getsource(api._library_insert)
    assert "added_later" in source
    assert "has the migration been applied?" in source
    assert 'body.pop(column, None)' in source


def test_the_migration_adds_the_column_without_breaking_old_rows():
    migration = open(
        os.path.join(os.path.dirname(__file__), "..", "..", "supabase_migration.sql"),
        encoding="utf-8",
    ).read()
    assert "add column if not exists wardrobe text not null default ''" in migration
