"""
LoL Stats - Backend Configuration
==================================
Dataclass-based configuration with JSON persistence.

Stores: Riot API key, database path, rate limits, server settings.
Config lives in backend/data/config.json.
"""

import json
import logging
import os
import sys
from dataclasses import dataclass, asdict, fields
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_data_dir() -> Path:
    """Return the persistent data directory.

    When running as a frozen PyInstaller EXE, stored under
    %APPDATA%/LoLStats so that data survives EXE restarts.
    Otherwise, the default backend/data/ folder.
    """
    if getattr(sys, 'frozen', False):
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "LoLStats"
    return Path(__file__).parent / "data"


def _get_project_root() -> Path:
    """Return the project root.

    In frozen mode this is sys._MEIPASS (the temp extraction dir).
    """
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent


DATA_DIR = _get_data_dir()
CONFIG_FILE = DATA_DIR / "config.json"
PROJECT_ROOT = _get_project_root()


@dataclass
class BackendConfig:
    """All backend settings with sensible defaults."""

    # ── Riot API ──
    riot_api_key: str = ""  # Set via config.json or env var RIOT_API_KEY

    # ── Paths ──
    database_path: str = ""  # Auto-set in __post_init__ if empty
    strategy_file: str = ""  # Auto-set in __post_init__ if empty

    # ── Match fetching ──
    match_history_count: int = 20  # How many matches to fetch per refresh
    match_history_days: int = 90  # How far back to look (days)

    # ── Rate limiting (Riot dev key: 20 req/s, 100 req/2min) ──
    rate_limit_per_second: int = 19  # Slightly under limit to be safe
    rate_limit_per_2min: int = 95

    # ── Server ──
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True

    # ── Live Client API ──
    live_client_url: str = "https://127.0.0.1:2999"

    def __post_init__(self):
        if not self.database_path:
            self.database_path = str(DATA_DIR / "matches.db")
        if not self.strategy_file:
            # When frozen, store strategy.json in the persistent AppData dir
            # so dashboard edits survive restarts. _seed_data_dir() copies the
            # bundled file there on first run.
            if getattr(sys, 'frozen', False):
                self.strategy_file = str(DATA_DIR / "strategy.json")
            else:
                self.strategy_file = str(PROJECT_ROOT / "shared" / "strategy.json")

    def save(self) -> None:
        """Write config to disk."""
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2))
            logger.info("Config saved to %s", CONFIG_FILE)
        except Exception:
            logger.exception("Failed to save config.")

    def to_frontend_dict(self) -> dict:
        """Return safe subset for the frontend (no API key)."""
        return {
            "host": self.host,
            "port": self.port,
            "match_history_count": self.match_history_count,
            "match_history_days": self.match_history_days,
        }


def _find_config_files() -> list[Path]:
    """Return all config files to check, in priority order."""
    import os
    import sys

    paths = []

    # 1. Environment variable
    env_path = os.environ.get("LOL_STATS_CONFIG", "")
    if env_path:
        paths.append(Path(env_path))

    # 2. Same folder as the EXE (for PyInstaller builds)
    if getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        paths.append(exe_dir / "config.json")

    # 3. User's app data folder
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        paths.append(Path(appdata) / "LoLStats" / "config.json")

    # 4. Default project location
    paths.append(DATA_DIR / "config.json")

    return paths


def _seed_data_dir() -> None:
    """On first frozen run, seed AppData with bundled config and strategy files."""
    if not getattr(sys, 'frozen', False):
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for rel_path in ("backend/data/config.json", "shared/strategy.json"):
        src = Path(sys._MEIPASS) / rel_path
        dst = DATA_DIR / Path(rel_path).name
        if src.exists() and not dst.exists():
            dst.write_text(src.read_text())
            logger.info("Seeded %s from bundled file.", dst)


def load_config() -> BackendConfig:
    """Load config from disk, checking multiple locations in priority order.
    Falls back to defaults for missing/invalid fields."""
    _seed_data_dir()
    import os

    config = BackendConfig()

    # Check for API key in environment variable first (highest priority)
    env_key = os.environ.get("RIOT_API_KEY", "")
    if env_key:
        config.riot_api_key = env_key
        logger.info("Loaded RIOT_API_KEY from environment variable.")

    # Try each config file location
    for config_path in _find_config_files():
        try:
            if config_path.exists():
                data = json.loads(config_path.read_text())
                valid_keys = {f.name for f in fields(BackendConfig)}
                for key, value in data.items():
                    if key not in valid_keys or key in ("database_path", "strategy_file"):
                        continue
                    # Env var wins over config.json for the API key.
                    if key == "riot_api_key" and env_key:
                        continue
                    setattr(config, key, value)
                logger.info("Loaded config from %s", config_path)
                break  # Use first found config
        except Exception:
            logger.debug("Could not load config from %s", config_path, exc_info=True)

    # __post_init__ runs after __init__, but since we constructed without
    # calling __post_init__ properly on the modified object, call it again
    config.__post_init__()

    if not config.riot_api_key:
        logger.warning(
            "No Riot API key configured. Set it via RIOT_API_KEY env var "
            "or place a config.json next to lol_stats.exe with your key."
        )

    return config
