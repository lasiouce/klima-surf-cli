"""Ports: the abstractions the application depends on (Dependency Inversion).

A ``typing.Protocol`` is Python's structural interface. Unlike a Java
``interface``, a class does **not** have to declare that it implements a
Protocol — if it has methods with matching signatures, it *is* a valid
implementation ("duck typing", checked statically by mypy). This is how
``core/`` (Phase 2 scoring) and ``main.py`` stay decoupled from the concrete
``api/`` clients: they depend only on these ports, and the real clients are
injected from the composition root.

Small, focused ports (ISP): a forecast provider and a tide provider, rather
than one fat "data source" interface.
"""

from __future__ import annotations

from typing import Protocol

from models.forecast import GridPoints, SunTimes, SwellData, TideEvent, WindData
from models.spot import Spot


class ForecastProvider(Protocol):
    """Supplies hourly swell and wind/weather data for a spot."""

    def get_swell(self, spot: Spot) -> list[SwellData]:
        """Hourly wave/swell series. Returns ``[]`` on failure (never raises)."""
        ...

    def get_wind(self, spot: Spot) -> list[WindData]:
        """Hourly wind/sky series. Returns ``[]`` on failure (never raises)."""
        ...

    def get_sun_times(self, spot: Spot) -> list[SunTimes]:
        """Daily sunrise/sunset series. Returns ``[]`` on failure (never raises)."""
        ...

    def get_grid_points(self, spot: Spot) -> GridPoints:
        """Model grid cells behind the forecast. Fields are ``None`` on failure."""
        ...


class TideProvider(Protocol):
    """Supplies tide events (highs/lows) for a spot over the next ``days``."""

    def get_tides(self, spot: Spot, days: int = 7) -> list[TideEvent]:
        """Tide events. Returns ``[]`` on failure (never raises)."""
        ...
