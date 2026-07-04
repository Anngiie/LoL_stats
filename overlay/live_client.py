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
        self._poll_count = 0
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
                self._poll_count += 1

                if data is not None:
                    if not was_connected:
                        logger.info("Connected to Live Client API (game detected)")
                    was_connected = True
                    self.game_data_updated.emit(data)
                else:
                    if was_connected:
                        logger.info("Live Client API disconnected — game likely ended")
                        self.game_data_updated.emit({"disconnected": True})
                        was_connected = False
                    elif self._poll_count <= 3:
                        logger.debug("Live Client API not reachable (poll #%d) — no game running", self._poll_count)
            except Exception as e:
                logger.debug("Poll error: %s", e)
                if was_connected:
                    self.game_data_updated.emit({"disconnected": True, "error": str(e)})
                    was_connected = False

            time.sleep(self._interval)

    _data_logged: bool = False  # Only log raw API structure once

    def _fetch_all_game_data(self) -> Optional[dict]:
        """
        Fetch the full game data from the Live Client API.
        Returns None if the API is unreachable (not in a game).
        """
        try:
            resp = self._session.get(
                f"{self._base_url}/liveclientdata/allgamedata",
                timeout=3,
            )
            if resp.status_code == 200:
                data = resp.json()
                # Log the actual API response structure once for debugging
                if not self._data_logged:
                    gd = data.get("gameData", {})
                    ap = data.get("activePlayer", {})
                    pl = data.get("allPlayers", [])
                    logger.info(
                        "Live Client API response structure:\n"
                        "  gameData keys: %s\n"
                        "  gameTime: %s\n"
                        "  activePlayer keys: %s\n"
                        "  activePlayer.championName: %r\n"
                        "  allPlayers count: %d\n"
                        "  allPlayers[0] keys: %s\n"
                        "  allPlayers positions: %s",
                        list(gd.keys()) if gd else [],
                        gd.get("gameTime", "MISSING"),
                        list(ap.keys())[:8] if ap else [],
                        ap.get("championName", "MISSING") if ap else "MISSING",
                        len(pl),
                        list(pl[0].keys())[:10] if pl else [],
                        [(p.get("championName", "?"), p.get("position", "?"), p.get("team", "?")) for p in pl],
                    )
                    # Log full summonerSpells structure for each player
                    logger.info("=== SUMMONER SPELLS DEBUG ===")
                    for player in pl:
                        champ = player.get("championName", "?")
                        spells = player.get("summonerSpells", {})
                        logger.info("Player: %s", champ)
                        logger.info("  summonerSpells keys: %s", list(spells.keys()) if spells else "NONE")
                        if spells:
                            for spell_key, spell_data in spells.items():
                                logger.info("  %s:", spell_key)
                                logger.info("    keys: %s", list(spell_data.keys()) if isinstance(spell_data, dict) else "NOT A DICT")
                                logger.info("    full data: %s", spell_data)
                    logger.info("=== END SUMMONER SPELLS DEBUG ===")
                    self._data_logged = True
                return data
            elif resp.status_code == 404:
                return None
            else:
                logger.debug("Live Client API returned status %d", resp.status_code)
                return None
        except requests.exceptions.ConnectionError:
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

        # Find the active player's team using riotId (summonerName is no longer
        # available on activePlayer in recent LoL patches)
        active_riot_id = active_player.get("riotIdGameName", "") or active_player.get("summonerName", "")
        active_team = None
        active_champ_name = ""

        for p in all_players:
            p_name = p.get("riotIdGameName", "") or p.get("summonerName", "")
            if p_name == active_riot_id and active_riot_id:
                active_team = p.get("team")
                active_champ_name = p.get("championName", "")
                break

        # Fallback: match by champion name if riotId doesn't work
        if active_team is None:
            for p in all_players:
                if p.get("championName") == active_player.get("championName", ""):
                    active_team = p.get("team")
                    active_champ_name = p.get("championName", "")
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
        """Get the active player's champion name by matching riotId against allPlayers."""
        active = all_game_data.get("activePlayer", {})
        all_players = all_game_data.get("allPlayers", [])

        # Try riotId matching first
        riot_name = active.get("riotIdGameName", "") or active.get("summonerName", "")
        if riot_name:
            for p in all_players:
                p_name = p.get("riotIdGameName", "") or p.get("summonerName", "")
                if p_name == riot_name:
                    return p.get("championName", "")

        # Fallback: direct championName on activePlayer (older API versions)
        return active.get("championName", "")

    def get_team_composition(self, all_game_data: dict) -> dict:
        """
        Extract team roles from the Live Client API.

        Uses the 'role' field when available (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY),
        with Smite-detection fallback for the jungler.

        Returns:
            {
                "enemy_support": str,   # enemy UTILITY champion
                "allied_adc": str,      # your team's BOTTOM champion
                "allied_jungler": str,  # your team's JUNGLE champion
                "all_enemies": list[str],
            }
        """
        empty = {"enemy_support": "", "allied_adc": "", "allied_jungler": "", "all_enemies": []}
        active_player = all_game_data.get("activePlayer", {})
        all_players = all_game_data.get("allPlayers", [])
        if not active_player or not all_players:
            return empty

        # Determine active player's team
        active_riot_id = active_player.get("riotIdGameName", "") or active_player.get("summonerName", "")
        active_team = None
        active_champ = ""
        for p in all_players:
            p_name = p.get("riotIdGameName", "") or p.get("summonerName", "")
            if p_name == active_riot_id and active_riot_id:
                active_team = p.get("team")
                active_champ = p.get("championName", "")
                break
        # Fallback: match by champion name
        if active_team is None:
            for p in all_players:
                if p.get("championName") == active_player.get("championName", ""):
                    active_team = p.get("team")
                    active_champ = p.get("championName", "")
                    break
        if active_team is None:
            return empty

        enemy_support = ""
        allied_adc = ""
        allied_jungler = ""
        all_enemies = []

        for p in all_players:
            team = p.get("team")
            champ = p.get("championName", "")
            # Live Client API uses 'position', older docs say 'role'
            pos = p.get("position", "") or p.get("role", "")
            if not champ:
                continue

            if team == active_team:
                if pos == "JUNGLE":
                    allied_jungler = champ
                elif pos == "BOTTOM" and champ != active_champ:
                    allied_adc = champ
            else:
                if not p.get("isBot", False):
                    all_enemies.append(champ)
                if pos == "UTILITY":
                    enemy_support = champ

        # Fallback: Smite detection for jungler if role wasn't available
        if not allied_jungler:
            for p in all_players:
                if p.get("team") != active_team:
                    continue
                spells = p.get("summonerSpells", {})
                if not isinstance(spells, dict):
                    continue
                for spell_key in ("summonerSpellOne", "summonerSpellTwo"):
                    spell = spells.get(spell_key, {})
                    spell_name = spell.get("displayName", "") or spell.get("spellKey", "")
                    if "Smite" in spell_name:
                        allied_jungler = p.get("championName", "")
                        break
                if allied_jungler:
                    break

        # Fallback: if no enemy support identified via role, keep all_enemies
        # so the overlay can still show tips for the full enemy team.
        return {
            "enemy_support": enemy_support,
            "allied_adc": allied_adc,
            "allied_jungler": allied_jungler,
            "all_enemies": all_enemies,
        }
