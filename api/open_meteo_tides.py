"""Open-Meteo tide adapter: high/low tide events from the free Marine API.

Outbound adapter implementing the ``TideProvider`` port, replacing the old
(paid-after-50-requests) TidesAtlas client. Open-Meteo has no "tide events"
endpoint, so we request the hourly ``sea_level_height_msl`` series — free,
keyless, same Marine API the swell data already comes from — and hand it to the
pure ``core.tides.derive_tide_events`` helper, which finds the high/low turning
points.

Per the project rule "the app must never crash on API failure", a failed or
malformed fetch logs and returns ``[]`` (degraded, not crashing). The French
tide ``coefficient`` is unavailable from sea level alone, so events carry
``coefficient=None``.
"""

from __future__ import annotations

import logging

import httpx

from api.open_meteo import MARINE_URL, fetch_hourly, parse_utc
from core.tides import derive_tide_events
from models.forecast import TideEvent
from models.spot import Spot

logger = logging.getLogger(__name__)

_TIDE_VAR = "sea_level_height_msl"
_DEFAULT_TIMEOUT_S = 10.0


class OpenMeteoTideProvider:
    """Concrete ``TideProvider`` backed by Open-Meteo's sea-level series."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        # Inject the httpx.Client (so tests can pass a mocked one); otherwise
        # build a sensible default — same pattern as OpenMeteoClient.
        self._client = client or httpx.Client(timeout=_DEFAULT_TIMEOUT_S)

    def get_tides(self, spot: Spot, days: int = 7) -> list[TideEvent]:
        params: dict[str, float | str] = {
            "latitude": spot.lat,
            "longitude": spot.lon,
            "hourly": _TIDE_VAR,
            "timezone": "GMT",
            "forecast_days": days,
        }
        hourly = fetch_hourly(self._client, MARINE_URL, params, spot.id)
        if hourly is None:
            return []
        try:
            series = [
                (parse_utc(t), float(h))
                for t, h in zip(hourly["time"], hourly[_TIDE_VAR], strict=True)
            ]
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Malformed sea-level response for %s: %s", spot.id, exc)
            return []
        return derive_tide_events(series)
