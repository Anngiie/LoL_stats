"""
LoL Stats - Game Phase Detector
=================================
Maps Live Client API responses to game phases.

Game phases:
  NO_GAME        — Live Client API not reachable (not in a game)
  CHAMP_SELECT   — Connected, but no active game data yet
  LOADING_SCREEN — Connected, gameTime < 0 (loading screen)
  IN_GAME        — Connected, gameTime >= 0 (gameplay in progress)
  GAME_ENDED     — Was in-game, now disconnected

Overlay behavior per phase:
  NO_GAME:        Hidden
  CHAMP_SELECT:   Show champion matchups
  LOADING_SCREEN: Auto-show full enemy team strategy notes
  IN_GAME:        Auto-hide after configured duration
  GAME_ENDED:     Hidden
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
    """
    Tracks game phase based on Live Client API polling results.
    Maintains state to detect transitions (e.g., IN_GAME → GAME_ENDED
    when the API becomes unreachable after a game was active).
    """

    def __init__(self) -> None:
        self._current_phase = GamePhase.NO_GAME
        self._previous_phase = GamePhase.NO_GAME
        self._was_in_game = False

    @property
    def current(self) -> GamePhase:
        return self._current_phase

    @property
    def just_entered(self) -> GamePhase | None:
        """Return the new phase if it just changed, otherwise None."""
        if self._current_phase != self._previous_phase:
            return self._current_phase
        return None

    def update(self, all_game_data: dict | None) -> GamePhase:
        """
        Determine the current game phase from Live Client API data.

        Args:
            all_game_data: Parsed JSON from GET /liveclientdata/allgamedata,
                           or None if the API is unreachable.

        Returns:
            The current GamePhase.
        """
        self._previous_phase = self._current_phase

        if all_game_data is None:
            # API unreachable
            if self._was_in_game:
                self._current_phase = GamePhase.GAME_ENDED
                self._was_in_game = False
            else:
                self._current_phase = GamePhase.NO_GAME
            self._log_transition()
            return self._current_phase

        # API reachable — extract game data
        game_stats = all_game_data.get("gameData", {})
        game_time = game_stats.get("gameTime", 0)

        # gameTime < 0 = loading screen
        # gameTime >= 0 = in game
        # gameTime = 0 and no active player = champ select

        active_player = all_game_data.get("activePlayer", {})
        if not active_player or not active_player.get("championName"):
            # No active player — likely in champ select
            self._current_phase = GamePhase.CHAMP_SELECT
            self._was_in_game = False
        elif game_time < 0:
            self._current_phase = GamePhase.LOADING_SCREEN
            self._was_in_game = False
        elif game_time >= 0:
            self._current_phase = GamePhase.IN_GAME
            self._was_in_game = True
        else:
            self._current_phase = GamePhase.CHAMP_SELECT
            self._was_in_game = False

        self._log_transition()
        return self._current_phase

    def _log_transition(self) -> None:
        if self._current_phase != self._previous_phase:
            logger.info(
                "Game phase: %s → %s",
                self._previous_phase.name,
                self._current_phase.name,
            )
