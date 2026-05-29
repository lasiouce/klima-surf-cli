# Surf Forecast App — Project Context for Claude Code

## Project overview

Python application that aggregates surf forecast data for spots in the French Basque Country (Biarritz, Anglet, Hossegor). 
It fetches swell, wind, tide, and weather data from external APIs, computes a session score per spot, 
and identifies the optimal surf window for each day.

---

## Architecture

```
klima-surf-cli/
├── CLAUDE.md               ← this file
├── main.py                 ← composition root / CLI entry point (wires adapters into core)
├── config/
│   ├── spots.json          ← spot definitions (name, coords, swell/tide/wind profile, timezone)
│   └── loader.py           ← JSON → Spot dataclasses
├── api/                    ← outbound adapters (implement core/ ports)
│   ├── open_meteo.py       ← swell + wind/weather + sun times + model grid points
│   └── open_meteo_tides.py ← tide events derived from Open-Meteo sea level
├── core/                   ← use cases (pure, depend only on models/ + ports)
│   ├── ports.py            ← ForecastProvider, TideProvider (typing.Protocol)
│   ├── geo.py              ← angular helpers (offshore logic) + haversine distance
│   ├── tides.py            ← derive high/low events from a sea-level series
│   ├── timeline.py         ← pick the day's daylight window, fold into ForecastBlocks
│   ├── score.py            ← session score calculator (0–10)         [PLANNED — Phase 2]
│   └── window.py           ← optimal scored session window finder    [PLANNED — Phase 2]
├── models/                 ← domain layer (frozen dataclasses, no I/O)
│   ├── forecast.py         ← SwellData, WindData, TideEvent, SunTimes, GridPoint(s),
│   │                          ForecastBlock, SessionScore
│   └── spot.py             ← Spot
└── output/
    └── formatter.py        ← CLI rendering (grouped by timezone; Telegram/WhatsApp/JSON planned)
```

> **Implementation status:** Phase 1 is built and enriched. `core/score.py` and
> `core/window.py` (scored windows) do not exist yet — they are the Phase 2 spec
> below. What exists today is `core/timeline.py`, which selects the relevant
> *daylight* window (no scoring) and aggregates it into `ForecastBlock`s for the
> CLI. `SessionScore` is defined in `models/` but not yet populated.

---

## Data sources

### Open-Meteo Marine API
- Base URL: `https://marine-api.open-meteo.com/v1/marine`
- Free, no API key, no rate limit for non-commercial use
- Params: `latitude`, `longitude`, `hourly` (list of variables), `timezone`
- Key variables to request:
  - `wave_height` — combined wave height (m)
  - `wave_period` — combined wave period (s)
  - `wave_direction` — combined wave direction (°)
  - `swell_wave_height` — primary swell height (m)
  - `swell_wave_period` — primary swell period (s)
  - `swell_wave_direction` — primary swell direction (°)
  - `swell_wave_peak_period` — primary swell peak period (s)
  - `wind_wave_height` — local wind wave height (m)
  - `sea_level_height_msl` — tide height vs mean sea level (m); high/low
    tide events are derived from this hourly series (see Tides below)
  - `sea_surface_temperature` — water temperature (°C) for the `Eau` line
- Returns hourly JSON for 7 days

### Open-Meteo Weather API
- Base URL: `https://api.open-meteo.com/v1/forecast`
- Same free tier, no key
- Key variables:
  - `wind_speed_10m` — wind speed at 10m (km/h)
  - `wind_direction_10m` — wind direction (°)
  - `cloud_cover` — cloud cover (%)
  - `precipitation` — precipitation (mm)
  - `sunrise` / `sunset` — daily (for golden hour)

### Tides (derived from Open-Meteo, no separate API)
- No dedicated tide service: we reuse the **Open-Meteo Marine API** above,
  requesting the hourly `sea_level_height_msl` series — free, keyless.
- `api/open_meteo_tides.py` (`OpenMeteoTideProvider`) fetches the series and
  hands it to `core/tides.py::derive_tide_events`, which finds the high/low
  **turning points** (local maxima/minima) of the curve.
- Trade-off vs a dedicated tide service: the French tide **coefficient** is
  *not* derivable from sea level, so `TideEvent.coefficient` is `None`. It can
  be backfilled later from an offline astronomical calendar. Tide *timing* is
  only as precise as the hourly sampling (±~30 min).
- (Historical: this replaced a TidesAtlas client, dropped because its free tier
  is capped at 50 requests.)

---

## Data models (`models/forecast.py`)

All models are `@dataclass(frozen=True)` (immutable, like a Java `record`).

```python
@dataclass(frozen=True)
class SwellData:                      # one hourly wave/swell sample
    timestamp: datetime
    wave_height_m: float
    wave_period_s: float
    wave_direction_deg: float
    swell_height_m: float
    swell_period_s: float
    swell_direction_deg: float
    wind_wave_height_m: float
    water_temp_c: float | None = None  # SST; None when the wave model omits it

@dataclass(frozen=True)
class WindData:                       # one hourly wind + sky sample
    timestamp: datetime
    speed_kmh: float
    direction_deg: float
    is_offshore: bool                 # computed from the spot orientation by the adapter
    cloud_cover_pct: float
    precipitation_mm: float

@dataclass(frozen=True)
class TideEvent:
    time: datetime
    height_m: float
    is_high: bool
    trend: str                        # "rising" | "falling"
    coefficient: int | None = None    # French 20–120 scale; None (not derivable from sea level)

@dataclass(frozen=True)
class SunTimes:                       # daylight bounds for one day at a spot
    date: date
    sunrise: datetime
    sunset: datetime

@dataclass(frozen=True)
class GridPoint:                      # the model grid cell Open-Meteo actually used
    latitude: float
    longitude: float

@dataclass(frozen=True)
class GridPoints:                     # grid cells behind a spot's forecast (None on probe failure)
    marine: GridPoint | None
    weather: GridPoint | None

@dataclass(frozen=True)
class ForecastBlock:                  # conditions folded over a short window (default 2h)
    start: datetime
    end: datetime
    wave_height_min_m: float          # linear quantities → min–max range over the block
    wave_height_max_m: float
    swell_period_s: float             # period + directions taken from the block's first hour
    swell_direction_deg: float        # (averaging compass bearings is a circular-math trap)
    wind_speed_min_kmh: float
    wind_speed_max_kmh: float
    wind_direction_deg: float
    is_offshore: bool
    cloud_cover_min_pct: float
    cloud_cover_max_pct: float
    precipitation_mm_total: float     # accumulated over the block
    water_temp_c: float | None = None

@dataclass(frozen=True)
class SessionScore:                   # PLANNED — defined, populated by core/score.py in Phase 2
    timestamp: datetime
    score: float                      # 0.0–10.0
    label: str                        # "FLAT" | "POOR" | "FAIR" | "GOOD" | "EPIC"
    swell_score: float
    wind_score: float
    tide_score: float
    notes: list[str] = field(default_factory=list)  # human-readable explanation
```

---

## Scoring logic (`core/score.py`)

### Overall score
```
score = (swell_score * 0.45) + (wind_score * 0.35) + (tide_score * 0.20)
```

### Swell score (0–10)
| Factor | Rule |
|---|---|
| Wave height | 0.3–0.6m = 3pts, 0.6–1.2m = 6pts, 1.2–2.0m = 9pts, 2.0–3.0m = 10pts, >3.0m = drops |
| Period | <8s = 0, 8–10s = 4, 10–13s = 7, 13–16s = 9, >16s = 10 |
| Swell direction | Must match spot's optimal window ± 45°, else penalty |
| Swell cleanliness | wind_wave_height / swell_height < 0.3 = clean bonus |

### Wind score (0–10)
| Factor | Rule |
|---|---|
| Offshore | speed < 15 km/h = 10, 15–25 km/h = 8, > 25 km/h = 4 |
| Cross-shore | speed < 10 km/h = 7, else 4 |
| Onshore | score = max(0, 5 - speed/5) |
| Glassy (< 5 km/h any dir) | bonus +1 |

### Tide score (0–10)
Each spot has a tide profile in `config/spots.json` defining optimal tide window:
```json
{
  "optimal_tide": "mid_rising",   // "low" | "low_mid" | "mid" | "mid_rising" | "high" | "any"
  "min_height_m": 1.0,
  "max_height_m": 2.8,
  "coefficient_bonus": 80         // springs score higher if > this value
}
```
Score based on: height in optimal range + correct trend + coefficient bonus.

### Score labels
| Score | Label |
|---|---|
| 0–2 | FLAT |
| 2–4 | POOR |
| 4–6 | FAIR |
| 6–8 | GOOD |
| 8–10 | EPIC |

---

## Spot config (`config/spots.json`)

```json
[
  {
    "id": "la_barre",
    "name": "Anglet - La Barre",
    "lat": 43.535,
    "lon": -1.562,
    "optimal_swell_direction_deg": 290,
    "swell_window_deg": 45,
    "optimal_tide": "mid_rising",
    "min_height_m": 1.2,
    "max_height_m": 3.0,
    "coefficient_bonus": 70,
    "offshore_direction_deg": 100
  },
  {
    "id": "grande_plage",
    "name": "Biarritz - Grande Plage",
    "lat": 43.483,
    "lon": -1.558,
    "optimal_swell_direction_deg": 285,
    "swell_window_deg": 50,
    "optimal_tide": "low_mid",
    "min_height_m": 0.8,
    "max_height_m": 2.5,
    "coefficient_bonus": 60,
    "offshore_direction_deg": 110
  },
  {
    "id": "cote_des_basques",
    "name": "Biarritz - Côte des Basques",
    "lat": 43.476,
    "lon": -1.567,
    "optimal_swell_direction_deg": 285,
    "swell_window_deg": 50,
    "optimal_tide": "low",
    "min_height_m": 0.5,
    "max_height_m": 2.0,
    "coefficient_bonus": 75,
    "offshore_direction_deg": 110
  },
  {
    "id": "hossegor_graviere",
    "name": "Hossegor - La Gravière",
    "lat": 43.665,
    "lon": -1.440,
    "optimal_swell_direction_deg": 275,
    "swell_window_deg": 40,
    "optimal_tide": "low",
    "min_height_m": 1.5,
    "max_height_m": 4.0,
    "coefficient_bonus": 85,
    "offshore_direction_deg": 90
  }
]
```

Each entry also accepts an optional `"timezone"` (IANA name) used to display the
spot's times and group it in the output; it defaults to `"Europe/Paris"` (the
whole French Basque Country), so existing config without the key keeps working.

---

## Environment variables (`.env`)

```
# No key needed for forecast/tide data — all from Open-Meteo (free, keyless).
TELEGRAM_BOT_TOKEN=optional
TELEGRAM_CHAT_ID=optional

# WhatsApp (Meta WhatsApp Cloud API) — optional
WHATSAPP_ACCESS_TOKEN=optional      # permanent/system-user token from Meta
WHATSAPP_PHONE_NUMBER_ID=optional   # sender phone number ID
WHATSAPP_RECIPIENT=optional         # recipient number in E.164 format, e.g. 33612345678
```

---

## Key conventions

- All timestamps in **UTC**, displayed in **Europe/Paris** timezone
- Wind directions follow meteorological convention (direction the wind comes **from**)
- Swell directions follow oceanographic convention (direction the swell travels **toward**)
- Offshore wind = wind direction ≈ spot's `offshore_direction_deg` ± 45°
- Tide coefficient: French standard 20–120 (vives-eaux > 95, mortes-eaux < 45)
- Wave height in **metres** (not feet)
- All API calls should be wrapped in `try/except` with logged errors — app must never crash on API failure
- Cache API responses locally for 3h (simple JSON file cache) to avoid hammering free tiers

---

## Engineering practices & technical choices

These rules are mandatory for all code written in this project.

### Clean Architecture (layering)

Dependencies point **inward**: the domain knows nothing about the outside world; adapters depend on the domain, never the reverse. The existing folders map directly to layers:

| Layer | Folder | Rules |
|---|---|---|
| Domain | `models/` | Pure entities/dataclasses. **No** I/O, no `httpx`, no framework imports. |
| Use cases | `core/` | Business logic (scoring, window finding). Depends **only** on `models/`. Receives data through `Protocol` interfaces — never calls an API directly. |
| Inbound/outbound adapters | `api/` | External-service clients (Open-Meteo marine/weather/tides). Implement the `Protocol`s the use cases depend on. |
| Presentation adapters | `output/` | CLI, Telegram, WhatsApp, JSON renderers. Depend on `models/`, not the other way around. |
| Composition root | `main.py` | Instantiate adapters and inject them into `core/`. **No business logic here.** |

### SOLID

- **SRP** — one reason to change per module: `score.py` only scores, `window.py` only finds windows, each adapter only talks to its one service.
- **OCP** — add a new spot via `config/spots.json` and a new notification channel via a new adapter, **without** editing `core/`.
- **LSP** — every forecast provider / notifier is fully substitutable behind its `Protocol`.
- **ISP** — prefer small, focused `Protocol`s (`ForecastProvider`, `TideProvider`, `Notifier`) over one fat interface.
- **DIP** — `core/` depends on abstractions (`typing.Protocol`); concrete clients are injected from `main.py`.

### TDD (test-driven, non-negotiable)

- Red → green → refactor: write the failing test **before** the implementation.
- `pytest`; target **≥ 80 % coverage**, with `core/` (pure scoring/window logic) close to 100 %.
- Mock external HTTP with `respx`/recorded fixtures — **never hit live APIs in tests**.
- `core/` functions are pure: given `SwellData` / `WindData` / `TideEvent`, assert the resulting `SessionScore`. Deterministic, no clock/network dependence (inject `now` where time matters).

### Clean code

- Full type hints everywhere; `mypy --strict` must pass.
- Small, pure, single-purpose functions; descriptive names; early returns over nested conditionals.
- No magic numbers — scoring thresholds and weights live in named constants (or config), not inline literals.
- Lint & format with **ruff** + **black**; imports sorted by ruff.
- **Conventional Commits** (`feat:`, `fix:`, `test:`, `refactor:`…).

### Dev tooling (add to `pyproject.toml` `[project.optional-dependencies].dev`)

```toml
[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-cov",
    "respx",     # httpx request mocking
    "mypy",
    "ruff",
    "black",
]
```

---

## Daylight timeline (`core/timeline.py`) — implemented

Today's view layer (no scoring). Given a spot's `SunTimes` plus the hourly
`SwellData` / `WindData` series, it picks the relevant day and folds its daylight
into `ForecastBlock`s. Both `now` and the local `tz` are **injected** so the
module stays pure and deterministic (no clock/timezone hard-coding).

- **Which day** (`select_sun`): asked **before noon** local → plan **today**
  (window clamped to `now` so past hours drop); asked **at/after noon** → plan
  **tomorrow** (full sunrise→sunset).
- **`daylight_blocks(...)`** returns `list[ForecastBlock]`, each `block_h`
  hours (default 2), covering only daylight. Blocks with no swell *or* wind data
  in range are skipped, so a partial series yields fewer blocks rather than
  raising.

## Scored session window finder (`core/window.py`) — PLANNED (Phase 2)

Given an array of `SessionScore` objects for a day, find the best contiguous block of hours where:
1. Score ≥ threshold (default 6.0)
2. Block is at least 2 hours long
3. Sunrise ≤ window start and window end ≤ sunset (daylight only)

Return: `(start_time, end_time, peak_score_time, avg_score)`

## Geo helpers (`core/geo.py`) — implemented

Pure angular/distance maths, reused by the adapters and (later) the scorer:
`angular_difference`, `is_offshore_wind` (wind from within ±45° of the spot's
`offshore_direction_deg`), and `haversine_km` (great-circle distance, used to
report how far each model grid cell sits from the spot — a spatial-precision
signal shown in the CLI).

---

## Output format (CLI example)

Spots are **grouped by timezone**; the shared day, daylight, lead time and data
source head the group once, then each spot shows its daylight `ForecastBlock`
rows and tide line. (Scoring/window — the `Score`/`Fenêtre` lines — arrives in
Phase 2.) The tide `coefficient` is `None` from Open-Meteo, so the `| Coeff`
suffix only appears once it is backfilled.

```
🕒 prévision pour : Europe/Paris — Ven 29 mai (aujourd'hui)
☀️ lever 06h28 → coucher 21h38
📡 vagues : Open-Meteo Marine · météo : Open-Meteo · récupéré à 18h32

🌊 Anglet - La Barre
🌡️ Eau : 17°C
📡 point de grille : vagues 2.3 km · météo 0.6 km
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
18h00→20h00  1.2–1.4m 13s WSW  ·  12 km/h offshore ✅ (E)  ·  ☁️ 40% 0.0mm
20h00→21h38  1.3–1.5m 13s WSW  ·  10–14 km/h offshore ✅ (E)  ·  ☁️ 30–50% 0.2mm
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Marée  : BM 17h45 (0.8m) → PM 23h10 (3.2m)
```

---

## Development phases

1. **Phase 1** — ✅ **Done.** API clients (`api/`) + dataclasses (`models/`) +
   config loader + CLI output. Enriched beyond the original scope with
   `core/timeline.py` (daylight-block view), `core/geo.py`, timezone grouping,
   model grid-point distance, and sea-temperature display.
2. **Phase 2** — Score calculator (`core/score.py`) + scored window finder (`core/window.py`)
3. **Phase 3** — Multi-spot support + config-driven spot profiles (config loader done; scoring-driven profiles pending Phase 2)
4. **Phase 4** — Notification channels: Telegram bot + WhatsApp (Meta WhatsApp Cloud API) integration
5. **Phase 5** — Caching layer + scheduling (cron or APScheduler)

##  Development Style

The goal of this project is learning. It involves using suggestion, knowledge transfer, and pedagogy in the development process. 
I have been a Java developer for 8 years and I want to learn Python

## Dependencies

Defined in `pyproject.toml`; install with `pip install -e ".[dev]"`.

```toml
# pyproject.toml
[project]
requires-python = ">=3.11"
dependencies = [
    "httpx",         # HTTP client (used synchronously in Phase 1)
    "python-dotenv", # .env loading
    "pydantic",      # validation of raw API JSON at the api/ boundary
    "rich",          # CLI formatting
]
```

`apscheduler` is deferred to Phase 5 (scheduling) and is **not** a current
dependency. Dev tooling (`pytest`, `pytest-cov`, `respx`, `mypy`, `ruff`,
`black`) lives in `[project.optional-dependencies].dev`.
