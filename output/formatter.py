"""Presentation adapter: render a spot's raw forecast as a CLI text block.

Phase 1 shows the *data* only (swell / wind / tide / weather) — no score or
session window yet (that arrives in Phase 2). ``render_spot`` is a pure function
returning a string, which keeps it trivial to unit-test; ``main.py`` is
responsible for actually printing it (optionally via rich).

All timestamps are stored as UTC and displayed in Europe/Paris here, per the
project's timezone convention.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from models.forecast import SwellData, TideEvent, WindData
from models.spot import Spot

DISPLAY_TZ = ZoneInfo("Europe/Paris")
_SEPARATOR = "━" * 40
_NO_DATA = "—"

# 16-point compass, indexed by round(bearing / 22.5).
_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]  # fmt: skip


def _compass_point(deg: float) -> str:
    return _COMPASS[round(deg / 22.5) % 16]


def _local_time(dt: datetime) -> str:
    """Format a UTC datetime as French-style local time, e.g. '07h00'."""
    return dt.astimezone(DISPLAY_TZ).strftime("%Hh%M")


def _swell_line(swell: list[SwellData]) -> str:
    if not swell:
        return f"Houle     : {_NO_DATA}"
    s = swell[0]
    direction = f"{_compass_point(s.swell_direction_deg)} ({s.swell_direction_deg:.0f}°)"
    return f"Houle     : {s.wave_height_m:.1f}m — {s.swell_period_s:.0f}s — {direction}"


def _wind_line(wind: list[WindData]) -> str:
    if not wind:
        return f"Vent      : {_NO_DATA}"
    w = wind[0]
    orientation = "offshore ✅" if w.is_offshore else "onshore"
    return (
        f"Vent      : {w.speed_kmh:.0f} km/h {orientation} " f"({_compass_point(w.direction_deg)})"
    )


def _weather_line(wind: list[WindData]) -> str:
    if not wind:
        return f"Météo     : {_NO_DATA}"
    w = wind[0]
    return f"Météo     : ☁️ {w.cloud_cover_pct:.0f}% nuages, {w.precipitation_mm:.1f}mm pluie"


def _tide_line(tides: list[TideEvent]) -> str:
    if not tides:
        return f"Marée     : {_NO_DATA}"
    parts = []
    for t in tides[:2]:
        marker = "PM" if t.is_high else "BM"  # pleine mer / basse mer
        parts.append(f"{marker} {_local_time(t.time)} ({t.height_m:.1f}m)")
    line = f"Marée     : {' → '.join(parts)}"
    coeff = tides[0].coefficient
    if coeff is not None:
        line += f" | Coeff {coeff}"
    return line


def render_spot(
    spot: Spot,
    swell: list[SwellData],
    wind: list[WindData],
    tides: list[TideEvent],
) -> str:
    """Return a human-readable forecast block for one spot."""
    lines = [
        f"🌊 {spot.name}",
        _SEPARATOR,
        _swell_line(swell),
        _wind_line(wind),
        _tide_line(tides),
        _weather_line(wind),
    ]
    return "\n".join(lines)
