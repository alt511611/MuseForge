"""Job 8d082bf7: "turns from the stove" over an empty plate came back as a
kitchen with a steaming pot, a fruit bowl and an ambulance at the door.

The plate is drawn from the one "setting_location" sentence ("a snowbound
mountain refuge hut, interior and its doorway") and says the set holds only
what is named -- but nothing was named, while the shots named a stove, a table,
a radio. The video model fills what the plate lacks. The writer is now told
that the location sentence IS the inventory.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from agents.screenwriter import ScreenwriterAgent  # noqa: E402


def test_the_writer_is_told_the_location_is_the_inventory_the_shots_use():
    prompt = ScreenwriterAgent.SYSTEM_PROMPT
    assert "THE ROOM IS ITS CONTENTS" in prompt
    assert "stove" in prompt and "ambulance" in prompt


def test_a_door_shows_weather_and_light_not_a_street_or_a_vehicle():
    assert "never a street, a vehicle or a second place" in ScreenwriterAgent.SYSTEM_PROMPT


def test_the_schema_example_names_contents_not_just_a_place():
    assert "fixed contents" in ScreenwriterAgent.SYSTEM_PROMPT
