"""Pure angular helpers for wind/swell direction logic.

Lives in ``core/`` (use-case layer) because it is reused by both the api
adapters (to set ``is_offshore`` when building ``WindData``) and the Phase 2
scorer. It depends on nothing — no models, no I/O — so it is trivially testable.
"""

from __future__ import annotations

import math

_EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometres.

    Used to measure how far a forecast's model grid cell sits from the actual
    spot — a spatial-precision signal. Pure maths, no I/O.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# Wind is considered offshore when it blows from within this many degrees of
# the spot's offshore direction (see CLAUDE.md: "offshore ± 45°").
DEFAULT_OFFSHORE_TOLERANCE_DEG = 45.0


def angular_difference(a: float, b: float) -> float:
    """Smallest absolute difference between two compass bearings, in [0, 180].

    Handles wrap-around at 0/360 (e.g. 350° and 10° are 20° apart).
    """
    diff = abs(a - b) % 360.0
    return 360.0 - diff if diff > 180.0 else diff


def is_offshore_wind(
    wind_from_deg: float,
    offshore_direction_deg: float,
    tolerance_deg: float = DEFAULT_OFFSHORE_TOLERANCE_DEG,
) -> bool:
    """True if wind blows from within ``tolerance_deg`` of the offshore direction.

    ``wind_from_deg`` is the direction the wind comes *from* (meteorological
    convention), which is exactly what "offshore_direction_deg" describes.
    """
    return angular_difference(wind_from_deg, offshore_direction_deg) <= tolerance_deg
