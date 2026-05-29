"""Tests for angular/geometry helpers (pure functions, no I/O)."""

from __future__ import annotations

import pytest

from core.geo import angular_difference, haversine_km, is_offshore_wind


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (10, 20, 10),
        (350, 10, 20),  # wraps around 0/360
        (10, 350, 20),
        (0, 180, 180),  # maximum separation
        (90, 90, 0),
        (-10, 10, 20),  # negative inputs normalised
    ],
)
def test_angular_difference(a: float, b: float, expected: float) -> None:
    assert angular_difference(a, b) == pytest.approx(expected)


def test_haversine_zero_distance_for_same_point() -> None:
    assert haversine_km(43.535, -1.562, 43.535, -1.562) == pytest.approx(0.0)


def test_haversine_known_distance() -> None:
    # La Barre spot (43.535, -1.562) to a grid cell ~0.0067°N, 0.0204°E away.
    # ≈ 1.7 km; assert within a tolerant band (great-circle, not flat-earth).
    km = haversine_km(43.535, -1.562, 43.541664, -1.5416565)
    assert km == pytest.approx(1.75, abs=0.3)


def test_haversine_is_symmetric() -> None:
    a = haversine_km(43.5, -1.5, 43.7, -1.4)
    b = haversine_km(43.7, -1.4, 43.5, -1.5)
    assert a == pytest.approx(b)


def test_angular_difference_never_exceeds_180() -> None:
    for a in range(0, 360, 17):
        for b in range(0, 360, 23):
            assert 0 <= angular_difference(a, b) <= 180


def test_is_offshore_within_tolerance() -> None:
    # offshore_direction = 100°, tolerance 45° → wind from 70°-140° is offshore
    assert is_offshore_wind(wind_from_deg=100, offshore_direction_deg=100)
    assert is_offshore_wind(wind_from_deg=130, offshore_direction_deg=100)
    assert is_offshore_wind(wind_from_deg=70, offshore_direction_deg=100)


def test_is_offshore_outside_tolerance() -> None:
    assert not is_offshore_wind(wind_from_deg=180, offshore_direction_deg=100)
    assert not is_offshore_wind(wind_from_deg=280, offshore_direction_deg=100)  # onshore


def test_is_offshore_custom_tolerance() -> None:
    assert not is_offshore_wind(wind_from_deg=130, offshore_direction_deg=100, tolerance_deg=20)
    assert is_offshore_wind(wind_from_deg=115, offshore_direction_deg=100, tolerance_deg=20)
