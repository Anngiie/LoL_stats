"""
LoL Stats - Overlay Entry Point
=================================
Launches the PySide6 transparent overlay window and the
Live Client API polling thread.

Usage:
    python overlay/main.py
"""

import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtGui import QIcon, QAction

from overlay.league_overlay import LeagueOverlay
from overlay.live_client import LiveClientPoller
from overlay.game_phase_detector import GamePhaseDetector, GamePhase

# ── File Logging Setup ─────────────────────────────────────

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"overlay_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
))

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)

# Console output only when LOGGER=1 env var is set
if os.environ.get("LOGGER") == "1":
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    root_logger.addHandler(console_handler)

logger = logging.getLogger("lol_overlay")


class LeagueOverlayApp:
    """Orchestrates the overlay window and live client polling."""

    def __init__(self) -> None:
        self._qt_app = QApplication(sys.argv)
        self._qt_app.setApplicationName("LoL Stats Overlay")
        self._qt_app.setQuitOnLastWindowClosed(False)

        # Load bundled fonts so the overlay uses JetBrains Mono / Martian Mono
        self._load_fonts()

        # Strategy file path (shared with backend)
        strategy_file = Path(__file__).parent.parent / "shared" / "strategy.json"

        logger.info("Strategy file: %s", strategy_file)
        logger.info("Log file: %s", LOG_FILE)

        self._overlays = [
            LeagueOverlay(str(strategy_file), "vs_support"),
            LeagueOverlay(str(strategy_file), "with_adc"),
            LeagueOverlay(str(strategy_file), "with_jungler"),
        ]
        self._phase_detector = GamePhaseDetector()
        self._poller = LiveClientPoller(interval=2.0)

        # Connect poller signals
        self._poller.game_data_updated.connect(self._on_game_data)

        # Track previous state for change detection
        self._last_team_comp: dict | None = None
        self._poll_count: int = 0

    def _load_fonts(self) -> None:
        """Load bundled TTF fonts so Qt can use JetBrains Mono and Martian Mono."""
        from PySide6.QtGui import QFontDatabase

        if getattr(sys, 'frozen', False):
            fonts_dir = Path(sys._MEIPASS) / "frontend" / "fonts"
        else:
            fonts_dir = Path(__file__).parent.parent / "frontend" / "fonts"

        if not fonts_dir.exists():
            logger.warning("Fonts directory not found: %s", fonts_dir)
            return

        loaded = 0
        for ttf in sorted(fonts_dir.glob("*.ttf")):
            font_id = QFontDatabase.addApplicationFont(str(ttf))
            if font_id >= 0:
                families = QFontDatabase.applicationFontFamilies(font_id)
                logger.info("Loaded font: %s (%s)", ttf.name, families)
                loaded += 1
            else:
                logger.warning("Failed to load font: %s", ttf.name)
        logger.info("Loaded %d font file(s)", loaded)

    def _get_icon_path(self) -> str:
        """Find the app icon file (works in source and frozen EXE)."""
        icon_name = "LoL_stats icon (2).ico"
        if getattr(sys, 'frozen', False):
            return str(Path(sys._MEIPASS) / icon_name)
        return str(Path(__file__).parent.parent / icon_name)

    def _setup_tray(self) -> None:
        """Create a system tray icon with a Quit menu."""
        icon_path = self._get_icon_path()
        icon = QIcon(icon_path)

        if icon.isNull():
            logger.warning("Tray icon not found at %s", icon_path)
            return

        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("LoL Stats Overlay — right-click to quit")

        # Context menu
        menu = QApplication.instance().style()  # dummy to ensure style exists
        from PySide6.QtWidgets import QMenu
        tray_menu = QMenu()
        quit_action = tray_menu.addAction("Quit")
        quit_action.triggered.connect(self._qt_app.quit)
        self._tray.setContextMenu(tray_menu)

        self._tray.show()
        logger.info("System tray icon created")

    def run(self) -> int:
        """Start everything and enter the Qt event loop."""
        logger.info("=" * 50)
        logger.info("  LoL Stats — Live Game Overlay")
        logger.info("  Log: %s", LOG_FILE)
        logger.info("=" * 50)

        # Show all overlays briefly at startup so user can confirm positions
        for ov in self._overlays:
            ov.setWindowOpacity(0.8)
            ov.show()
        logger.info("3 overlay panels shown (initial opacity: 0.8)")

        # Set up system tray icon
        self._setup_tray()

        # Start polling the Live Client API
        self._poller.start()

        # Handle Ctrl+C gracefully
        signal.signal(signal.SIGINT, self._handle_sigint)
        self._sig_timer = QTimer()
        self._sig_timer.timeout.connect(lambda: None)
        self._sig_timer.start(200)

        # Auto-hide after 5 seconds if no game detected (gives user time to see it)
        QTimer.singleShot(5000, self._initial_hide_check)

        # Enter Qt event loop
        exit_code = self._qt_app.exec()

        # Cleanup
        self._shutdown()
        return exit_code

    def _initial_hide_check(self) -> None:
        """After 5 seconds, if no game is running, fade out all overlays."""
        if not self._last_team_comp:
            logger.info("No game detected after 5s — overlays will fade until a game starts.")
            for ov in self._overlays:
                ov._target_opacity = 0.0
                ov._show_until = 0.0

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
        """Called from the LiveClientPoller thread when game data updates."""
        self._poll_count += 1

        if all_game_data.get("disconnected"):
            logger.info("Live Client API disconnected — game likely ended.")
            all_game_data = None

        phase = self._phase_detector.update(all_game_data)

        if all_game_data is None:
            team_comp = {}
        else:
            team_comp = self._poller.get_team_composition(all_game_data)

            if self._poll_count % 5 == 0:
                logger.debug(
                    "Poll #%d — Phase: %s, EnemySupp: %s, AllyADC: %s, AllyJG: %s",
                    self._poll_count, phase.name,
                    team_comp.get("enemy_support", "?"),
                    team_comp.get("allied_adc", "?"),
                    team_comp.get("allied_jungler", "?"),
                )

        # Log team comp changes
        if team_comp != self._last_team_comp:
            if any(team_comp.values()):
                logger.info(
                    "Team comp: vs %s, with ADC %s, with JG %s",
                    team_comp.get("enemy_support", "?"),
                    team_comp.get("allied_adc", "?"),
                    team_comp.get("allied_jungler", "?"),
                )
            self._last_team_comp = team_comp

        # Forward to all 3 overlays (thread-safe via Qt Signals)
        for ov in self._overlays:
            ov.on_game_data(phase.name, team_comp)


def _kill_existing_instance() -> None:
    """Kill any previously running overlay instance (PID file approach)."""
    import os
    import ctypes

    pid_file = LOG_DIR / "overlay.pid"
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            try:
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x0001, False, old_pid)  # PROCESS_TERMINATE
                if handle:
                    kernel32.TerminateProcess(handle, 0)
                    kernel32.CloseHandle(handle)
                    logger.info("Terminated previous overlay instance (PID %d).", old_pid)
            except Exception:
                pass
        except Exception:
            pass
    # Write current PID
    pid_file.write_text(str(os.getpid()))


def main() -> int:
    """Application entry point."""
    _kill_existing_instance()
    app = LeagueOverlayApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
