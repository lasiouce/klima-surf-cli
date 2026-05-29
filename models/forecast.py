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
from datetime import datetime


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
