"""Presentation adapter: render the daylight forecast, grouped by timezone.

Phase 1 shows the *data* only (swell / wind / tide) — no score yet (Phase 2).
Each spot's surfable day is shown as a handful of 2-hour ``ForecastBlock`` rows
(built by ``core/timeline.py``).

Spots are **grouped by timezone**, and the daylight context shared by a group
is **factored out** of the per-spot blocks: the day always heads the group, and
the sunrise/sunset line is lifted to the group level whenever every spot in it
would print the same one (nearby spots share it to the minute). When they differ
the line stays per-spot. Rendering is pure (data in → string out); ``main.py``
prints the result.

All timestamps are stored as UTC and displayed in each group's timezone, per the
project's "store UTC, display local" convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from zoneinfo import ZoneInfo

from models.forecast import ForecastBlock, SunTimes, TideEvent
from models.spot import Spot

DISPLAY_TZ = ZoneInfo("Europe/Paris")
_SEPARATOR = "━" * 40
_NO_DATA = "—"
# Honest provenance per source: the marine endpoint serves a wave model, the
# weather endpoint auto-selects with best_match. Neither exposes a model name
# or confidence score in the response, so these are the truthful labels.
_SOURCE_WAVES = "Open-Meteo Marine"
_SOURCE_WEATHER = "Open-Meteo"

# 16-point compass, indexed by round(bearing / 22.5).
_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]  # fmt: skip

# Abbreviated French weekday names, indexed by datetime.weekday() (Mon=0).
# Built manually rather than via locale-aware strftime: locale "fr_FR" is not
# guaranteed installed (and differs across OSes), which would make output
# non-deterministic — exactly what tests must avoid.
_JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
_MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]  # fmt: skip


@dataclass(frozen=True)
class SpotForecast:
    """One spot's computed forecast, ready to render.

    A small view-model assembled by the composition root (fetch + ``core``),
    so the formatter receives finished data and stays pure. The ``*_grid_km``
    fields are how far the model grid cells sit from the spot (data quality).
    """

    spot: Spot
    blocks: list[ForecastBlock]
    tides: list[TideEvent]
    sun: SunTimes | None
    marine_grid_km: float | None = None
    weather_grid_km: float | None = None


def _compass_point(deg: float) -> str:
    return _COMPASS[round(deg / 22.5) % 16]


def _local(dt: datetime, tz: tzinfo) -> datetime:
    return dt.astimezone(tz)


def _local_time(dt: datetime, tz: tzinfo) -> str:
    """Format a UTC datetime as French-style local time, e.g. '07h00'."""
    return _local(dt, tz).strftime("%Hh%M")


def _local_day(dt: datetime, tz: tzinfo) -> str:
    """Format a UTC datetime as a French local day, e.g. 'Ven 29 mai'."""
    local = _local(dt, tz)
    return f"{_JOURS[local.weekday()]} {local.day} {_MOIS[local.month - 1]}"


def _range(low: float, high: float, unit: str, digits: int = 1) -> str:
    """'0.8m' if the rounded ends match, else '0.8–1.1m' (wind uses digits=0)."""
    lo, hi = f"{low:.{digits}f}", f"{high:.{digits}f}"
    return f"{lo}{unit}" if lo == hi else f"{lo}–{hi}{unit}"


def _group_sun_line(suns: list[SunTimes], tz: tzinfo) -> str:
    """'☀️ lever 06h28 → coucher 21h38' — the group's shared daylight.

    Sunrise/sunset vary by a minute or so between nearby spots, which is noise
    to a surfer, so a whole timezone group shares one line. We take the earliest
    (lowest) time of the group for each, giving a single clean value.
    """
    lever = _local_time(min(s.sunrise for s in suns), tz)
    coucher = _local_time(min(s.sunset for s in suns), tz)
    return f"☀️ lever {lever} → coucher {coucher}"


def _block_row(block: ForecastBlock, tz: tzinfo) -> str:
    when = f"{_local_time(block.start, tz)}→{_local_time(block.end, tz)}"
    height = _range(block.wave_height_min_m, block.wave_height_max_m, "m")
    swell_dir = _compass_point(block.swell_direction_deg)
    wind_speed = _range(block.wind_speed_min_kmh, block.wind_speed_max_kmh, " km/h", digits=0)
    orientation = "offshore ✅" if block.is_offshore else "onshore"
    wind_dir = _compass_point(block.wind_direction_deg)
    clouds = _range(block.cloud_cover_min_pct, block.cloud_cover_max_pct, "%", digits=0)
    rain = f"{block.precipitation_mm_total:.1f}mm"
    return (
        f"{when}  {height} {block.swell_period_s:.0f}s {swell_dir}"
        f"  ·  {wind_speed} {orientation} ({wind_dir})"
        f"  ·  ☁️ {clouds} {rain}"
    )


def _tide_line(tides: list[TideEvent], tz: tzinfo) -> str:
    if not tides:
        return f"Marée  : {_NO_DATA}"
    parts = []
    for t in tides[:2]:
        marker = "PM" if t.is_high else "BM"  # pleine mer / basse mer
        parts.append(f"{marker} {_local_time(t.time, tz)} ({t.height_m:.1f}m)")
    line = f"Marée  : {' → '.join(parts)}"
    coeff = tides[0].coefficient
    if coeff is not None:
        line += f" | Coeff {coeff}"
    return line


def _eau_line(item: SpotForecast) -> str | None:
    """'🌡️ Eau : 17°C' — mean sea temperature over the day's daylight blocks."""
    temps = [b.water_temp_c for b in item.blocks if b.water_temp_c is not None]
    if not temps:
        return None
    return f"🌡️ Eau : {sum(temps) / len(temps):.0f}°C"


def _grid_line(item: SpotForecast) -> str | None:
    """'📡 point de grille : vagues 2.3 km · météo 0.6 km' — spatial precision."""
    parts = []
    if item.marine_grid_km is not None:
        parts.append(f"vagues {item.marine_grid_km:.1f} km")
    if item.weather_grid_km is not None:
        parts.append(f"météo {item.weather_grid_km:.1f} km")
    return f"📡 point de grille : {' · '.join(parts)}" if parts else None


def _lead_time(target: date, now: datetime, tz: tzinfo) -> str:
    """'aujourd'hui' / 'J+1' — how far ahead the shown day is (reliability proxy)."""
    days = (target - _local(now, tz).date()).days
    return "aujourd'hui" if days == 0 else f"J+{days}"


def _source_line(now: datetime, tz: tzinfo) -> str:
    return (
        f"📡 vagues : {_SOURCE_WAVES} · météo : {_SOURCE_WEATHER}"
        f" · récupéré à {_local_time(now, tz)}"
    )


def _spot_section(item: SpotForecast, tz: tzinfo) -> str:
    """Render one spot's blocks + tides. Daylight is factored to the group head."""
    if not item.blocks:
        return f"🌊 {item.spot.name}\n{_SEPARATOR}\nPrévision : {_NO_DATA}"

    # Only tides from the window start onward matter — drop already-passed ones.
    upcoming_tides = [t for t in item.tides if t.time >= item.blocks[0].start]

    lines = [f"🌊 {item.spot.name}"]
    lines += [line for line in (_eau_line(item), _grid_line(item)) if line is not None]
    lines += [
        _SEPARATOR,
        *[_block_row(b, tz) for b in item.blocks],
        _SEPARATOR,
        _tide_line(upcoming_tides, tz),
    ]
    return "\n".join(lines)


def group_by_timezone(items: list[SpotForecast]) -> list[tuple[str, list[SpotForecast]]]:
    """Group forecasts by their spot's timezone, preserving first-seen order."""
    groups: dict[str, list[SpotForecast]] = {}
    for item in items:
        groups.setdefault(item.spot.timezone, []).append(item)
    return list(groups.items())


def render_timezone_group(tz_name: str, items: list[SpotForecast], now: datetime) -> str:
    """Render one timezone group: the shared day + daylight header, then spots.

    The day, the sunrise/sunset line, the lead time and the data source are the
    context every spot in the group shares, so they head the group once instead
    of repeating on each spot. Only the per-spot grid distance stays per spot.
    """
    tz = ZoneInfo(tz_name)

    suns = [it.sun for it in items if it.sun is not None]
    if suns:
        day = _local_day(suns[0].sunrise, tz)
        lead = _lead_time(suns[0].date, now, tz)
        header = [f"🕒 prévision pour : {tz_name} — {day} ({lead})", _group_sun_line(suns, tz)]
    else:
        header = [f"🕒 prévision pour : {tz_name}"]
    header.append(_source_line(now, tz))

    sections = [_spot_section(it, tz) for it in items]
    return "\n".join(header) + "\n\n" + "\n\n".join(sections)
