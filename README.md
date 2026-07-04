# LoL Stats — Personal Match Analytics & Live Overlay

A League of Legends personal statistics dashboard with a live in-game overlay. Built for players who want deep match analysis and real-time tactical insights without leaving the game.

---

## Features

### 📊 Web Dashboard
- **Home / Command Overview** — Profile card, match history, quick stats (win rate, KDA, CS, vision)
- **Match Details** — Full breakdown: KDA, CS/min, gold/min, vision, damage, grade, tactical assessment
- **Tactical Assessment** — AI-generated analysis per match with priority improvements highlighted
- **Analytics** — Performance trends over last 20 games (KDA, vision/min, CS/min, gold/min, damage/min), recent form (W/L), champion pool win rates, rank comparison (Iron → Master)
- **Strategy Editor** — Three-context notes per champion (vs enemy support / with your ADC / with your jungler), imported from Coach K's Excel guide, fully editable
- **Settings** — Summoner identity, overlay preferences (always-visible, opacity, font, position), backend status

### 🎮 Live In-Game Overlay
Three transparent panels that appear automatically during games:

| Panel | Position | Content |
|-------|----------|---------|
| **VS Enemy Support** | Top-left | How to play vs the enemy support, counters, strengths/weaknesses |
| **With Your ADC** | Bottom-left | Lane gameplan, trading patterns, roam timing |
| **With Your Jungler** | Top-right | Jungle synergy, gank setup, vision control |

**Design:** Dark semi-transparent panels with gold corner brackets, HUD grid pattern, monospace typography (Martian Mono for titles, JetBrains Mono for body). Panels stay visible during the game and auto-hide when no game is running.

---

## Quick Start

### Prerequisites
- Windows 10/11
- League of Legends installed
- Riot Games API key (see below)

### 1. Get Your Riot API Key
1. Go to **[Riot Developer Portal](https://developer.riotgames.com/)**
2. Log in with your League of Legends account
3. Click **"Regenerate API Key"** (Personal API Key)
4. Copy the key (starts with `RGAPI-`)

> ⚠️ **Note:** Development keys expire every 24 hours. For production use, apply for a production key on the developer portal.

### 2. Configure Your API Key
Create `backend/data/config.json` (or edit if it exists):
```json
{
  "riot_api_key": "RGAPI-YOUR-KEY-HERE",
  "match_history_count": 20,
  "match_history_days": 90,
  "rate_limit_per_second": 19,
  "rate_limit_per_2min": 95,
  "host": "127.0.0.1",
  "port": 8000
}
```

Or set the `RIOT_API_KEY` environment variable instead.

### 3. Run the App

**Option A: Run from source (Python 3.12+)**
```bash
# Terminal 1 — Backend
pip install -r backend/requirements.txt
python scripts/run.py --backend

# Terminal 2 — Frontend (served by backend)
# Open http://localhost:8000 in browser
```

**Option B: Use the pre-built EXE (Windows)**
1. Download `lol_stats.exe` from Releases
2. Place `backend/data/config.json` next to the EXE with your API key
3. Run `lol_stats.exe` — launches backend + overlay automatically

---

## How It Works

### Backend (FastAPI)
- Polls Riot API for match history and live game data
- Stores matches in SQLite with computed stats (KDA, CS/min, vision, gold/min, etc.)
- Runs tactical analysis on each match (CS efficiency, vision, KDA, deaths, itemization)
- Serves frontend + REST API on `http://localhost:8000`

### Frontend (Vanilla JS, no build step)
- Single-page app with hash routing (`#/home`, `#/strategy`, `#/settings`)
- Chart.js for analytics charts
- Auto-refreshes match data via API

### Overlay (PySide6 / Qt)
- Three frameless, click-through, always-on-top windows
- Reads `shared/strategy.json` written by backend
- Positions: top-left (vs support), bottom-left (with ADC), top-right (with jungler)
- Auto-shows during loading screen / in-game; hides when no game detected
- Reads `shared/strategy.json` for champion-specific notes per context

### Data Flow
```
Riot API → Backend (FastAPI) → SQLite + JSON strategy file
                                    ↓
                         Frontend (Dashboard) + Overlay (Qt)
```

---

## Project Structure
```
LoL_stats/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Config loading (config.json + env vars)
│   ├── database.py          # SQLite schema & queries
│   ├── routers/             # API endpoints
│   │   ├── summoner.py      # Summoner lookup
│   │   ├── matches.py       # Match history & details
│   │   ├── analysis.py      # Match analysis & trends
│   │   ├── strategy.py      # Strategy notes CRUD + global prefs
│   │   └── analytics.py     # Aggregated stats & trends
│   ├── services/
│   │   ├── riot_client.py   # Riot API wrapper with rate limiting
│   │   ├── match_analyzer.py# Tactical analysis per match
│   │   └── strategy_manager.py
│   └── data/                # config.json, matches.db, strategy.json (gitignored)
├── frontend/
│   ├── index.html           # Shell + font imports
│   ├── css/style.css        # Tactical Design System (CSS variables)
│   ├── js/
│
│
│       ├── app.js           # Router, state, toast notifications
│       ├── api.js           # API client
│       └── pages│
│           ├── home.js      # Home + match detail + analytics
│           ├── strategy.js  # Strategy editor (3 contexts)
│           └── settings.js  # Identity, overlay prefs, backend status
│   └── fonts/               # Bundled fonts (Martian Mono, JetBrains Mono)
├── overlay/
│   ├── main.py              # Launcher: starts 3 overlay windows
│   ├── league_overlay.py    # Single-panel widget (3 instances)
│   ├── live_client.py       # Polls Riot Live Client Data API (port 2999)
│   ├── strategy_reader.py   # Reads shared/strategy.json
│   └── game_phase_detector.py
├── shared/
│   └── strategy.json        # Champion strategy notes (gitignored)
├── scripts/
│   ├── run.py               # Launcher (backend / overlay / both)
│   └── build_exe.py         # PyInstaller build script
└── build_exe.py             # Legacy build script
```

---

## Development

```bash
# Install deps
pip install -r backend/requirements.txt

# Run backend
python scripts/run.py --backend

# Run overlay (separate terminal)
python scripts/run.py --overlay

# Or both
python scripts/run.py --both
```

### Build EXE
```bash
pip install pyinstaller
python build_exe.py
# Output: dist/lol_stats.exe (~55 MB)
```

---

## Configuration Reference

### `backend/data/config.json`
| Key | Description | Default |
|-----|-------------|---------|
| `riot_api_key` | **Required** - Your Riot Developer API key | — |
| `match_history_count` | Matches to fetch per refresh | `20` |
| `match_history_days` | How far back to fetch | `90` |
| `rate_limit_per_second` | Riot dev key limit | `19` |
| `rate_limit_per_2min` | Riot dev key limit | `95` |
| `host` / `port` | Backend bind address | `127.0.0.1:8000` |

### Overlay Preferences (via Settings page)
| Setting | Description |
|---------|-------------|
| `overlay_always_visible` | Stay visible entire game (no auto-fade) |
| `overlay_show_duration_seconds` | Fade delay when not always visible |
| `overlay_opacity` | Panel transparency (0.1–1.0) |
| `overlay_font_family` | Font for tip text (JetBrains Mono, Martian Mono, etc.) |
| `overlay_font_size` | Base font size (pt) |
| `overlay_width` | Panel width in pixels |
| `overlay_x` / `overlay_y` | Screen position offset |

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Backend 404 on summoner lookup | API key expired — regenerate at developer.riotgames.com |
| Overlay not appearing | Ensure game is running; check Live Client API at `https://127.0.0.1:2999` |
| "Font not found" in overlay | Run EXE (fonts bundled) or install JetBrains Mono / Martian Mono |
| Settings not saving | Check backend logs; ensure `config.json` writable |
| Overlay not showing in game | Check Settings → "Always visible during game" toggle |

---

## Security Notes

- **Never commit** `backend/data/config.json` (contains API key) — it's gitignored
- `shared/strategy.json`, `backend/data/matches.db`, and `logs/` are gitignored
- The EXE bundles fonts and strategy JSON — no external dependencies at runtime
- No telemetry, no external connections except Riot APIs and Live Client API

---

## Roadmap / Future Features

- **Item Recommendations in Overlay** — Show recommended build paths directly in the overlay based on the champion you're playing and the enemy team composition
- **Expanded Champion Database** — Add more champions to the strategy database with matchup-specific notes, power spikes, and laning tips
- **Summoner Spell Tracker** — Track enemy summoner spell cooldowns (Flash, Ignite, Heal, etc.) with visual countdown timers on the overlay
- **Item Build Import** — Import recommended item builds from popular sources and display them contextually during champion select or loading screen
- **Win Condition Detection** — Automatically identify your team's win conditions (scaling, early game, skirmish, split-push) based on team compositions
- **Overlay Customization** — More control over panel positioning, sizing, and which panels to show/hide
- **Match Timeline** — Visual timeline of key events (kills, objectives, gold leads) per match
- **Multi-Role Support** — Currently tuned for support mains; expand strategy data and benchmarks for all roles
- **Live Stats Overlay** — Real-time CS, gold, and KDA comparison between you and your lane opponent during the game

---

## License

MIT License — free for personal use.

---

## Credits

- Riot Games for the League of Legends API
- [Chart.js](https://www.chartjs.org/) for analytics charts
- [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) & [Martian Mono](https://github.com/evilmartians/mono) fonts
- [PySide6](https://www.qt.io/qt-for-python) for the overlay
- [FastAPI](https://fastapi.tiangolo.com/) + [Chart.js](https://www.chartjs.org/)

---

*Not affiliated with Riot Games. This is a community project for personal use.*