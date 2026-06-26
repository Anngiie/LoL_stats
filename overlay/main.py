"""
LoL Stats - Overlay Entry Point
=================================
Launches the PySide6 transparent overlay window and the
Live Client API polling thread.

Reuses the Phantom Lyrics pattern:
  - QApplication + overlay + background thread orchestration
  - SIGINT handling via QTimer

Usage:
    python -m overlay.main
"""

import logging
import signal
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from overlay.league_overlay import LeagueOverlay
from overlay.live_client import LiveClientPoller
from overlay.game_phase_detector import GamePhaseDetector, GamePhase

logger = logging.getLogger("lol_overlay")


class LeagueOverlayApp:
    """Orchestrates the overlay window and live client polling."""

    def __init__(self) -> None:
        self._qt_app = QApplication(sys.argv)
        self._qt_app.setApplicationName("LoL Stats Overlay")
        self._qt_app.setQuitOnLastWindowClosed(False)

        # Strategy file path (shared with backend)
        strategy_file = Path(__file__).parent.parent / "shared" / "strategy.json"

        self._overlay = LeagueOverlay(str(strategy_file))
        self._phase_detector = GamePhaseDetector()
        self._poller = LiveClientPoller(interval=2.0)

        # Connect poller signals to overlay
        self._poller.game_data_updated.connect(self._on_game_data)

        # Track previous enemy team to detect changes
        self._last_enemy_champs: list[str] = []

    def run(self) -> int:
        """Start everything and enter the Qt event loop."""
        logger.info("=" * 50)
        logger.info("  LoL Stats — Live Game Overlay")
        logger.info("=" * 50)

        # Show overlay (it starts hidden, will fade in when a game is detected)
        self._overlay.show()

        # Start polling the Live Client API
        self._poller.start()

        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self._handle_sigint)
        self._sig_timer = QTimer()
        self._sig_timer.timeout.connect(lambda: None)
        self._sig_timer.start(200)

        # Enter Qt event loop
        exit_code = self._qt_app.exec()

        # Cleanup
        self._shutdown()
        return exit_code

    def _shutdown(self) -> None:
        """Gracefully stop background services."""
        logger.info("Shutting down overlay...")
        self._poller.stop()
        logger.info("Overlay exited cleanly.")

    def _handle_sigint(self, signum, frame) -> None:
        """Handle Ctrl+C."""
        logger.info("Ctrl+C received, quitting...")
        self._qt_app.quit()

    # ─── Event Handlers ─────────────────────────────────────

    def _on_game_data(self, all_game_data: dict) -> None:
        """
        Called from the LiveClientPoller thread when game data updates.

        Determines the game phase, extracts enemy champions, and
        forwards everything to the overlay for rendering.
        """
        # Handle disconnect signal
        if all_game_data.get("disconnected"):
            all_game_data = None

        # Determine game phase
        phase = self._phase_detector.update(all_game_data)

        if all_game_data is None:
            # No game running
            enemy_champs = []
            active_champ = ""
        else:
            enemy_champs = self._poller.get_enemy_champions(all_game_data)
            active_champ = self._poller.get_active_champion(all_game_data)

        # Only log when enemy team changes
        if enemy_champs != self._last_enemy_champs:
            if enemy_champs:
                logger.info(
                    "Enemy team: %s (phase: %s)",
                    ", ".join(enemy_champs),
                    phase.name,
                )
            self._last_enemy_champs = enemy_champs

        # Forward to overlay (thread-safe via Qt Signal)
        self._overlay.on_game_data(
            all_game_data or {},
            phase.name,
            enemy_champs,
            active_champ,
        )


def main() -> int:
    """Application entry point."""
    app = LeagueOverlayApp()
    return app.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    sys.exit(main())
