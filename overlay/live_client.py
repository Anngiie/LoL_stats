"""
LoL Stats - Live Client API Poller
====================================
Background thread that polls the League of Legends Live Client Data API
(https://127.0.0.1:2999) for live game state.

The LCU API is a local HTTPS server that the LoL client runs.
It uses a self-signed certificate, so we disable SSL verification.

Key endpoints:
  GET /liveclientdata/allgamedata        — Full game state
  GET /liveclientdata/gamestats          — Game time, mode, map
  GET /liveclientdata/playerlist         — All players with champions

Communication with the overlay happens via Qt Signals.
"""

import logging
import threading
import time
from typing import Optional

import requests
import urllib3

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

# Suppress SSL warnings (self-signed cert on localhost)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class LiveClientPoller(QObject):
    """
    Polls the Live Client Data API on a background thread.
    Emits Qt signals when game state changes.
    """

    # Signals (thread-safe — connect from the Qt main thread)
    game_data_updated = Signal(dict)    # Full allgamedata payload
    phase_changed = Signal(str, dict)   # (phase_name, parsed_data)
    error_occurred = Signal(str)        # Error message

    def __init__(self, base_url: str = "https://127.0.0.1:2999", interval: float = 2.0) -> None:
        super().__init__()
        self._base_url = base_url.rstrip("/")
        self._interval = interval
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._session = requests.Session()
        self._session.verify = False  # Self-signed cert on localhost

    def start(self) -> None:
        """Start polling in a background daemon thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("LiveClientPoller is already running.")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="live-client-poller",
            daemon=True,
        )
        self._thread.start()
        logger.info("LiveClientPoller started (interval: %.1fs)", self._interval)

    def stop(self) -> None:
        """Stop the polling thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        logger.info("LiveClientPoller stopped.")

    # ── Polling loop (runs in background thread) ───────────

    def _poll_loop(self) -> None:
        """Main polling loop."""
        was_connected = False

        while self._running:
            try:
                data = self._fetch_all_game_data()
                if data is not None:
                    was_connected = True
                    self.game_data_updated.emit(data)
                else:
                    if was_connected:
                        # Lost connection — game probably ended
                        self.game_data_updated.emit({"disconnected": True})
                        was_connected = False
            except Exception as e:
                logger.debug("Poll error: %s", e)
                if was_connected:
                    self.game_data_updated.emit({"disconnected": True, "error": str(e)})
                    was_connected = False

            time.sleep(self._interval)

    def _fetch_all_game_data(self) -> Optional[dict]:
        """
        Fetch the full game data from the Live Client API.
        Returns None if the API is unreachable (not in a game).

        The endpoint returns:
        {
            "activePlayer": { "championName": "Thresh", "summonerSpells": [...], "runes": {...} },
            "allPlayers": [ { "championName": "...", "team": "ORDER"/"CHAOS", "summonerName": "..." } ],
            "events": { "Events": [...] },
            "gameData": { "gameTime": 123.45, "gameMode": "CLASSIC", "mapName": "Summoner's Rift" }
        }
        """
        try:
            resp = self._session.get(
                f"{self._base_url}/liveclientdata/allgamedata",
                timeout=3,
            )
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                return None  # Not in a game
            else:
                logger.debug("Live Client API returned status %d", resp.status_code)
                return None
        except requests.exceptions.ConnectionError:
            # LCU is not running — not in a game
            return None
        except requests.exceptions.Timeout:
            logger.debug("Live Client API timed out.")
            return None
        except Exception as e:
            logger.debug("Live Client API error: %s", e)
            return None

    def get_enemy_champions(self, all_game_data: dict) -> list[str]:
        """
        Extract enemy champion names from the allgamedata payload.

        The active player's team is determined by their summoner name
        matching one of the allPlayers entries. Enemies are all players
        on the opposite team.
        """
        active_player = all_game_data.get("activePlayer", {})
        all_players = all_game_data.get("allPlayers", [])

        if not active_player or not all_players:
            return []

        # Find the active player's team
        active_name = active_player.get("summonerName", "")
        active_team = None
        for p in all_players:
            if p.get("summonerName") == active_name:
                active_team = p.get("team")
                break

        if active_team is None:
            # Fallback: if active player name doesn't match (API quirk),
            # just use the active champion name for team lookup
            active_champ = active_player.get("championName", "")
            for p in all_players:
                if p.get("championName") == active_champ:
                    active_team = p.get("team")
                    break

        if active_team is None:
            return []

        # Collect enemy champions
        enemies = []
        for p in all_players:
            if p.get("team") != active_team and not p.get("isBot", False):
                champ = p.get("championName", "")
                if champ:
                    enemies.append(champ)

        return enemies

    def get_active_champion(self, all_game_data: dict) -> str:
        """Get the active player's champion name."""
        active = all_game_data.get("activePlayer", {})
        return active.get("championName", "")
