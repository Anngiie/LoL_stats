"""
LoL Stats - Game Phase Detector
=================================
Maps Live Client API responses to game phases.

Detection strategy (in priority order):
  1. API unreachable → NO_GAME
  2. API reachable, no gameData.gameTime → CHAMP_SELECT
  3. gameTime < 0 → LOADING_SCREEN (Riot uses negative time during loading)
  4. gameTime > 0 → IN_GAME
  5. gameTime == 0 + champion data available → LOADING_SCREEN edge case
  6. gameTime == 0 + no champion data → CHAMP_SELECT
  7. Was in-game, now disconnected → GAME_ENDED
"""

import logging
from enum import Enum, auto

logger = logging.getLogger(__name__)


class GamePhase(Enum):
    NO_GAME = auto()
    CHAMP_SELECT = auto()
    LOADING_SCREEN = auto()
    IN_GAME = auto()
    GAME_ENDED = auto()


class GamePhaseDetector:
    """Tracks game phase based on Live Client API polling results."""

    def __init__(self) -> None:
        self._current_phase = GamePhase.NO_GAME
        self._previous_phase = GamePhase.NO_GAME
        self._was_in_game = False
        self._debug_logged = False  # Only log raw data once per phase

    @property
    def current(self) -> GamePhase:
        return self._current_phase

    @property
    def just_entered(self) -> GamePhase | None:
        if self._current_phase != self._previous_phase:
            return self._current_phase
        return None

    def update(self, all_game_data: dict | None) -> GamePhase:
        """
        Determine the current game phase from Live Client API data.
        """
        self._previous_phase = self._current_phase

        if all_game_data is None:
            if self._was_in_game:
                self._current_phase = GamePhase.GAME_ENDED
                self._was_in_game = False
            else:
                self._current_phase = GamePhase.NO_GAME
            self._log_transition()
            return self._current_phase

        # ── Extract data from API response ──────────────────
        game_data = all_game_data.get("gameData", {})
        game_time = game_data.get("gameTime", 0)
        active_player = all_game_data.get("activePlayer", {})
        all_players = all_game_data.get("allPlayers", [])

        active_champ = active_player.get("championName", "") if active_player else ""
        has_active_champ = bool(active_champ and active_champ.strip())
        has_players = len(all_players) > 0

        # Check if any allPlayers entry has summoner spells (only after loading screen)
        has_summoner_spells = any(
            p.get("summonerSpells") and len(p.get("summonerSpells", {})) > 0
            for p in all_players
        )

        # Determine phase
        if game_time < 0:
            # Riot sets gameTime to a negative value during loading screen
            self._current_phase = GamePhase.LOADING_SCREEN
            self._was_in_game = False
        elif game_time > 0:
            self._current_phase = GamePhase.IN_GAME
            self._was_in_game = True
        elif has_active_champ or has_summoner_spells:
            # We have champion data but gameTime is 0 — likely loading screen edge case
            self._current_phase = GamePhase.LOADING_SCREEN
            self._was_in_game = False
        elif has_players:
            # Players are present but no active champion picked yet — champ select
            self._current_phase = GamePhase.CHAMP_SELECT
            self._was_in_game = False
        else:
            # Connected but no meaningful data
            self._current_phase = GamePhase.CHAMP_SELECT
            self._was_in_game = False

        # ── Debug: log raw data once per new phase ──────────
        if self._current_phase != self._previous_phase:
            logger.info(
                "Phase change: %s -> %s (gameTime=%s, activeChamp=%r, players=%d, spells=%s)",
                self._previous_phase.name,
                self._current_phase.name,
                game_time,
                active_champ or "<none>",
                len(all_players),
                has_summoner_spells,
            )
            self._debug_logged = False

        if not self._debug_logged:
            logger.debug(
                "Raw API keys: gameData=%s, activePlayer=%s, allPlayers=%s",
                list(game_data.keys()) if game_data else [],
                list(active_player.keys())[:5] if active_player else [],
                [p.get("championName", "?") for p in all_players[:5]] if all_players else [],
            )
            self._debug_logged = True

        return self._current_phase

    def _log_transition(self) -> None:
        """Only called for disconnect states (keeps it clean)."""
        if self._current_phase != self._previous_phase:
            logger.info(
                "Game phase: %s -> %s",
                self._previous_phase.name,
                self._current_phase.name,
            )
