"""Tests for the pure tide-derivation logic (no I/O, no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from core.tides import derive_tide_events
from models.forecast import TideEvent


def _series(heights: list[float]) -> list[tuple[datetime, float]]:
    """Build an hourly ``(time, height)`` series starting at 2026-05-28T00:00 UTC."""
    start = datetime(2026, 5, 28, 0, 0, tzinfo=UTC)
    return [(start + timedelta(hours=i), h) for i, h in enumerate(heights)]


def test_finds_low_then_high() -> None:
    # Falls to a trough at index 2, rises to a crest at index 5.
    heights = [2.0, 1.0, 0.5, 1.5, 2.8, 3.2, 2.6]
    events = derive_tide_events(_series(heights))

    assert len(events) == 2
    low, high = events
    assert isinstance(low, TideEvent)
    assert low.is_high is False
    assert low.height_m == 0.5
    assert low.trend == "rising"  # tide rises away from a low
    assert low.time.hour == 2

    assert high.is_high is True
    assert high.height_m == 3.2
    assert high.trend == "falling"  # tide falls away from a high
    assert high.time.hour == 5


def test_coefficient_is_none_from_sea_level() -> None:
    events = derive_tide_events(_series([1.0, 0.5, 1.0]))
    assert events[0].coefficient is None


def test_ignores_monotonic_series() -> None:
    """A purely rising (or falling) series has no turning point."""
    assert derive_tide_events(_series([0.5, 1.0, 1.5, 2.0])) == []


def test_too_short_series_returns_empty() -> None:
    assert derive_tide_events(_series([1.0, 2.0])) == []
    assert derive_tide_events([]) == []


def test_endpoints_are_not_reported_as_events() -> None:
    """First/last samples lack a neighbour and must never be turning points."""
    # Lowest value sits at index 0; it should NOT be flagged as a low.
    events = derive_tide_events(_series([0.1, 1.0, 2.0, 3.0]))
    assert events == []
