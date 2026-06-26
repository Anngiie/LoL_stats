"""
LoL Stats - Backend Configuration
==================================
Dataclass-based configuration with JSON persistence.

Stores: Riot API key, database path, rate limits, server settings.
Config lives in backend/data/config.json.
"""

import json
import logging
from dataclasses import dataclass, asdict, fields
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
CONFIG_FILE = DATA_DIR / "config.json"
PROJECT_ROOT = Path(__file__).parent.parent


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


def load_config() -> BackendConfig:
    """Load config from disk, falling back to defaults for missing/invalid fields."""
    config = BackendConfig()

    # Check for API key in environment variable first (highest priority)
    import os

    env_key = os.environ.get("RIOT_API_KEY", "")
    if env_key:
        config.riot_api_key = env_key
        logger.info("Loaded RIOT_API_KEY from environment variable.")

    # Overlay with config file values
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text())
            valid_keys = {f.name for f in fields(BackendConfig)}
            for key, value in data.items():
                if key in valid_keys and key != "database_path" and key != "strategy_file":
                    setattr(config, key, value)
            logger.info("Loaded config from %s", CONFIG_FILE)
    except Exception:
        logger.debug("Could not load config from disk, using defaults.", exc_info=True)

    # __post_init__ runs after __init__, but since we constructed without
    # calling __post_init__ properly on the modified object, call it again
    config.__post_init__()

    if not config.riot_api_key:
        logger.warning(
            "No Riot API key configured. Set it via RIOT_API_KEY env var "
            "or in %s. The app will start but cannot fetch match data.",
            CONFIG_FILE,
        )

    return config
