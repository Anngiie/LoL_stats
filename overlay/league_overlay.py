"""
LoL Stats - League Overlay Widget
===================================
A transparent, always-on-top, frameless PySide6 window that displays
personal strategy notes against enemy champions during a live League game.

Core patterns reused from Phantom Lyrics overlay.py:
  - FramelessWindowHint | WindowStaysOnTopHint | Tool
  - WA_TranslucentBackground + WA_ShowWithoutActivating
  - WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT via win32gui
  - QPainterPath outlined text for readability on any background
  - QTimer tick loop for smooth opacity auto-hide fade
  - Qt Signals for thread-safe updates from background threads
  - GRAB_FILL_COLOR for full-window hit-testing

Differences from Phantom Lyrics:
  - No drag-and-drop (overlay stays at fixed configured position)
  - Click-through always on (WS_EX_TRANSPARENT always set)
  - No sync buttons or hover states
  - Renders strategy notes instead of song lyrics
  - Auto-show/hide based on game phase detection
"""

import json
import logging
import sys
import time
from pathlib import Path

from PySide6.QtCore import (
    Qt,
    QTimer,
    QRect,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QFont,
    QColor,
    QPainter,
    QPen,
    QBrush,
    QPainterPath,
    QFontMetrics,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
)

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────

# Colors
TEXT_COLOR = QColor(255, 255, 255)      # Pure white, alpha applied
SHADOW_COLOR = QColor(0, 0, 0)          # Black outline
GRAB_FILL_COLOR = QColor(0, 0, 0, 1)    # Near-invisible fill for hit-testing

# Fade parameters
AUTO_HIDE_FADE_STEP = 0.05              # Opacity delta per tick
TICK_INTERVAL_MS = 100                  # UI update frequency

# Layout defaults
DEFAULT_WIDTH = 500
DEFAULT_X = 20
DEFAULT_Y = 60
SIDE_PADDING = 24
LINE_SPACING_PX = 4
TITLE_GAP = 16
CHAMPION_HEADER_SIZE = 13
TIP_TEXT_SIZE = 12

# Messages
NO_GAME_MESSAGE = "Waiting for game..."
LOADING_MESSAGE = "Loading screen — preparing strategy..."
NO_STRATEGY_MESSAGE = "No strategy notes for these champions. Add some in the web dashboard!"


class LeagueOverlay(QWidget):
    """
    Transparent overlay that shows strategy notes during a LoL game.

    The overlay auto-positions at a fixed location (configurable via
    the web dashboard). Click-through is always enabled so gameplay
    is never interrupted.
    """

    # Signal for thread-safe UI updates
    update_requested = Signal()

    def __init__(self, strategy_file: str) -> None:
        super().__init__()

        # Import strategy reader here to avoid circular imports
        from overlay.strategy_reader import StrategyReader

        self._strategy = StrategyReader(strategy_file)
        self._prefs = self._strategy.get_global_preferences()

        # ── State ─────────────────────────────────────────
        self._enemy_champions: list[str] = []
        self._enemy_tips: list[dict] = []
        self._active_champion: str = ""
        self._game_phase: str = "NO_GAME"
        self._show_until: float = 0.0        # monotonic time when to start hiding
        self._target_opacity: float = 0.0
        self._last_phase_change: float = time.monotonic()
        self._visible_lines: list[str] = []

        # ── Setup ─────────────────────────────────────────
        self._init_window()
        self._init_timer()

        logger.info("League overlay initialized.")

    # ─── Public API (called from main.py) ──────────────────

    def on_game_data(self, all_game_data: dict, phase: str, enemy_champs: list[str], active_champ: str) -> None:
        """
        Called when game state updates from the LiveClientPoller.

        Thread-safe — emits signal to update on the Qt thread.
        """
        self._enemy_champions = enemy_champs
        self._active_champion = active_champ
        self._game_phase = phase

        # Load strategy tips for these enemies
        if enemy_champs:
            self._enemy_tips = self._strategy.get_enemy_team_tips(enemy_champs)
        else:
            self._enemy_tips = []

        # Reload prefs (may have changed from web dashboard)
        self._prefs = self._strategy.get_global_preferences()

        # Determine visibility based on phase
        if phase == "LOADING_SCREEN" and self._prefs.get("overlay_auto_show_loading_screen", True):
            self._target_opacity = self._prefs.get("overlay_opacity", 0.85)
            duration = self._prefs.get("overlay_show_duration_seconds", 15)
            self._show_until = time.monotonic() + duration
        elif phase == "IN_GAME":
            # Keep showing for configured seconds after game starts, then fade
            if self._show_until == 0:
                duration = self._prefs.get("overlay_show_duration_seconds", 15)
                self._show_until = time.monotonic() + duration
            self._target_opacity = self._prefs.get("overlay_opacity", 0.85)
        elif phase == "NO_GAME" or phase == "GAME_ENDED":
            self._target_opacity = 0.0
            self._show_until = 0.0
        elif phase == "CHAMP_SELECT":
            # Show briefly during champ select
            self._target_opacity = self._prefs.get("overlay_opacity", 0.85)
            self._show_until = time.monotonic() + 30

        self._last_phase_change = time.monotonic()
        self.update_requested.emit()

    def refresh_preferences(self) -> None:
        """Reload preferences from strategy.json (called on file change)."""
        self._prefs = self._strategy.get_global_preferences()
        self._apply_prefs()
        self.update()

    # ─── Initialization ─────────────────────────────────────

    def _init_window(self) -> None:
        """Configure window flags and geometry for the transparent overlay."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # Apply geometry from preferences
        self._apply_prefs()

    def _apply_prefs(self) -> None:
        """Update window geometry from preferences."""
        width = self._prefs.get("overlay_width", DEFAULT_WIDTH)
        x = self._prefs.get("overlay_x", DEFAULT_X)
        y = self._prefs.get("overlay_y", DEFAULT_Y)

        # Estimate height based on font size and max possible lines
        font_size = self._prefs.get("overlay_font_size", 14)
        max_lines = 10  # Max we'd ever show (5 enemies × 2 lines each)
        line_height = font_size + 4 + LINE_SPACING_PX
        height = (max_lines * line_height) + TITLE_GAP + SIDE_PADDING * 2 + 80

        self.setGeometry(x, y, width, height)
        self.setFixedSize(width, height)

    def _init_timer(self) -> None:
        """Set up the refresh timer for UI updates and opacity fade."""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.start()

        # Connect signal for cross-thread updates
        self.update_requested.connect(self._on_update_requested)

    # ─── Window Styles (Win32) ─────────────────────────────

    def showEvent(self, event) -> None:
        """Apply Win32 styles after the window is shown."""
        super().showEvent(event)
        self._apply_window_styles()

    def _apply_window_styles(self) -> None:
        """
        Set Win32 extended styles:
          WS_EX_LAYERED    — required for per-pixel alpha
          WS_EX_NOACTIVATE — never steal focus from League
          WS_EX_TRANSPARENT — click-through (always on for gaming)
        """
        if sys.platform != "win32":
            return

        try:
            import win32gui
            import win32con

            hwnd = int(self.winId())
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style |= win32con.WS_EX_LAYERED
            ex_style |= win32con.WS_EX_NOACTIVATE
            ex_style |= win32con.WS_EX_TRANSPARENT  # Always click-through

            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
            win32gui.SetWindowPos(
                hwnd, 0, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE |
                win32con.SWP_FRAMECHANGED,
            )
            logger.debug("Window styles applied (click-through always on).")
        except ImportError:
            logger.warning("pywin32 not available — window styles not applied.")
        except Exception:
            logger.exception("Failed to apply window styles.")

    # ─── Event Overrides ───────────────────────────────────

    def paintEvent(self, event) -> None:
        """Custom paint: render strategy notes with outlined text."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Near-invisible fill for full-window hit-testing
        painter.fillRect(self.rect(), GRAB_FILL_COLOR)

        font_family = self._prefs.get("overlay_font_family", "Segoe UI")
        font_size = self._prefs.get("overlay_font_size", 14)

        header_font = QFont(font_family, CHAMPION_HEADER_SIZE, QFont.Weight.Bold)
        tip_font = QFont(font_family, TIP_TEXT_SIZE)
        title_font = QFont(font_family, font_size, QFont.Weight.Bold)
        normal_font = QFont(font_family, font_size)

        fm_title = QFontMetrics(title_font)
        fm_tip = QFontMetrics(tip_font)
        line_height = fm_tip.height() + LINE_SPACING_PX

        overlay_width = self._prefs.get("overlay_width", DEFAULT_WIDTH)

        def center_x(text: str, fm: QFontMetrics) -> int:
            return (overlay_width - fm.horizontalAdvance(text)) // 2

        y = SIDE_PADDING

        # ── Title line ──────────────────────────────────
        title = "LoL Stats • Strategy"
        if self._active_champion:
            title = f"As {self._active_champion} vs Enemy Team"

        painter.setFont(title_font)
        self._draw_outlined_text(
            painter,
            center_x(title, fm_title),
            y + fm_title.ascent(),
            title,
            220,
            title_font,
        )
        y += fm_title.height() + TITLE_GAP

        # ── Game phase indicator ─────────────────────────
        phase_text = self._phase_display_text()
        painter.setFont(normal_font)
        fm_normal = QFontMetrics(normal_font)
        self._draw_outlined_text(
            painter,
            center_x(phase_text, fm_normal),
            y + fm_normal.ascent(),
            phase_text,
            140,
            normal_font,
        )
        y += fm_normal.height() + 12

        # ── Enemy team strategy ───────────────────────────
        if not self._enemy_champions:
            # No game detected
            painter.setFont(normal_font)
            self._draw_outlined_text(
                painter,
                center_x(NO_GAME_MESSAGE, fm_normal),
                y + fm_normal.ascent(),
                NO_GAME_MESSAGE,
                160,
                normal_font,
            )
            painter.end()
            return

        if not any(t.get("tips") for t in self._enemy_tips) and not any(
            t.get("personal_notes") for t in self._enemy_tips
        ):
            # No strategy data
            painter.setFont(tip_font)
            self._draw_outlined_text(
                painter,
                center_x(NO_STRATEGY_MESSAGE, fm_tip),
                y + fm_tip.ascent(),
                NO_STRATEGY_MESSAGE,
                140,
                tip_font,
            )
            painter.end()
            return

        # ── Render per-champion tips ──────────────────────
        for enemy in self._enemy_tips:
            # Check if we have room (leave margin at bottom)
            if y + line_height > self.height() - 20:
                painter.setFont(tip_font)
                self._draw_outlined_text(
                    painter,
                    center_x("... more", fm_tip),
                    y + fm_tip.ascent(),
                    "... more",
                    100,
                    tip_font,
                )
                break

            champ_name = enemy["champion"]
            tips = enemy.get("tips", [])
            notes = enemy.get("personal_notes", "")
            is_missing = enemy.get("missing", False)

            # Champion header
            painter.setFont(header_font)
            fm_h = QFontMetrics(header_font)
            header = f"▸ {champ_name}"
            if is_missing:
                header += " (no notes)"
            self._draw_outlined_text(
                painter,
                SIDE_PADDING,
                y + fm_h.ascent(),
                header,
                200 if not is_missing else 100,
                header_font,
            )
            y += fm_h.height() + 2

            # Tips
            if tips:
                painter.setFont(tip_font)
                for tip in tips[:3]:  # Max 3 tips per champion
                    if y + line_height > self.height() - 20:
                        break
                    # Truncate long tips
                    display_tip = tip[:90] + "..." if len(tip) > 90 else tip
                    self._draw_outlined_text(
                        painter,
                        SIDE_PADDING + 12,
                        y + fm_tip.ascent(),
                        f"• {display_tip}",
                        160,
                        tip_font,
                    )
                    y += line_height

            # Personal notes
            if notes and y + line_height < self.height() - 20:
                painter.setFont(tip_font)
                display_note = notes[:90] + "..." if len(notes) > 90 else notes
                self._draw_outlined_text(
                    painter,
                    SIDE_PADDING + 12,
                    y + fm_tip.ascent(),
                    f"📝 {display_note}",
                    140,
                    tip_font,
                )
                y += line_height

            y += 6  # Gap between champions
            if y > self.height() - 20:
                break

        painter.end()

    def _draw_outlined_text(
        self,
        painter: QPainter,
        x: int,
        baseline: int,
        text: str,
        alpha: int,
        font: QFont,
    ) -> None:
        """
        Draw text with a black outline and white fill — readable on any
        background. Same technique as Phantom Lyrics.

        Uses QPainterPath: stroke the path for outline, fill for the text.
        """
        if not text:
            return

        path = QPainterPath()
        path.addText(x, baseline, font, text)

        # Outline
        outline_color = QColor(SHADOW_COLOR)
        outline_color.setAlpha(alpha)
        outline_pen = QPen(outline_color)
        outline_pen.setWidthF(2.5)
        outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(outline_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Fill
        fill_color = QColor(TEXT_COLOR)
        fill_color.setAlpha(alpha)
        painter.setPen(QPen(fill_color))
        painter.setBrush(QBrush(fill_color))
        painter.drawPath(path)

    # ─── Tick & Auto-hide ──────────────────────────────────

    @Slot()
    def _tick(self) -> None:
        """Called by the timer to handle auto-hide fade and repaint."""
        now = time.monotonic()

        # Determine target opacity based on show_until
        if self._show_until > 0 and now < self._show_until:
            self._target_opacity = self._prefs.get("overlay_opacity", 0.85)
        elif self._show_until > 0 and now >= self._show_until:
            self._target_opacity = 0.0
            self._show_until = 0.0

        # Smoothly approach target opacity
        current = self.windowOpacity()
        if current < self._target_opacity:
            current = min(self._target_opacity, current + AUTO_HIDE_FADE_STEP)
            self.setWindowOpacity(current)
        elif current > self._target_opacity:
            current = max(self._target_opacity, current - AUTO_HIDE_FADE_STEP)
            self.setWindowOpacity(current)

        # Hide window entirely when fully faded
        if current <= 0.01 and self.isVisible():
            self.hide()
        elif current > 0.01 and not self.isVisible():
            self.show()

        self.update()

    @Slot()
    def _on_update_requested(self) -> None:
        """Handle cross-thread update signal."""
        # Refresh prefs in case they changed
        self._apply_prefs()
        self.update()

    # ─── Helpers ───────────────────────────────────────────

    def _phase_display_text(self) -> str:
        """Get a user-friendly text for the current game phase."""
        phases = {
            "NO_GAME": "No active game",
            "CHAMP_SELECT": "Champion Select",
            "LOADING_SCREEN": "Loading Screen — Study Your Matchups",
            "IN_GAME": "Game in Progress",
            "GAME_ENDED": "Game Ended",
        }
        return phases.get(self._game_phase, self._game_phase)
