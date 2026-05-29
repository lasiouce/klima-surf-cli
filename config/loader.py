"""Load surf-spot definitions from JSON into domain `Spot` objects.

This sits at the edge of the domain: it reads a file (I/O) and maps raw dicts
to the pure `Spot` dataclass, so the rest of the app never touches JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

from models.spot import Spot

# Default location of the shipped config, relative to the project root.
DEFAULT_SPOTS_PATH = Path("config/spots.json")


def load_spots(path: Path = DEFAULT_SPOTS_PATH) -> list[Spot]:
    """Read `path` and return the configured spots.

    Raises `FileNotFoundError` if the file is missing — config is required, so
    we fail loudly here (unlike API calls, which must degrade gracefully).
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    # `**entry` unpacks the dict as keyword arguments — the keys in spots.json
    # match the Spot field names exactly, so this maps straight onto the
    # dataclass constructor (Java: like a constructor taking each field).
    return [Spot(**entry) for entry in raw]
