"""Tests for the spot-config loader.

These are 'classicist' unit tests: no mocks, we just write a temp JSON file and
assert the parsed `Spot` objects. `tmp_path` is a built-in pytest fixture that
hands us a fresh temporary directory per test (≈ JUnit's @TempDir).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.loader import load_spots
from models.spot import Spot

SAMPLE = [
    {
        "id": "la_barre",
        "name": "Anglet - La Barre",
        "lat": 43.535,
        "lon": -1.562,
        "optimal_swell_direction_deg": 290,
        "swell_window_deg": 45,
        "optimal_tide": "mid_rising",
        "min_height_m": 1.2,
        "max_height_m": 3.0,
        "coefficient_bonus": 70,
        "offshore_direction_deg": 100,
    }
]


def _write(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "spots.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_load_spots_parses_into_spot_objects(tmp_path: Path) -> None:
    spots = load_spots(_write(tmp_path, SAMPLE))

    assert len(spots) == 1
    spot = spots[0]
    assert isinstance(spot, Spot)
    assert spot.id == "la_barre"
    assert spot.name == "Anglet - La Barre"
    assert spot.lat == pytest.approx(43.535)
    assert spot.optimal_tide == "mid_rising"
    assert spot.coefficient_bonus == 70
    # Config omits "timezone", so the default applies.
    assert spot.timezone == "Europe/Paris"


def test_load_spots_real_config_has_four_spots() -> None:
    """The shipped config/spots.json must load and contain all four breaks."""
    spots = load_spots(Path("config/spots.json"))
    ids = {s.id for s in spots}
    assert ids == {"la_barre", "grande_plage", "cote_des_basques", "hossegor_graviere"}


def test_load_spots_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_spots(tmp_path / "does_not_exist.json")
