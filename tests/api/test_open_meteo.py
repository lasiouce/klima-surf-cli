"""Tests for the Open-Meteo adapter.

External HTTP is mocked with `respx` — we never hit the live API. Each test
spins up a real `httpx.Client`; respx intercepts requests at the transport
layer and returns our canned JSON, so we exercise the real request-building and
JSON-mapping code without a network.
"""

from __future__ import annotations

from datetime import UTC

import httpx
import pytest
import respx

from api.open_meteo import OpenMeteoClient
from models.forecast import SwellData, WindData
from models.spot import Spot

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

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

MARINE_JSON = {
    "latitude": 43.535,
    "longitude": -1.562,
    "hourly": {
        "time": ["2026-05-28T00:00", "2026-05-28T01:00"],
        "wave_height": [1.8, 1.9],
        "wave_period": [13.0, 12.5],
        "wave_direction": [285.0, 288.0],
        "swell_wave_height": [1.6, 1.7],
        "swell_wave_period": [14.0, 13.5],
        "swell_wave_direction": [290.0, 292.0],
        "swell_wave_peak_period": [15.0, 14.0],
        "wind_wave_height": [0.4, 0.5],
    },
}

WEATHER_JSON = {
    "hourly": {
        "time": ["2026-05-28T00:00", "2026-05-28T01:00"],
        "wind_speed_10m": [12.0, 22.0],
        "wind_direction_10m": [100.0, 250.0],  # 100° = offshore, 250° = onshore
        "cloud_cover": [40.0, 60.0],
        "precipitation": [0.0, 0.2],
    },
}


@pytest.fixture
def client() -> OpenMeteoClient:
    return OpenMeteoClient(client=httpx.Client(timeout=5.0))


@respx.mock
def test_get_swell_maps_hourly_series(client: OpenMeteoClient) -> None:
    respx.get(MARINE_URL).mock(return_value=httpx.Response(200, json=MARINE_JSON))

    swell = client.get_swell(SPOT)

    assert len(swell) == 2
    first = swell[0]
    assert isinstance(first, SwellData)
    assert first.wave_height_m == pytest.approx(1.8)
    assert first.swell_period_s == pytest.approx(14.0)
    assert first.swell_direction_deg == pytest.approx(290.0)
    assert first.wind_wave_height_m == pytest.approx(0.4)
    # Timestamps stored as tz-aware UTC.
    assert first.timestamp.tzinfo == UTC
    assert first.timestamp.hour == 0


@respx.mock
def test_get_swell_sends_spot_coordinates(client: OpenMeteoClient) -> None:
    route = respx.get(MARINE_URL).mock(return_value=httpx.Response(200, json=MARINE_JSON))

    client.get_swell(SPOT)

    request = route.calls.last.request
    assert request.url.params["latitude"] == "43.535"
    assert request.url.params["longitude"] == "-1.562"
    assert "swell_wave_height" in request.url.params["hourly"]


@respx.mock
def test_get_wind_maps_and_computes_offshore(client: OpenMeteoClient) -> None:
    respx.get(WEATHER_URL).mock(return_value=httpx.Response(200, json=WEATHER_JSON))

    wind = client.get_wind(SPOT)

    assert len(wind) == 2
    assert isinstance(wind[0], WindData)
    assert wind[0].speed_kmh == pytest.approx(12.0)
    assert wind[0].is_offshore is True  # 100° wind vs 100° offshore dir
    assert wind[0].cloud_cover_pct == pytest.approx(40.0)
    assert wind[1].is_offshore is False  # 250° wind is onshore


@respx.mock
def test_get_swell_returns_empty_on_http_error(client: OpenMeteoClient) -> None:
    respx.get(MARINE_URL).mock(return_value=httpx.Response(500))

    assert client.get_swell(SPOT) == []


@respx.mock
def test_get_wind_returns_empty_on_network_error(client: OpenMeteoClient) -> None:
    respx.get(WEATHER_URL).mock(side_effect=httpx.ConnectError("boom"))

    assert client.get_wind(SPOT) == []


@respx.mock
def test_get_swell_returns_empty_on_malformed_json(client: OpenMeteoClient) -> None:
    respx.get(MARINE_URL).mock(return_value=httpx.Response(200, json={"unexpected": "shape"}))

    assert client.get_swell(SPOT) == []


@respx.mock
def test_get_swell_returns_empty_when_hourly_missing_time(client: OpenMeteoClient) -> None:
    """`hourly` block present but without a `time` key → handled gracefully."""
    respx.get(MARINE_URL).mock(return_value=httpx.Response(200, json={"hourly": {"foo": []}}))

    assert client.get_swell(SPOT) == []


@respx.mock
def test_get_swell_returns_empty_on_inconsistent_arrays(client: OpenMeteoClient) -> None:
    """`hourly` present but a data array is shorter than `time` → handled, not crash."""
    broken = {"hourly": {"time": ["2026-05-28T00:00", "2026-05-28T01:00"], "wave_height": [1.8]}}
    respx.get(MARINE_URL).mock(return_value=httpx.Response(200, json=broken))

    assert client.get_swell(SPOT) == []


@respx.mock
def test_get_wind_returns_empty_on_inconsistent_arrays(client: OpenMeteoClient) -> None:
    broken = {"hourly": {"time": ["2026-05-28T00:00", "2026-05-28T01:00"], "wind_speed_10m": [12]}}
    respx.get(WEATHER_URL).mock(return_value=httpx.Response(200, json=broken))

    assert client.get_wind(SPOT) == []
