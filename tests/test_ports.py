"""Conformance smoke test for the ports (DIP contract).

The real guarantee that the adapters implement the Protocols is enforced
statically by `mypy --strict` (structural typing). This test just pins the
contract at runtime: the concrete clients can be bound to the port-typed names,
and expose the expected methods. It also gives the type-only `core.ports`
module import-time coverage.
"""

from __future__ import annotations

from api.open_meteo import OpenMeteoClient
from api.open_meteo_tides import OpenMeteoTideProvider
from core.ports import ForecastProvider, TideProvider


def test_open_meteo_satisfies_forecast_provider() -> None:
    provider: ForecastProvider = OpenMeteoClient()
    assert hasattr(provider, "get_swell")
    assert hasattr(provider, "get_wind")


def test_open_meteo_tides_satisfies_tide_provider() -> None:
    provider: TideProvider = OpenMeteoTideProvider()
    assert hasattr(provider, "get_tides")
