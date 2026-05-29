"""Surf spot definition.

A ``Spot`` is the static profile of a break (location + the parameters scoring
will need later). It is a domain entity: pure data, loaded from
``config/spots.json`` by ``config/loader.py``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Spot:
    id: str
    name: str
    lat: float
    lon: float
    optimal_swell_direction_deg: float
    swell_window_deg: float
    optimal_tide: str  # "low" | "low_mid" | "mid" | "mid_rising" | "high" | "any"
    min_height_m: float
    max_height_m: float
    coefficient_bonus: int
    offshore_direction_deg: float
