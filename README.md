# 🌊 klima-surf-cli

Aggregates surf-forecast data for spots on the **French Basque Country** coast
(Biarritz, Anglet, Hossegor). It fetches swell, wind, tide and weather data from
free public APIs, and (as the scoring engine lands) computes a per-spot session
score and the optimal surf window for each day.

> **Status:** Phase 1 is implemented — API clients, domain models, config
> loading, a daylight-window timeline (`core/timeline.py`) and a timezone-grouped
> CLI forecast view. Session *scoring*, the scored-window finder and notification
> channels are on the [roadmap](#roadmap).

---

## Features

**Available today**

- Fetches **swell & wave** data (height, period, direction, clean vs. wind-wave)
  from the keyless Open-Meteo Marine API.
- Fetches **wind & sky** data (speed, direction, cloud cover, precipitation)
  from the Open-Meteo Weather API, and derives whether the wind is *offshore*
  for each spot.
- Derives **tide** events (high/low times & heights) from Open-Meteo's hourly
  sea-level series — also keyless. (The French tide *coefficient* isn't available
  from this source, so it's shown only if backfilled later.)
- Shows the **relevant daylight window** as 2-hour `ForecastBlock` rows: asked
  before noon it plans **today** (from now to sunset), at/after noon it plans
  **tomorrow** (full day). Each block summarises wave height and wind as a
  min–max range.
- Reports the **model grid-point distance** (how far Open-Meteo's marine/weather
  grid cells sit from the spot) and the day's mean **sea temperature** — honest
  spatial-precision and data-provenance signals.
- Config-driven, multi-spot: add a break by editing `config/spots.json`, no code
  change required. Spots are **grouped by timezone** in the output (with an
  optional per-spot `timezone`, default `Europe/Paris`).
- Resilient by design — any API failure is logged and degrades gracefully
  (empty data) rather than crashing the app.
- Rich CLI output, in French, with all times displayed in each spot's timezone.

**Planned** — session scoring (0–10), best-window finder, Telegram & WhatsApp
notifications, and a local response cache. See the [roadmap](#roadmap).

### Example CLI output

Spots in a timezone share one header (day, daylight, lead time, data source);
each spot then lists its daylight blocks and tide line.

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

> The tide *coefficient* is `None` from Open-Meteo, so the `| Coeff` suffix only
> appears once a value is backfilled. The score/window lines arrive in Phase 2.

---

## Tech stack

| Concern        | Choice |
|----------------|--------|
| Language       | Python ≥ 3.11 |
| HTTP client    | `httpx` |
| Config / env   | `python-dotenv` |
| Validation     | `pydantic` |
| CLI rendering  | `rich` |
| Tests          | `pytest`, `pytest-cov`, `respx` (HTTP mocking) |
| Typing / lint  | `mypy --strict`, `ruff`, `black` |

Data sources (all free):

- **Open-Meteo Marine** — `https://marine-api.open-meteo.com/v1/marine` (keyless)
  — swell/waves, plus `sea_level_height_msl` (tides) and water temperature
- **Open-Meteo Weather** — `https://api.open-meteo.com/v1/forecast` (keyless)

No API keys are required for forecast data.

---

## Architecture

The project follows **Clean Architecture**: dependencies point *inward*. The
domain knows nothing about the outside world; adapters depend on the domain,
never the reverse. Decoupling is achieved with `typing.Protocol` "ports"
(structural interfaces) injected from the composition root.

```
klima-surf-cli/
├── main.py              # Composition root / CLI entry point — wires everything, no business logic
├── config/
│   ├── spots.json       # Spot definitions (coords, swell/tide/wind profile)
│   └── loader.py        # JSON → Spot dataclasses
├── models/              # Domain layer — pure frozen dataclasses, no I/O
│   ├── forecast.py      # SwellData, WindData, TideEvent, SunTimes, GridPoint(s),
│   │                    #   ForecastBlock, SessionScore
│   └── spot.py          # Spot (incl. optional per-spot timezone)
├── core/                # Use-case layer — depends only on models/ + ports
│   ├── ports.py         # ForecastProvider, TideProvider (Protocols)
│   ├── geo.py           # Angular helpers (offshore-wind logic) + haversine distance
│   ├── tides.py         # Pure high/low derivation from a sea-level series
│   └── timeline.py      # Pick the day's daylight window, fold it into ForecastBlocks
├── api/                 # Outbound adapters — implement the ports
│   ├── open_meteo.py        # Swell + wind/weather + sun times + model grid points
│   └── open_meteo_tides.py  # Tide events from Open-Meteo sea level
└── output/              # Presentation adapters — depend on models/
    └── formatter.py     # CLI text rendering (grouped by timezone)
```

### Layers

| Layer | Folder | Rule |
|-------|--------|------|
| Domain | `models/` | Pure entities. No I/O, no `httpx`, no framework imports. |
| Use cases | `core/` | Business logic. Depends only on `models/`, talks to the world via `Protocol` ports. |
| Outbound adapters | `api/` | External-service clients implementing the ports. |
| Presentation adapters | `output/` | CLI / Telegram / WhatsApp / JSON renderers. |
| Composition root | `main.py` | Builds adapters and injects them into `core/`. No business logic. |

### Dependency flow

```
main.py ──constructs──▶ api/ (OpenMeteoClient, OpenMeteoTideProvider)
   │                      │ implements
   │                      ▼
   └──injects──▶ core/ports.py (ForecastProvider, TideProvider)  ◀── core/ depends on these
                          │
                          ▼
                      models/ (pure domain)  ◀── everything depends inward on this
```

`core/` and `main.py` depend on the **abstractions** in `core/ports.py`; the
concrete `api/` clients are injected at runtime, so a provider can be swapped or
mocked without touching business logic.

---

## Getting started

### Prerequisites

- Python **3.11+**
- No API keys needed for forecast data — all sources are keyless Open-Meteo
  endpoints. (Keys are only needed later for the optional Telegram/WhatsApp
  notification channels.)

### Install

```bash
git clone git@github.com:lasiouce/klima-surf-cli.git
cd klima-surf-cli

# Create and activate a virtualenv
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Editable install, including dev tooling
pip install -e ".[dev]"
```

### Configure

Forecast data needs no keys. A `.env` is only required for the optional
notification channels (a later phase):

```bash
cp .env.example .env
```

```dotenv
# Optional notification channels (used in a later phase)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_RECIPIENT=
```

### Run

```bash
python main.py                 # forecast for all configured spots
python main.py --spot la_barre # a single spot by id
```

Spot ids are defined in `config/spots.json` (`la_barre`, `grande_plage`,
`cote_des_basques`, `hossegor_graviere`).

---

## Development

This project is built **test-first**. The toolchain:

```bash
# Run the test suite
pytest

# With coverage (target ≥ 80%, core/ close to 100%)
pytest --cov

# Static type checking
mypy .

# Lint + import sorting
ruff check .

# Format
black .
```

### Conventions

- **TDD** — write the failing test before the implementation; never hit live
  APIs in tests (mock with `respx`).
- **Typing** — full type hints; `mypy --strict` must pass.
- **No magic numbers** — scoring thresholds / weights live in named constants or
  config, not inline literals.
- **Timestamps** — stored in **UTC**, displayed in **Europe/Paris**.
- **Conventional Commits** (`feat:`, `fix:`, `test:`, `refactor:`…).
- **Resilience** — every API call is wrapped; the app must never crash on an API
  failure.

### Adding a spot

Append an entry to `config/spots.json` — no code change needed:

```json
{
  "id": "my_spot",
  "name": "My Spot",
  "lat": 43.5,
  "lon": -1.56,
  "optimal_swell_direction_deg": 285,
  "swell_window_deg": 45,
  "optimal_tide": "mid_rising",
  "min_height_m": 1.0,
  "max_height_m": 3.0,
  "coefficient_bonus": 70,
  "offshore_direction_deg": 100
}
```

---

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | API clients + domain models + config loader + daylight timeline + CLI output | ✅ Done |
| 2 | Session score (`core/score.py`) + scored window finder (`core/window.py`) | ⏳ Planned |
| 3 | Multi-spot config profiles (scoring-driven) | ⏳ Planned |
| 4 | Notifications: Telegram bot + WhatsApp Cloud API | ⏳ Planned |
| 5 | Response caching + scheduling (cron / APScheduler) | ⏳ Planned |

### Scoring model (Phase 2 preview)

```
score = swell_score · 0.45 + wind_score · 0.35 + tide_score · 0.20
```

| Score | Label |
|-------|-------|
| 0–2   | FLAT  |
| 2–4   | POOR  |
| 4–6   | FAIR  |
| 6–8   | GOOD  |
| 8–10  | EPIC  |

See `CLAUDE.md` for the full scoring rules and project conventions.
