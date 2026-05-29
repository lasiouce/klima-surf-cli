"""Derive high/low tide events from an hourly sea-level series.

Open-Meteo's free Marine API does not hand back discrete high/low tide *events*
the way the old TidesAtlas endpoint did; it returns an hourly
``sea_level_height_msl`` series (metres relative to mean sea level). The tide's
high and low waters are simply the **turning points** of that curve — the local
maxima (pleine mer) and minima (basse mer).

This module is pure use-case logic (no I/O, no ``httpx``): given the series it
returns ``TideEvent``s. That makes it deterministic and trivial to unit-test,
and keeps the Open-Meteo adapter thin. The French tide ``coefficient`` is not
derivable from sea level alone, so events carry ``coefficient=None`` (the field
is already optional); it can be backfilled later from an astronomical calendar.
"""

from __future__ import annotations

from datetime import datetime

from models.forecast import TideEvent

# A turning point needs a point plus both neighbours, so a series shorter than
# this can contain no detectable high/low water.
_MIN_POINTS_FOR_TURNING_POINT = 3


def derive_tide_events(series: list[tuple[datetime, float]]) -> list[TideEvent]:
    """Find high/low tide turning points in an hourly ``(time, height_m)`` series.

    ``series`` must be ordered by time. A point is a **high** (pleine mer) when it
    is higher than the hour before and not lower than the hour after, and a
    **low** (basse mer) in the mirror case. ``trend`` describes what the tide
    does *after* the turning point: it falls after a high and rises after a low —
    matching the convention the rest of the app already expects.

    Timing is only as precise as the hourly sampling (±~30 min around the true
    turning point); good enough for a session window, not for a tide table.
    """
    if len(series) < _MIN_POINTS_FOR_TURNING_POINT:
        return []

    events: list[TideEvent] = []
    # Skip the first and last samples: a turning point needs a neighbour on
    # each side. `range(1, len-1)` is the Pythonic "interior points" idiom.
    for i in range(1, len(series) - 1):
        _, height_prev = series[i - 1]
        time, height = series[i]
        _, height_next = series[i + 1]

        if height > height_prev and height >= height_next:
            events.append(_event(time, height, is_high=True))
        elif height < height_prev and height <= height_next:
            events.append(_event(time, height, is_high=False))

    return events


def _event(time: datetime, height: float, *, is_high: bool) -> TideEvent:
    """Build a ``TideEvent``; trend is 'falling' after a high, 'rising' after a low."""
    return TideEvent(
        time=time,
        height_m=height,
        is_high=is_high,
        trend="falling" if is_high else "rising",
        coefficient=None,  # not derivable from sea level alone
    )
