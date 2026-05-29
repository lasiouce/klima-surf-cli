"""Pick the useful surf window for a day and fold it into short blocks.

Surfers care about daylight, and about *which* day to plan. The rule, kept
deliberately simple:

* asked **before noon** (local) → plan **today**, from now until sunset;
* asked **at/after noon** → plan **tomorrow**, the whole sunrise→sunset day.

Given the day's ``SunTimes`` and the hourly ``SwellData`` / ``WindData`` series,
``daylight_blocks`` keeps only the daylight hours of the chosen day and groups
them into ``block_h``-hour blocks — the view the CLI shows and, later, what the
alerting rule scans for good windows.

Pure use-case logic (no I/O). Both ``now`` and the local ``tz`` are **injected**
(like ``core/tides.py`` stays deterministic): the noon cutoff and the
today/tomorrow choice are local-time concepts, but core must not hard-code a
timezone, so the composition root passes it in.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, tzinfo

from models.forecast import ForecastBlock, SunTimes, SwellData, WindData

_DEFAULT_BLOCK_H = 2
_MORNING_CUTOFF_H = 12  # asked before this local hour → plan today, else tomorrow


def _floor_to_hour(dt: datetime) -> datetime:
    """Round a datetime down to the start of its hour (drop minutes/seconds)."""
    return dt.replace(minute=0, second=0, microsecond=0)


def _target_date(now: datetime, tz: tzinfo, cutoff_h: int) -> date:
    """Today if asked before the local cutoff hour, otherwise tomorrow."""
    local = now.astimezone(tz)
    if local.hour >= cutoff_h:
        return local.date() + timedelta(days=1)
    return local.date()


def _sun_for(sun_times: list[SunTimes], target: date) -> SunTimes | None:
    """The ``SunTimes`` entry for ``target``, or ``None`` if not in the series."""
    return next((s for s in sun_times if s.date == target), None)


def select_sun(
    sun_times: list[SunTimes],
    now: datetime,
    *,
    tz: tzinfo,
    cutoff_h: int = _MORNING_CUTOFF_H,
) -> SunTimes | None:
    """The ``SunTimes`` for the day the noon rule plans for (today/tomorrow).

    Public so the composition root can hand the same chosen day to the renderer
    for its header, instead of re-deriving the today/tomorrow decision.
    """
    return _sun_for(sun_times, _target_date(now, tz, cutoff_h))


def daylight_blocks(
    swell: list[SwellData],
    wind: list[WindData],
    sun_times: list[SunTimes],
    now: datetime,
    *,
    tz: tzinfo,
    block_h: int = _DEFAULT_BLOCK_H,
    cutoff_h: int = _MORNING_CUTOFF_H,
) -> list[ForecastBlock]:
    """Aggregate the target day's daylight into ``block_h``-hour blocks.

    The target day is chosen by the noon rule above. The window runs from
    sunrise to sunset, but for *today* the start is clamped to ``now`` so we
    never show hours already gone. Blocks with no swell *or* wind data in range
    are skipped, so a missing/partial series yields fewer blocks rather than
    raising.
    """
    if not swell or not wind or not sun_times:
        return []

    sun = select_sun(sun_times, now, tz=tz, cutoff_h=cutoff_h)
    if sun is None:
        return []

    window_start = max(sun.sunrise, now)  # the max only bites for the "today" case
    window_end = sun.sunset
    if window_start >= window_end:  # day's daylight already over
        return []

    step = timedelta(hours=block_h)
    blocks: list[ForecastBlock] = []
    block_start = _floor_to_hour(window_start)
    while block_start < window_end:
        block_end = block_start + step
        # A point counts when it falls inside both this block and the daylight
        # window — so pre-sunrise / post-sunset (and pre-now) hours drop out.
        lo = max(block_start, window_start)
        hi = min(block_end, window_end)
        s_points = [s for s in swell if lo <= s.timestamp < hi]
        w_points = [w for w in wind if lo <= w.timestamp < hi]
        if s_points and w_points:
            blocks.append(_aggregate(block_start, block_end, s_points, w_points))
        block_start = block_end

    return blocks


def _aggregate(
    start: datetime,
    end: datetime,
    swell: list[SwellData],
    wind: list[WindData],
) -> ForecastBlock:
    """Fold one block's worth of hourly points into a single ``ForecastBlock``.

    ``swell``/``wind`` are time-ordered (they preserve the source series order),
    so ``[0]`` is the block's first hour — used for the directional/period
    fields where a min/max range would be meaningless or misleading.
    """
    return ForecastBlock(
        start=start,
        end=end,
        wave_height_min_m=min(s.wave_height_m for s in swell),
        wave_height_max_m=max(s.wave_height_m for s in swell),
        swell_period_s=swell[0].swell_period_s,
        swell_direction_deg=swell[0].swell_direction_deg,
        wind_speed_min_kmh=min(w.speed_kmh for w in wind),
        wind_speed_max_kmh=max(w.speed_kmh for w in wind),
        wind_direction_deg=wind[0].direction_deg,
        is_offshore=wind[0].is_offshore,
        cloud_cover_min_pct=min(w.cloud_cover_pct for w in wind),
        cloud_cover_max_pct=max(w.cloud_cover_pct for w in wind),
        # Precipitation is an hourly accumulation, so summing gives the total
        # rainfall expected across the block (not a min/max of rates).
        precipitation_mm_total=sum(w.precipitation_mm for w in wind),
        # First hour that actually reports a temperature (some sources omit it).
        water_temp_c=next((s.water_temp_c for s in swell if s.water_temp_c is not None), None),
    )
