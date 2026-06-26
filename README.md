# 🏆 LoL Stats

League of Legends match history tracker & live game strategy overlay.

**Two components, one app:**
- 📊 **Web Dashboard** — browse match history, view personalized improvement analysis, edit champion strategy notes
- 👻 **Live Game Overlay** — transparent overlay that shows your personal strategy notes against enemy champions during a live game

---

## Setup

### 1. Install Requirements

```bash
pip install -r requirements.txt
```

### 2. Configure Riot API Key

You need a free Riot Games API key from [developer.riotgames.com](https://developer.riotgames.com).

Set it via environment variable:
```powershell
# PowerShell
$env:RIOT_API_KEY = "RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

Or save it in `backend/data/config.json`:
```json
{
  "riot_api_key": "RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

### 3. Run

```bash
# Launch both backend + overlay
python scripts/run.py

# Or individually:
python scripts/run.py --backend   # Web dashboard only
python scripts/run.py --overlay   # Overlay only
```

### 4. Open Web Dashboard

Navigate to **http://localhost:8000** in your browser.

---

## Features

### Match History
- Search any summoner by Riot ID (GameName#TAG)
- View full match history with KDA, CS, vision, items
- Refresh to pull new matches from Riot API

### Match Analysis
- **CS Analysis** — farming efficiency vs role benchmarks
- **Kill Participation** — impact in team fights
- **Vision Analysis** — ward coverage and control ward usage
- **Death Analysis** — avoidable vs unavoidable deaths
- **Itemization** — build appropriateness
- **Overall Grade** — S/A/B/C/D with focus areas for improvement

### Strategy Editor
- Write personal strategy notes for each champion matchup
- Import from Excel (Coach K guide)
- Tips automatically appear in the overlay during live games
- Priority system: mark champions as high/normal/low priority

### Live Game Overlay
- Auto-detects game phase (champ select → loading → in-game → ended)
- Shows your strategy notes during loading screen
- Click-through (never interferes with gameplay)
- All settings configurable from the web dashboard

---

## How It Works

```
┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│  Overlay     │     │  Dashboard   │     │  Riot API     │
│  (PySide6)   │     │  (Browser)   │     │  (HTTP)       │
└──────┬───────┘     └──────┬───────┘     └───────┬───────┘
       │ reads              │ serves + writes     │ fetches
       ▼                    ▼                     ▼
┌──────────────────────────────────────────────────────────┐
│              DATA LAYER                                   │
│  • shared/strategy.json (your champion notes)            │
│  • backend/data/matches.db (SQLite match history)        │
└──────────────────────────────────────────────────────────┘
```

- **Overlay reads `strategy.json` directly** — no server dependency
- **Web dashboard edits `strategy.json`** — same file, live updates
- **Riot API** provides match data (stores in SQLite)
- **Live Client API** (`localhost:2999`) detects live game state

---

## File Structure

```
LoL_stats/
├── backend/          # FastAPI server
│   ├── main.py       # App entry point
│   ├── routers/      # REST API endpoints
│   ├── services/     # Business logic
│   └── data/         # SQLite database
├── frontend/         # Web dashboard (HTML/CSS/JS)
├── overlay/          # PySide6 transparent overlay
├── shared/           # strategy.json (shared between dashboard + overlay)
├── scripts/run.py    # Launcher
└── requirements.txt
```

---

## Requirements

- Python 3.11+
- Windows 10/11 (overlay uses Win32 APIs)
- League of Legends (in **borderless** mode for overlay)
- Riot Games API key (free, from developer.riotgames.com)

---

## Troubleshooting

| Issue | Solution |
|---|---|
| "No Riot API key configured" | Set `RIOT_API_KEY` env var or update `backend/data/config.json` |
| Overlay doesn't appear | Make sure League is running in borderless mode (Settings → Video → Window Mode → Borderless) |
| Overlay not showing during game | The Live Client API may not be enabled. Check League settings. |
| "Failed to import Excel" | Excel file must be named `Support full Season 16 Guide1 - Coach K.xlsx` and placed in project root |
| Backend won't start | Check if port 8000 is already in use |

---

## Privacy

All data is stored locally. Nothing is sent to external servers except:
- Riot Games API (to fetch match data — using your personal API key)
- DataDragon (to get champion names — no key required)

Your strategy notes and match history never leave your computer.
