"""Domain entities for surf forecasting.

This is the innermost layer of the Clean Architecture: pure data, no I/O, no
third-party imports. Everything else (api/, core/, output/) depends on these
types — never the reverse.

Java analogy: these are like immutable `record` types / POJOs. We use
``@dataclass(frozen=True)`` to make them immutable (``frozen=True`` ≈ all-final
fields) and to get a generated constructor, ``__eq__`` and ``__repr__`` for
free — similar to a Lombok ``@Value`` or a Java 16+ ``record``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class SwellData:
    """Hourly wave/swell snapshot from the marine forecast."""

    timestamp: datetime
    wave_height_m: float
    wave_period_s: float
    wave_direction_deg: float
    swell_height_m: float
    swell_period_s: float
    swell_direction_deg: float
    wind_wave_height_m: float
    # Sea surface temperature (°C). Optional: some wave-only models (e.g. MFWAM)
    # return no SST, so it can be ``None``. Default keeps existing call sites valid.
    water_temp_c: float | None = None


@dataclass(frozen=True)
class WindData:
    """Hourly wind + sky snapshot from the weather forecast.

    ``is_offshore`` is derived from the spot's ``offshore_direction_deg`` when
    the adapter builds this object — the domain just stores the result.
    """

    timestamp: datetime
    speed_kmh: float
    direction_deg: float
    is_offshore: bool
    cloud_cover_pct: float
    precipitation_mm: float


@dataclass(frozen=True)
class GridPoint:
    """The model grid cell Open-Meteo actually used (≠ the requested coords).

    Forecasts aren't computed at the spot but at the nearest grid cell; the
    distance between the two is a real spatial-precision signal.
    """

    latitude: float
    longitude: float


@dataclass(frozen=True)
class GridPoints:
    """The grid cells behind a spot's forecast — one per source model.

    ``marine`` is the wave model (coarser, the surf-critical one); ``weather``
    is the atmospheric model. Either is ``None`` when its probe failed.
    """

    marine: GridPoint | None
    weather: GridPoint | None


@dataclass(frozen=True)
class SunTimes:
    """Sunrise/sunset for one day at a spot — the bounds of surfable daylight.

    ``date`` is the calendar day the event belongs to; ``sunrise`` / ``sunset``
    are tz-aware UTC instants (converted on ingest, per the store-UTC rule). For
    French latitudes daytime never crosses UTC midnight, so the UTC ``date`` of
    the series matches the local (Europe/Paris) date used to pick today/tomorrow.
    """

    date: date
    sunrise: datetime
    sunset: datetime


@dataclass(frozen=True)
class TideEvent:
    """A single high or low tide event.

    ``coefficient`` is the French tide coefficient (20–120 scale; vives-eaux >
    95, mortes-eaux < 45). It is ``None`` when the provider can't supply it —
    e.g. the free Open-Meteo sea-level series gives heights but no coefficient.
    A real value can be backfilled later from a published 2026 tide calendar.

    Note: in a dataclass, fields with defaults must come *after* fields without
    defaults (same rule as Python function arguments), so ``coefficient`` sits
    last. All our call sites use keyword arguments, so ordering is harmless.
    """

    time: datetime
    height_m: float
    is_high: bool
    trend: str  # "rising" | "falling"
    coefficient: int | None = None


@dataclass(frozen=True)
class ForecastBlock:
    """Conditions aggregated over a short time window (default 2h).

    The CLI shows the next 12h as six of these blocks, so you can scan when a
    spot turns good rather than reading a 7-day hour-by-hour series. Linear
    quantities (wave height, wind speed) are summarised as a **min–max range**
    over the block; period and the two **directions** are taken from the block's
    first hour, because averaging compass bearings is a circular-math trap
    (the naive mean of 350° and 10° is 180° — the opposite direction).
    """

    start: datetime
    end: datetime
    wave_height_min_m: float
    wave_height_max_m: float
    swell_period_s: float
    swell_direction_deg: float
    wind_speed_min_kmh: float
    wind_speed_max_kmh: float
    wind_direction_deg: float
    is_offshore: bool
    cloud_cover_min_pct: float
    cloud_cover_max_pct: float
    precipitation_mm_total: float  # accumulated over the block, not a min/max
    # Sea temperature is shown once per spot (it barely moves over a day), not
    # per block; carried here so it flows through the daylight filter. ``None``
    # when the source has no SST.
    water_temp_c: float | None = None


@dataclass(frozen=True)
class SessionScore:
    """Computed quality of a surf session at a given hour.

    Defined here for completeness; it is populated by ``core/score.py`` in
    Phase 2. ``notes`` defaults to an empty list — note the ``field(default_factory=list)``
    idiom: a plain ``= []`` default would be a shared mutable across instances
    (a classic Python gotcha), so dataclasses require a factory instead.
    """

    timestamp: datetime
    score: float  # 0.0–10.0
    label: str  # "FLAT" | "POOR" | "FAIR" | "GOOD" | "EPIC"
    swell_score: float
    wind_score: float
    tide_score: float
    notes: list[str] = field(default_factory=list)
