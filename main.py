"""Composition root / CLI entry point.

This is the only place that *wires* the application together: it loads config
and secrets, constructs the concrete adapters, and feeds their output to the
presentation layer. It contains **no business logic** — that lives in core/
(Phase 2) and the adapters.

Run:  python main.py            # all spots
      python main.py --spot la_barre
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from rich.console import Console

from api.open_meteo import OpenMeteoClient
from api.open_meteo_tides import OpenMeteoTideProvider
from config.loader import load_spots
from core.geo import haversine_km
from core.ports import ForecastProvider, TideProvider
from core.timeline import daylight_blocks, select_sun
from models.forecast import GridPoint
from models.spot import Spot
from output.formatter import SpotForecast, group_by_timezone, render_timezone_group


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Surf forecast for the French Basque Country.")
    parser.add_argument(
        "--spot",
        help="Only show this spot id (e.g. la_barre). Defaults to all spots.",
    )
    return parser


def _render_all(
    spots: list[Spot],
    forecast: ForecastProvider,
    tides: TideProvider,
    console: Console,
    now: datetime,
) -> None:
    """Fetch each spot's daylight forecast, then print it grouped by timezone.

    Depends on the ports, not the concretes. Each spot is resolved in its own
    timezone (``daylight_blocks`` / ``select_sun`` take it), and the formatter
    factors the shared daylight context per group.
    """
    items = []
    for spot in spots:
        tz = ZoneInfo(spot.timezone)
        swell = forecast.get_swell(spot)
        wind = forecast.get_wind(spot)
        sun_times = forecast.get_sun_times(spot)
        tide_events = tides.get_tides(spot)
        grid = forecast.get_grid_points(spot)
        blocks = daylight_blocks(swell, wind, sun_times, now, tz=tz)
        sun = select_sun(sun_times, now, tz=tz)
        items.append(
            SpotForecast(
                spot=spot,
                blocks=blocks,
                tides=tide_events,
                sun=sun,
                marine_grid_km=_grid_distance_km(spot, grid.marine),
                weather_grid_km=_grid_distance_km(spot, grid.weather),
            )
        )

    for tz_name, group in group_by_timezone(items):
        console.print(render_timezone_group(tz_name, group, now))
        console.print()


def _grid_distance_km(spot: Spot, grid: GridPoint | None) -> float | None:
    """Distance from the spot to its model grid cell, or ``None`` if unknown."""
    if grid is None:
        return None
    return haversine_km(spot.lat, spot.lon, grid.latitude, grid.longitude)


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    args = _build_parser().parse_args()
    console = Console()

    spots = load_spots()
    if args.spot:
        spots = [s for s in spots if s.id == args.spot]
        if not spots:
            console.print(f"[red]Unknown spot id: {args.spot}[/red]")
            return

    # Construct concrete adapters and inject them behind their ports.
    # Tides now come from Open-Meteo too (free, keyless) — no more TidesAtlas key.
    forecast: ForecastProvider = OpenMeteoClient()
    tides: TideProvider = OpenMeteoTideProvider()

    _render_all(spots, forecast, tides, console, now=datetime.now(UTC))


if __name__ == "__main__":
    main()
