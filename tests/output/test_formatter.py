"""Tests for the CLI formatter.

`render_spot` is a pure function (data in → string out), so we can assert on the
text directly with no console/terminal involved. We verify the UTC→Europe/Paris
conversion by checking displayed local times.
"""

from __future__ import annotations

from datetime import UTC, datetime

from models.forecast import SwellData, TideEvent, WindData
from models.spot import Spot
from output.formatter import render_spot

SPOT = Spot(
    id="la_barre",
    name="Anglet - La Barre",
    lat=43.535,
    lon=-1.562,
    optimal_swell_direction_deg=290,
    swell_window_deg=45,
    optimal_tide="mid_rising",
    min_height_m=1.2,
    max_height_m=3.0,
    coefficient_bonus=70,
    offshore_direction_deg=100,
)


def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, 28, hour, minute, tzinfo=UTC)


SWELL = [
    SwellData(
        timestamp=_utc(6),
        wave_height_m=1.8,
        wave_period_s=13.0,
        wave_direction_deg=285.0,
        swell_height_m=1.6,
        swell_period_s=14.0,
        swell_direction_deg=255.0,  # WSW
        wind_wave_height_m=0.4,
    )
]
WIND = [
    WindData(
        timestamp=_utc(6),
        speed_kmh=12.0,
        direction_deg=100.0,
        is_offshore=True,
        cloud_cover_pct=40.0,
        precipitation_mm=0.0,
    )
]
TIDES = [
    TideEvent(time=_utc(3, 45), height_m=0.8, is_high=False, coefficient=88, trend="rising"),
    TideEvent(time=_utc(10, 10), height_m=3.2, is_high=True, coefficient=88, trend="falling"),
]


def test_render_includes_spot_name_and_swell() -> None:
    text = render_spot(SPOT, SWELL, WIND, TIDES)
    assert "Anglet - La Barre" in text
    assert "1.8" in text  # wave height (headline surf height)
    assert "14" in text  # swell period (swell power)
    assert "WSW" in text  # swell direction 255° → WSW


def test_render_shows_offshore_wind() -> None:
    text = render_spot(SPOT, SWELL, WIND, TIDES)
    assert "12" in text
    assert "offshore" in text.lower()


def test_render_converts_tide_times_to_paris() -> None:
    text = render_spot(SPOT, SWELL, WIND, TIDES)
    # 03:45 UTC in May (CEST, +2) → 05h45 local
    assert "05h45" in text
    # 10:10 UTC → 12h10 local
    assert "12h10" in text
    assert "88" in text  # coefficient


def test_render_handles_missing_data_gracefully() -> None:
    text = render_spot(SPOT, [], [], [])
    assert "Anglet - La Barre" in text
    # Should not raise and should signal absence of data.
    assert "—" in text or "n/a" in text.lower() or "indispo" in text.lower()
