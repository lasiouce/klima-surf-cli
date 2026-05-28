# Surf Forecast App — Project Context for Claude Code

## Project overview

Python application that aggregates surf forecast data for spots in the French Basque Country (Biarritz, Anglet, Hossegor). 
It fetches swell, wind, tide, and weather data from external APIs, computes a session score per spot, 
and identifies the optimal surf window for each day.

---

## Architecture

```
surf-forecast-scrapper/
├── CLAUDE.md               ← this file
├── main.py                 ← entry point (CLI or scheduler)
├── config/
│   └── spots.json          ← spot definitions (name, coords, tide profile)
├── api/
│   ├── open_meteo.py       ← swell + wind + weather (Open-Meteo Marine)
│   └── tides_atlas.py      ← tide times + heights (TidesAtlas)
├── core/
│   ├── score.py            ← session score calculator (0–10)
│   └── window.py           ← optimal session window finder
├── models/
│   └── forecast.py         ← dataclasses: SwellData, TideData, WindData, SessionScore
└── output/
    └── formatter.py        ← CLI display / Telegram / JSON
```

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

### TidesAtlas API
- Base URL: `https://tidesatlas.com/api/v1`
- Free tier with API key (register at tidesatlas.com)
- API key stored in `.env` as `TIDES_ATLAS_KEY`
- Key endpoint: `GET /tides?lat={lat}&lon={lon}&days={n}&include=tides`
- Returns: high/low tide times, heights (m), tide coefficient

---

## Data models (`models/forecast.py`)

```python
@dataclass
class SwellData:
    timestamp: datetime
    wave_height_m: float
    wave_period_s: float
    wave_direction_deg: float
    swell_height_m: float
    swell_period_s: float
    swell_direction_deg: float
    wind_wave_height_m: float

@dataclass
class WindData:
    timestamp: datetime
    speed_kmh: float
    direction_deg: float
    is_offshore: bool           # computed from spot orientation
    cloud_cover_pct: float
    precipitation_mm: float

@dataclass
class TideEvent:
    time: datetime
    height_m: float
    is_high: bool
    coefficient: int            # 20–120 scale (French standard)
    trend: str                  # "rising" | "falling"

@dataclass
class SessionScore:
    timestamp: datetime
    score: float                # 0.0–10.0
    label: str                  # "FLAT" | "POOR" | "FAIR" | "GOOD" | "EPIC"
    swell_score: float
    wind_score: float
    tide_score: float
    notes: list[str]            # human-readable explanation
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

---

## Environment variables (`.env`)

```
TIDES_ATLAS_KEY=your_key_here
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
| Inbound/outbound adapters | `api/` | External-service clients (Open-Meteo, TidesAtlas). Implement the `Protocol`s the use cases depend on. |
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

## Session window finder (`core/window.py`)

Given an array of `SessionScore` objects for a day, find the best contiguous block of hours where:
1. Score ≥ threshold (default 6.0)
2. Block is at least 2 hours long
3. Sunrise ≤ window start and window end ≤ sunset (daylight only)

Return: `(start_time, end_time, peak_score_time, avg_score)`

---

## Output format (CLI example)

```
🌊 La Barre — Mercredi 28 mai
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Score     : ████████░░  8.1/10  GOOD
Fenêtre   : 07h00 → 10h30

Houle     : 1.8m — 13s — WSW (285°)
Vent      : 12 km/h offshore (E) ✅
Marée     : Montante | BM 05h45 (0.8m) → HM 12h10 (3.2m)
Coeff     : 88 (vives-eaux)
Eau       : 17°C
Météo     : ☁️ 40% nuages, 0mm pluie
```

---

## Development phases

1. **Phase 1** — API clients (`api/`) + dataclasses (`models/`) + basic CLI output
2. **Phase 2** — Score calculator (`core/score.py`) + window finder (`core/window.py`)
3. **Phase 3** — Multi-spot support + config-driven spot profiles
4. **Phase 4** — Notification channels: Telegram bot + WhatsApp (Meta WhatsApp Cloud API) integration
5. **Phase 5** — Caching layer + scheduling (cron or APScheduler)

---

## Dependencies

```toml
# pyproject.toml
[project]
requires-python = ">=3.11"
dependencies = [
    "httpx",           # async HTTP client
    "python-dotenv",   # .env loading
    "pydantic",        # data validation
    "rich",            # CLI formatting
    "apscheduler",     # optional scheduling
]
```

Install: `pip install httpx python-dotenv pydantic rich apscheduler`
