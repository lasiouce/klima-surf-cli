"""Open-Meteo adapter: marine (swell/wave) + weather (wind/sky) forecasts.

Outbound adapter implementing the ``ForecastProvider`` port. It owns all the
HTTP and JSON-mapping detail so the rest of the app only ever sees domain
objects (``SwellData`` / ``WindData``).

Per the project rule "the app must never crash on API failure", every fetch is
wrapped: on any network/HTTP/parse error we log and return ``[]``.

Both Open-Meteo endpoints are free, keyless, and return a 7-day hourly series.
We request ``timezone=GMT`` so timestamps come back as UTC, matching the
"store UTC, display Europe/Paris" convention.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from core.geo import is_offshore_wind
from models.forecast import SwellData, WindData
from models.spot import Spot

logger = logging.getLogger(__name__)

MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Hourly variables requested from each endpoint (kept as named constants rather
# than inline literals so the request shape is documented in one place).
_MARINE_VARS = [
    "wave_height",
    "wave_period",
    "wave_direction",
    "swell_wave_height",
    "swell_wave_period",
    "swell_wave_direction",
    "swell_wave_peak_period",
    "wind_wave_height",
]
_WEATHER_VARS = [
    "wind_speed_10m",
    "wind_direction_10m",
    "cloud_cover",
    "precipitation",
]

_DEFAULT_TIMEOUT_S = 10.0


def parse_utc(value: str) -> datetime:
    """Parse an Open-Meteo ISO timestamp (requested in GMT) as tz-aware UTC."""
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def fetch_hourly(
    client: httpx.Client, url: str, params: dict[str, float | str], spot_id: str
) -> dict[str, Any] | None:
    """GET ``url`` and return its ``hourly`` block, or ``None`` on any failure.

    Package-internal helper shared by the forecast and tide adapters: it
    centralises the "never crash on API failure" rule, so each adapter only
    deals with mapping the JSON it asked for. Any transport/HTTP-status/parse
    error is logged and swallowed.
    """
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        hourly = data["hourly"]
        if not isinstance(hourly, dict) or "time" not in hourly:
            raise KeyError("hourly")
        return hourly
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        logger.warning("Open-Meteo request failed for %s (%s): %s", spot_id, url, exc)
        return None


class OpenMeteoClient:
    """Concrete ``ForecastProvider`` backed by the Open-Meteo APIs."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        # Inject the httpx.Client (so tests can pass a mocked one); otherwise
        # build a sensible default.
        self._client = client or httpx.Client(timeout=_DEFAULT_TIMEOUT_S)

    def get_swell(self, spot: Spot) -> list[SwellData]:
        params: dict[str, float | str] = {
            "latitude": spot.lat,
            "longitude": spot.lon,
            "hourly": ",".join(_MARINE_VARS),
            "timezone": "GMT",
        }
        hourly = fetch_hourly(self._client, MARINE_URL, params, spot.id)
        if hourly is None:
            return []
        try:
            return [
                SwellData(
                    timestamp=parse_utc(t),
                    wave_height_m=hourly["wave_height"][i],
                    wave_period_s=hourly["wave_period"][i],
                    wave_direction_deg=hourly["wave_direction"][i],
                    swell_height_m=hourly["swell_wave_height"][i],
                    swell_period_s=hourly["swell_wave_period"][i],
                    swell_direction_deg=hourly["swell_wave_direction"][i],
                    wind_wave_height_m=hourly["wind_wave_height"][i],
                )
                for i, t in enumerate(hourly["time"])
            ]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("Malformed marine response for %s: %s", spot.id, exc)
            return []

    def get_wind(self, spot: Spot) -> list[WindData]:
        params: dict[str, float | str] = {
            "latitude": spot.lat,
            "longitude": spot.lon,
            "hourly": ",".join(_WEATHER_VARS),
            "timezone": "GMT",
        }
        hourly = fetch_hourly(self._client, WEATHER_URL, params, spot.id)
        if hourly is None:
            return []
        try:
            return [
                WindData(
                    timestamp=parse_utc(t),
                    speed_kmh=hourly["wind_speed_10m"][i],
                    direction_deg=hourly["wind_direction_10m"][i],
                    is_offshore=is_offshore_wind(
                        hourly["wind_direction_10m"][i], spot.offshore_direction_deg
                    ),
                    cloud_cover_pct=hourly["cloud_cover"][i],
                    precipitation_mm=hourly["precipitation"][i],
                )
                for i, t in enumerate(hourly["time"])
            ]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("Malformed weather response for %s: %s", spot.id, exc)
            return []
