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

from dotenv import load_dotenv
from rich.console import Console

from api.open_meteo import OpenMeteoClient
from api.open_meteo_tides import OpenMeteoTideProvider
from config.loader import load_spots
from core.ports import ForecastProvider, TideProvider
from models.spot import Spot
from output.formatter import render_spot


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
) -> None:
    """Fetch and print each spot. Depends on the ports, not the concretes."""
    for spot in spots:
        swell = forecast.get_swell(spot)
        wind = forecast.get_wind(spot)
        tide_events = tides.get_tides(spot)
        console.print(render_spot(spot, swell, wind, tide_events))
        console.print()


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

    _render_all(spots, forecast, tides, console)


if __name__ == "__main__":
    main()
