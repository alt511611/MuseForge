"""Every episode this product made was a pilot.

The market unit is a series -- sixty to ninety episodes of one story,
commissioned as a block -- and everything needed to make episode two already
existed: the character library locks a face, a wardrobe and a voice, and the
setting and look are locked per drama. What did not exist was the thing that
makes episode two a SEQUEL: what has happened, who knows it, and the question
the last frame left open.

That last one is the sharpest of them. The screenwriter has been told to end a
micro-drama on an unanswered question since the format existed, and has been
writing it into `cliffhanger` on every result. Nothing has ever read it.
"""

import os
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["MUSEFORGE_DEMO"] = "1"
os.environ.pop("MUAPI_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402

import api as _api  # noqa: E402
import series_store  # noqa: E402
from auth import AuthUser  # noqa: E402
from interfaces.series import (  # noqa: E402
    RECENT_EPISODES,
    Episode,
    Series,
    SeriesCharacter,
    absorb,
    cast_from_result,
    continuity_brief,
    synopsis_of,
)

client = TestClient(_api.app)


@contextmanager
def _auth_as(user_id="user-pro-1", email="pro@example.com"):
    async def _fake_user():
        return AuthUser(user_id, email)

    _api.app.dependency_overrides[_api.get_current_user] = _fake_user
    try:
        yield
    finally:
        _api.app.dependency_overrides.pop(_api.get_current_user, None)


@pytest.fixture(autouse=True)
def _clear_series_mem():
    series_store._memory.clear()
    yield
    series_store._memory.clear()


def _episode_result(number=1, cliffhanger="whose child is it"):
    return {
        "video_url": f"https://cdn/ep{number}.mp4",
        "portraits": {"Vera": "https://cdn/vera.png"},
        "character_voices": {"Vera": "voice-7"},
        "script": {
            "title": f"Episode {number}",
            "logline": "A letter arrives at the harbour.",
            "cliffhanger": cliffhanger,
            "setting_location": "a harbour office",
            "theme": "what you inherit, you did not choose",
            "characters": [
                {
                    "name": "Vera",
                    "description": "40s, grey coat, harbourmaster",
                    "wardrobe": "grey wool coat",
                }
            ],
            "scenes": [
                {"action": "She opens the letter.", "turn": "Vera learns the boat was sold"},
                {"action": "Emre arrives.", "turn": "Emre admits he signed it"},
            ],
        },
    }


# --- what an episode leaves behind ----------------------------------------


def test_the_synopsis_is_assembled_from_the_script_not_from_a_model():
    """Each scene's `turn` is the field that says what CHANGED. Asking a model
    to summarise a script another model just wrote costs a call and produces a
    paraphrase of prose we are holding."""
    text = synopsis_of(_episode_result()["script"])

    assert "the boat was sold" in text
    assert "signed it" in text


def test_the_cast_an_episode_locked_is_what_the_next_one_reuses():
    """Face, outfit and voice. The voice matters most: casting is a hash of
    the NAME that walks past voices already taken, so adding one character to
    episode two re-casts the returning lead unless it is written down."""
    cast = cast_from_result(_episode_result())

    assert cast[0].name == "Vera"
    assert cast[0].portrait_url == "https://cdn/vera.png"
    assert cast[0].voice_id == "voice-7"
    assert cast[0].wardrobe == "grey wool coat"


def test_absorbing_an_episode_moves_the_open_question():
    series = Series(title="Harbour", premise="A letter arrives.")

    absorb(series, 1, "job-1", _episode_result(cliffhanger="who was in the doorway"))

    assert series.open_question == "who was in the doorway"
    assert series.episode(1).status == "completed"
    assert series.episode(1).video_url.endswith("ep1.mp4")
    assert series.next_number == 2


def test_the_setting_is_locked_by_the_first_episode_that_establishes_one():
    """"The same room" is most of what makes a set of films a series."""
    series = Series(title="Harbour")

    absorb(series, 1, "job-1", _episode_result())
    drifted = _episode_result(2)
    drifted["script"]["setting_location"] = "a completely different city"
    absorb(series, 2, "job-2", drifted)

    assert series.setting_location == "a harbour office"


def test_a_returning_character_keeps_their_place_in_the_cast():
    """Cast ORDER is the 180-degree axis: the first visible character is
    frame-left for the whole series. A returning lead who moved to the end of
    the list would flip the screen direction at episode four."""
    series = Series(title="Harbour", cast=[SeriesCharacter("Vera", "40s, grey coat")])

    second = _episode_result(2)
    second["script"]["characters"] = [
        {"name": "Emre", "description": "50s, dock foreman"},
        {"name": "Vera", "description": "40s, grey coat"},
    ]
    absorb(series, 1, "job-1", second)

    assert [c.name for c in series.cast] == ["Vera", "Emre"]


def test_the_series_lock_outranks_a_later_render():
    series = Series(
        title="Harbour",
        cast=[SeriesCharacter("Vera", "40s, grey coat", portrait_url="https://cdn/locked.png")],
    )

    absorb(series, 1, "job-1", _episode_result())

    assert series.cast[0].portrait_url == "https://cdn/locked.png"


# --- what the next episode is told ----------------------------------------


def test_episode_one_is_written_exactly_as_a_standalone_drama():
    """It IS one, until it has a sequel."""
    assert continuity_brief(Series(title="Harbour", premise="A letter.")) == ""


def test_the_brief_leads_with_the_question_the_last_frame_left_open():
    series = Series(title="Harbour", premise="A letter arrives.")
    absorb(series, 1, "job-1", _episode_result(cliffhanger="whose child is it"))

    brief = continuity_brief(series)

    assert "THIS IS EPISODE 2" in brief
    assert "whose child is it" in brief
    assert "Vera" in brief
    assert "a harbour office" in brief


def test_a_long_running_series_does_not_paste_its_whole_history_into_a_prompt():
    """Episode ninety's prompt has to be the size of episode two's. The recent
    window stays in full; everything older is one rolling paragraph."""
    series = Series(title="Harbour", premise="A letter arrives.")
    for number in range(1, 21):
        absorb(series, number, f"job-{number}", _episode_result(number))

    brief = continuity_brief(series)

    assert len(brief) < 4000
    assert brief.count("Episode ") <= RECENT_EPISODES + 1
    assert "Earlier episodes:" in brief


def test_the_rolling_summary_is_grown_by_appending_not_re_summarising():
    """A summary of a summary loses a name per pass, and by episode forty the
    protagonist has a different one."""
    series = Series(title="Harbour")
    for number in range(1, 6):
        absorb(series, number, f"job-{number}", _episode_result(number))

    assert series.story_so_far.startswith("Ep 1:")
    assert "Ep 2:" in series.story_so_far
    # The recent window is NOT in the rolling summary; it is quoted in full.
    assert "Ep 5:" not in series.story_so_far


def test_the_screenwriter_is_told_this_is_not_a_pilot():
    from agents.screenwriter import ScreenwriterAgent

    agent = ScreenwriterAgent(api_key="")
    ordinary = agent._system_prompt(num_scenes=3)
    episode = agent._system_prompt(num_scenes=3, is_episode=True)

    assert "THIS IS NOT A PILOT" in episode
    assert "THIS IS NOT A PILOT" not in ordinary
    # And the rules that matter are the ones a fresh prompt gets wrong.
    assert "DO NOT RE-INTRODUCE ANYONE" in episode
    assert "OPEN ON THE CONSEQUENCE" in episode


def test_the_brief_is_the_first_thing_in_the_prompt():
    """An episode's idea is a suggestion for what happens next; what has
    already happened is not, and a model weights the opening hardest."""
    from agents.screenwriter import _series_block

    block = _series_block("THIS IS EPISODE 4.")

    assert block.startswith("SERIES CONTINUITY")
    assert _series_block("") == ""


# --- the endpoints ---------------------------------------------------------


def _create_series(**overrides):
    body = {
        "title": "Harbour",
        "premise": "A harbourmaster inherits a debt she cannot pay.",
        "num_scenes": 3,
    }
    body.update(overrides)
    return client.post("/api/series", json=body)


def test_a_series_is_pro_only():
    with _auth_as(), patch.object(_api, "_get_user_plan", AsyncMock(return_value="creator")):
        assert _create_series().status_code == 403
        # Hidden rather than refused on the listing, like the character library.
        assert client.get("/api/series").json() == {"series": []}


def test_a_series_defaults_to_the_format_it_is_sold_into():
    """Vertical, micro-drama shaped: nobody commissions sixty cinematic 16:9
    shorts."""
    with _auth_as(), patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")):
        body = _create_series().json()

    assert body["aspect_ratio"] == "9:16"
    assert body["narrative_mode"] == "micro_drama"
    assert body["next_episode"] == 1


def test_commissioning_an_episode_carries_the_series_locks_onto_the_job():
    with _auth_as(), patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")):
        series = _create_series(aspect_ratio="9:16", language="tr").json()
        started = client.post(f"/api/series/{series['id']}/episodes", json={})

    assert started.status_code == 200
    body = started.json()
    assert body["episode_number"] == 1

    from jobs import job_store

    job = job_store.get(body["job_id"])
    assert job.aspect_ratio == "9:16"
    assert job.language == "tr"
    assert job.series_id == series["id"]


def test_the_second_episode_is_commissioned_with_the_first_one_s_cliffhanger():
    with _auth_as(), patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")):
        series = _create_series().json()
        first = client.post(f"/api/series/{series['id']}/episodes", json={}).json()

        # The first episode lands, the way a finished job lands.
        from jobs import job_store

        import asyncio

        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            series_store.record_episode(
                "user-pro-1",
                series["id"],
                first["episode_number"],
                first["job_id"],
                _episode_result(1, cliffhanger="who was standing in the doorway"),
            )
        )

        second = client.post(f"/api/series/{series['id']}/episodes", json={}).json()
        from jobs import job_store as store

        job = store.get(second["job_id"])

    assert second["episode_number"] == 2
    assert "who was standing in the doorway" in job.series_brief
    # ...and the user did not have to retype their own cliffhanger as an idea.
    assert "who was standing in the doorway" in job.idea


def test_an_episode_number_is_claimed_before_the_render_starts():
    """It is part of the brief the script is written against ("THIS IS EPISODE
    7"), so two episodes ordered a second apart must not both be seven."""
    with _auth_as(), patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")):
        series = _create_series().json()
        first = client.post(f"/api/series/{series['id']}/episodes", json={}).json()
        second = client.post(f"/api/series/{series['id']}/episodes", json={}).json()

    assert [first["episode_number"], second["episode_number"]] == [1, 2]


def test_deleting_a_series_is_not_deleting_its_episodes():
    """They were paid for, they still play, and they live under their own job
    ids."""
    with _auth_as(), patch.object(_api, "_get_user_plan", AsyncMock(return_value="pro")):
        series = _create_series().json()
        started = client.post(f"/api/series/{series['id']}/episodes", json={}).json()
        assert client.delete(f"/api/series/{series['id']}").status_code == 200
        assert client.get(f"/api/series/{series['id']}").status_code == 404

    from jobs import job_store

    assert job_store.get(started["job_id"]) is not None


@pytest.mark.asyncio
async def test_a_missing_series_never_costs_a_delivered_episode():
    """A series is a memory wrapped around jobs stored independently. Losing
    the wrapper must not lose an episode."""
    from jobs import Job, _record_series_episode

    job = Job(id="job-x", user_id="user-pro-1", series_id="gone", episode_number=3)

    result = await _record_series_episode(job, {"video_url": "https://cdn/x.mp4"})

    assert result["series_id"] == "gone"
    assert result["episode_number"] == 3
