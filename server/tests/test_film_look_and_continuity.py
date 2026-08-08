"""The three zero-cost cinema layers: cadence/grain/scope, lighting
continuity, and per-boundary transitions.

None of these call a provider. All three are things a real production gets for
free from having a camera, a gaffer and an editor, and that a generated
sequence has to be told explicitly.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("MUAPI_KEY", "test-key-not-real")

from interfaces.film_look import build_film_look_filters  # noqa: E402
from interfaces.lighting import resolve_lighting  # noqa: E402
from interfaces.transitions import DISSOLVE_SECONDS, plan_transitions  # noqa: E402


# --- cadence / grain / scope -------------------------------------------------


def _clear(monkeypatch):
    for key in ("MUSEFORGE_TARGET_FPS", "MUSEFORGE_FILM_GRAIN", "MUSEFORGE_LETTERBOX"):
        monkeypatch.delenv(key, raising=False)


def test_defaults_deliver_24fps_and_grain_but_no_matte(monkeypatch):
    """24fps and grain are safe everywhere. The matte is not: it burns bars
    into the master that the 9:16 re-export would then centre-crop."""
    _clear(monkeypatch)
    filters, args = build_film_look_filters(1920, 1080)

    assert "fps=24" in filters
    assert args == ["-r", "24"], "The container header must agree with the filtered stream"
    assert any(f.startswith("noise=") for f in filters)
    assert not any("crop=" in f for f in filters)


def test_matte_is_skipped_on_vertical_and_square_masters(monkeypatch):
    """Scope on a 9:16 master would just eat the picture."""
    _clear(monkeypatch)
    monkeypatch.setenv("MUSEFORGE_LETTERBOX", "1")

    wide, _ = build_film_look_filters(1920, 1080)
    tall, _ = build_film_look_filters(1080, 1920)
    square, _ = build_film_look_filters(1080, 1080)

    assert any("crop=" in f for f in wide)
    assert not any("crop=" in f for f in tall)
    assert not any("crop=" in f for f in square)


def test_matte_height_is_even(monkeypatch):
    """H.264 chroma subsampling rejects odd dimensions — an odd matte would
    fail the encode and silently ship the un-finished video."""
    _clear(monkeypatch)
    monkeypatch.setenv("MUSEFORGE_LETTERBOX", "1")
    for width, height in ((1920, 1080), (1366, 768), (854, 480), (1280, 720)):
        filters, _ = build_film_look_filters(width, height)
        crop = next(f for f in filters if f.startswith("crop="))
        crop_h = int(crop.split("crop=")[1].split(":")[1])
        assert crop_h % 2 == 0, f"{width}x{height} produced an odd matte height"


def test_everything_can_be_switched_off(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("MUSEFORGE_TARGET_FPS", "0")
    monkeypatch.setenv("MUSEFORGE_FILM_GRAIN", "0")
    filters, args = build_film_look_filters(1920, 1080)
    assert filters == [] and args == []


def test_resample_runs_before_grain(monkeypatch):
    """Grain generated at 30fps and then resampled to 24 loses the per-frame
    freshness that makes it read as grain rather than as sensor dirt."""
    _clear(monkeypatch)
    filters, _ = build_film_look_filters(1920, 1080)
    assert filters.index("fps=24") < next(
        i for i, f in enumerate(filters) if f.startswith("noise=")
    )


# --- lighting continuity -----------------------------------------------------


def test_one_hour_gives_one_lighting_setup():
    """Same hour in, same plan out — that identity IS the continuity."""
    assert resolve_lighting("early morning") is resolve_lighting("Early Morning")
    assert resolve_lighting("night") is not resolve_lighting("midday")


def test_longer_phrase_wins_over_its_own_substring():
    """'late afternoon' must not be resolved by the 'afternoon' entry — they
    light from different heights."""
    assert resolve_lighting("late afternoon").label == "Late afternoon"
    assert resolve_lighting("early morning").label == "Early morning"


def test_unknown_hour_still_gets_a_fixed_setup():
    """An unstated lighting setup is exactly the drift this prevents, so the
    fallback is a real plan rather than silence."""
    plan = resolve_lighting("some time nobody names")
    assert plan.key_direction and plan.quality and plan.temperature
    assert "key light" in plan.as_clause()


def test_clause_forbids_changing_the_light_between_shots():
    clause = resolve_lighting("night").as_clause()
    assert "every shot" in clause
    assert "Do not change" in clause


# --- transitions -------------------------------------------------------------


def _scene(function="rising_action", tension=5):
    return {"dramatic_function": function, "tension": tension}


def test_default_boundary_is_a_cut():
    """Film's default join is the cut. A dissolve everywhere tells the
    audience time passes at every join — that is what reads as a slideshow."""
    scenes = [_scene("setup", 3), _scene("inciting_incident", 6), _scene("climax", 10)]
    assert plan_transitions(scenes) == [0.0, 0.0]


def test_into_the_resolution_dissolves():
    scenes = [_scene("climax", 10), _scene("resolution", 4)]
    assert plan_transitions(scenes) == [DISSOLVE_SECONDS]


def test_big_tension_drop_dissolves_even_without_labels():
    """Covers scripts that leave dramatic_function unset — the numbers say the
    same thing the labels would have."""
    scenes = [_scene("", 9), _scene("", 3)]
    assert plan_transitions(scenes) == [DISSOLVE_SECONDS]

    gentle = [_scene("", 6), _scene("", 5)]
    assert plan_transitions(gentle) == [0.0]


def test_plan_length_always_matches_boundary_count():
    for n in range(1, 7):
        assert len(plan_transitions([_scene() for _ in range(n)])) == max(0, n - 1)
