"""Tests for the daylight-window block aggregation.

``daylight_blocks`` is pure and takes an injected ``now`` and ``tz``, so these
assertions are fully deterministic — no clock, no network. Times are built in
UTC; the local timezone is Europe/Paris (CEST, +2, in May), which is what drives
the noon today/tomorrow rule.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from core.timeline import daylight_blocks, select_sun
from models.forecast import SunTimes, SwellData, WindData

PARIS = ZoneInfo("Europe/Paris")


def _utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 5, day, hour, minute, tzinfo=UTC)


def _swell_series(day: int) -> list[SwellData]:
    """A full 24h hourly swell series for the given May day; height climbs 0.1m/h."""
    return [
        SwellData(
            timestamp=_utc(day, h),
            wave_height_m=0.5 + 0.1 * h,
            wave_period_s=8.0,
            wave_direction_deg=290.0,
            swell_height_m=0.4,
            swell_period_s=10.0,
            swell_direction_deg=255.0,
            wind_wave_height_m=0.2,
            water_temp_c=17.0,
        )
        for h in range(24)
    ]


def _wind_series(day: int) -> list[WindData]:
    return [
        WindData(
            timestamp=_utc(day, h),
            speed_kmh=10.0,
            direction_deg=100.0,
            is_offshore=True,
            cloud_cover_pct=20.0,
            precipitation_mm=0.0,
        )
        for h in range(24)
    ]


# Sunrise 04:30 UTC (06:30 local), sunset 19:30 UTC (21:30 local).
SUN = [
    SunTimes(date=date(2026, 5, 29), sunrise=_utc(29, 4, 30), sunset=_utc(29, 19, 30)),
    SunTimes(date=date(2026, 5, 30), sunrise=_utc(30, 4, 30), sunset=_utc(30, 19, 30)),
]


def test_morning_plans_today_from_now_until_sunset() -> None:
    # 09:00 local (07:00 UTC) on the 29th → before noon → plan today.
    blocks = daylight_blocks(
        _swell_series(29), _wind_series(29), SUN, now=_utc(29, 7), tz=PARIS
    )

    assert blocks[0].start == _utc(29, 7)  # clamped to now, not sunrise (04:30)
    assert blocks[-1].end <= _utc(29, 21)  # nothing past sunset (19:30)
    # 07,09,11,13,15,17,19 → 7 two-hour blocks.
    assert len(blocks) == 7


def test_afternoon_plans_tomorrow_full_daylight() -> None:
    # 14:00 local (12:00 UTC) on the 29th → at/after noon → plan the 30th.
    blocks = daylight_blocks(
        _swell_series(30), _wind_series(30), SUN, now=_utc(29, 12), tz=PARIS
    )

    assert all(b.start.day == 30 for b in blocks)
    assert blocks[0].start == _utc(30, 4)  # floor of sunrise 04:30, full day
    assert blocks[-1].end <= _utc(30, 20)


def test_excludes_hours_outside_daylight() -> None:
    blocks = daylight_blocks(
        _swell_series(30), _wind_series(30), SUN, now=_utc(29, 12), tz=PARIS
    )

    # First block is 04:00–06:00 but only 05:00 is past sunrise (04:30), so its
    # height range is a single point (0.5 + 0.1*5 = 1.0), not 04:00's 0.9.
    assert blocks[0].wave_height_min_m == blocks[0].wave_height_max_m == 1.0
    # Sea temperature carried through from the swell series.
    assert blocks[0].water_temp_c == 17.0
    # No data point past sunset leaks in.
    assert all(b.end <= _utc(30, 20) for b in blocks)


def test_no_sun_data_for_target_day_yields_no_blocks() -> None:
    only_29 = [SUN[0]]
    blocks = daylight_blocks(
        _swell_series(30), _wind_series(30), only_29, now=_utc(29, 12), tz=PARIS
    )
    assert blocks == []


def test_empty_series_yields_no_blocks() -> None:
    assert daylight_blocks([], [], SUN, now=_utc(29, 7), tz=PARIS) == []
    assert daylight_blocks(_swell_series(29), [], SUN, now=_utc(29, 7), tz=PARIS) == []
    assert daylight_blocks(_swell_series(29), _wind_series(29), [], now=_utc(29, 7), tz=PARIS) == []


def test_select_sun_picks_today_before_noon_and_tomorrow_after() -> None:
    morning = select_sun(SUN, now=_utc(29, 7), tz=PARIS)  # 09:00 local
    afternoon = select_sun(SUN, now=_utc(29, 12), tz=PARIS)  # 14:00 local

    assert morning is not None and morning.date == date(2026, 5, 29)
    assert afternoon is not None and afternoon.date == date(2026, 5, 30)


def test_select_sun_returns_none_when_target_day_absent() -> None:
    assert select_sun([SUN[0]], now=_utc(29, 12), tz=PARIS) is None  # wants the 30th
    assert select_sun([], now=_utc(29, 7), tz=PARIS) is None
