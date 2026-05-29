"""Tests for angular/geometry helpers (pure functions, no I/O)."""

from __future__ import annotations

import pytest

from core.geo import angular_difference, is_offshore_wind


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
