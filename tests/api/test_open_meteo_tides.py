"""Tests for the Open-Meteo tide adapter (HTTP mocked with respx).

We never hit the live API: respx intercepts the request and returns a canned
hourly ``sea_level_height_msl`` series, so we exercise real request-building and
the JSON → ``TideEvent`` mapping (turning-point detection lives in
``core.tides`` and is tested separately).
"""

from __future__ import annotations

from datetime import UTC

import httpx
import pytest
import respx

from api.open_meteo_tides import OpenMeteoTideProvider
from models.forecast import TideEvent
from models.spot import Spot

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"

SPOT = Spot(
    id="la_barre",
    name="Anglet - La Barre",
    lat=43.535,
    lon=-1.562,
    optimal_swell_direction_deg=290,
    swell_window_deg=45,
    optimal_tide="mid_rising",
    min_height_m=1.2,
    max_height_m=3.0,
    coefficient_bonus=70,
    offshore_direction_deg=100,
)

# A low at 02:00 (0.5m) and a high at 05:00 (3.2m).
SEA_LEVEL_JSON = {
    "hourly": {
        "time": [
            "2026-05-28T00:00",
            "2026-05-28T01:00",
            "2026-05-28T02:00",
            "2026-05-28T03:00",
            "2026-05-28T04:00",
            "2026-05-28T05:00",
            "2026-05-28T06:00",
        ],
        "sea_level_height_msl": [2.0, 1.0, 0.5, 1.5, 2.8, 3.2, 2.6],
    }
}


@pytest.fixture
def client() -> OpenMeteoTideProvider:
    return OpenMeteoTideProvider(client=httpx.Client(timeout=5.0))


@respx.mock
def test_get_tides_derives_events_from_sea_level(client: OpenMeteoTideProvider) -> None:
    respx.get(MARINE_URL).mock(return_value=httpx.Response(200, json=SEA_LEVEL_JSON))

    tides = client.get_tides(SPOT)

    assert len(tides) == 2
    low, high = tides
    assert isinstance(low, TideEvent)
    assert low.is_high is False
    assert low.height_m == pytest.approx(0.5)
    assert low.trend == "rising"
    assert low.coefficient is None  # not derivable from sea level
    assert low.time.tzinfo == UTC
    assert low.time.hour == 2

    assert high.is_high is True
    assert high.trend == "falling"


@respx.mock
def test_get_tides_requests_sea_level_for_spot(client: OpenMeteoTideProvider) -> None:
    route = respx.get(MARINE_URL).mock(return_value=httpx.Response(200, json=SEA_LEVEL_JSON))

    client.get_tides(SPOT, days=3)

    request = route.calls.last.request
    assert request.url.params["latitude"] == "43.535"
    assert request.url.params["hourly"] == "sea_level_height_msl"
    assert request.url.params["forecast_days"] == "3"


@respx.mock
def test_get_tides_returns_empty_on_http_error(client: OpenMeteoTideProvider) -> None:
    respx.get(MARINE_URL).mock(return_value=httpx.Response(500))

    assert client.get_tides(SPOT) == []


@respx.mock
def test_get_tides_returns_empty_on_malformed_json(client: OpenMeteoTideProvider) -> None:
    respx.get(MARINE_URL).mock(return_value=httpx.Response(200, json={"nope": []}))

    assert client.get_tides(SPOT) == []


@respx.mock
def test_get_tides_returns_empty_on_inconsistent_arrays(client: OpenMeteoTideProvider) -> None:
    """A data array shorter than `time` is handled, not crashed on."""
    broken = {
        "hourly": {
            "time": ["2026-05-28T00:00", "2026-05-28T01:00", "2026-05-28T02:00"],
            "sea_level_height_msl": [2.0, 1.0],
        }
    }
    respx.get(MARINE_URL).mock(return_value=httpx.Response(200, json=broken))

    assert client.get_tides(SPOT) == []
