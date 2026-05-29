"""Tests for the CLI formatter.

The formatter is pure (data in → string out), so we assert on the text directly
with no console/terminal involved. We verify the UTC→local conversion via tide
times, the per-block layout, and the timezone grouping / sun-line factoring.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from models.forecast import ForecastBlock, SunTimes, TideEvent
from models.spot import Spot
from output.formatter import (
    SpotForecast,
    group_by_timezone,
    render_timezone_group,
)

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


def _block(start_hour: int) -> ForecastBlock:
    return ForecastBlock(
        start=_utc(start_hour),
        end=_utc(start_hour + 2),
        wave_height_min_m=1.6,
        wave_height_max_m=1.8,
        swell_period_s=14.0,
        swell_direction_deg=255.0,  # WSW
        wind_speed_min_kmh=10.0,
        wind_speed_max_kmh=12.0,
        wind_direction_deg=100.0,
        is_offshore=True,
        cloud_cover_min_pct=20.0,
        cloud_cover_max_pct=60.0,
        precipitation_mm_total=0.3,
        water_temp_c=17.4,
    )


BLOCKS = [_block(6), _block(8)]
# Sunrise 04:30 UTC → 06h30 local; sunset 19:45 UTC → 21h45 local (CEST, +2).
SUN = SunTimes(date=date(2026, 5, 28), sunrise=_utc(4, 30), sunset=_utc(19, 45))
TIDES = [
    TideEvent(time=_utc(7, 45), height_m=0.8, is_high=False, coefficient=88, trend="rising"),
    TideEvent(time=_utc(10, 10), height_m=3.2, is_high=True, coefficient=88, trend="falling"),
]
# Request time: 14h00 local on the 27th → the 28th (SUN.date) is J+1. Freshness 14h00.
NOW = datetime(2026, 5, 27, 12, 0, tzinfo=UTC)


def _item(spot: Spot = SPOT, *, blocks: list[ForecastBlock] | None = None,
          sun: SunTimes | None = SUN, marine_km: float | None = 2.3,
          weather_km: float | None = 0.6) -> SpotForecast:
    return SpotForecast(
        spot=spot,
        blocks=BLOCKS if blocks is None else blocks,
        tides=TIDES,
        sun=sun,
        marine_grid_km=marine_km,
        weather_grid_km=weather_km,
    )


def _render_one(item: SpotForecast) -> str:
    return render_timezone_group(item.spot.timezone, [item], NOW)


def test_group_header_shows_timezone_day_and_lead_time() -> None:
    text = _render_one(_item())
    assert "Europe/Paris" in text
    # 2026-05-28 is a Thursday; day comes from the spot's sun date.
    assert "Jeu 28 mai" in text
    assert "(J+1)" in text  # the 28th is one day ahead of the 27th


def test_group_header_shows_source_and_freshness() -> None:
    text = _render_one(_item())
    head = text.split("🌊", 1)[0]
    assert "vagues : Open-Meteo Marine" in head
    assert "météo : Open-Meteo" in head
    assert "récupéré à 14h00" in head  # 12:00 UTC → 14h00 local


def test_spot_shows_grid_point_distance() -> None:
    text = _render_one(_item(marine_km=2.3, weather_km=0.6))
    assert "point de grille" in text
    assert "vagues 2.3 km" in text
    assert "météo 0.6 km" in text


def test_grid_line_omitted_when_distances_unknown() -> None:
    text = _render_one(_item(marine_km=None, weather_km=None))
    assert "point de grille" not in text


def test_spot_shows_water_temperature() -> None:
    # Blocks report 17.4°C → rounded to 17°C, shown once per spot.
    text = _render_one(_item())
    assert "Eau : 17°C" in text


def test_block_shows_height_range_period_and_direction() -> None:
    text = _render_one(_item())
    assert "1.6–1.8m" in text  # min–max wave height over the block
    assert "14s" in text
    assert "WSW" in text  # swell direction 255° → WSW


def test_block_shows_wind_and_weather() -> None:
    text = _render_one(_item())
    assert "10–12 km/h" in text
    assert "offshore" in text.lower()
    assert "20–60%" in text  # cloud cover range
    assert "0.3mm" in text  # accumulated precipitation


def test_height_range_collapses_when_ends_match() -> None:
    flat = replace(_block(6), wave_height_min_m=1.0, wave_height_max_m=1.0)
    text = _render_one(_item(blocks=[flat]))
    assert "1.0m" in text
    assert "1.0–1.0m" not in text


def test_tide_times_converted_to_local() -> None:
    text = _render_one(_item())
    assert "09h45" in text  # 07:45 UTC → 09h45 local
    assert "12h10" in text  # 10:10 UTC → 12h10 local
    assert "88" in text  # coefficient


def test_missing_blocks_renders_no_data() -> None:
    text = _render_one(_item(blocks=[], sun=None))
    assert "Anglet - La Barre" in text
    assert "—" in text


def test_shared_sun_is_factored_once_to_group_header() -> None:
    # Two spots, same timezone, identical sun → one sun line at the top only.
    other = replace(SPOT, id="grande_plage", name="Biarritz - Grande Plage")
    text = render_timezone_group("Europe/Paris", [_item(), _item(other)], NOW)

    assert text.count("lever") == 1  # factored, not repeated per spot
    head = text.split("🌊", 1)[0]
    assert "lever 06h30 → coucher 21h45" in head


def test_close_sun_times_factor_to_the_lower_value() -> None:
    # Nearby spots differing by a minute share one line: the earliest of each.
    other = replace(SPOT, id="hossegor", name="Hossegor - La Gravière")
    later_sun = SunTimes(date=date(2026, 5, 28), sunrise=_utc(4, 40), sunset=_utc(19, 50))
    text = render_timezone_group("Europe/Paris", [_item(), _item(other, sun=later_sun)], NOW)

    head = text.split("🌊", 1)[0]
    assert text.count("lever") == 1  # still one shared line
    # min(04:30, 04:40)=06h30 local; min(19:45, 19:50)=21h45 local.
    assert "lever 06h30 → coucher 21h45" in head


def test_group_by_timezone_splits_by_spot_timezone() -> None:
    paris = _item()
    canary = _item(replace(SPOT, id="lanzarote", name="Famara", timezone="Atlantic/Canary"))

    groups = group_by_timezone([paris, canary])

    assert [tz for tz, _ in groups] == ["Europe/Paris", "Atlantic/Canary"]
    assert [len(members) for _, members in groups] == [1, 1]
