"""
LoL Stats - League Overlay Widget (Single-Panel)
==================================================
A transparent, always-on-top, frameless PySide6 window that displays
strategy notes for ONE context (vs enemy support / with ADC / with jungler).

Three instances are created by main.py — each positioned at a different
screen corner and rendering a different strategy context.

Techniques:
  - FramelessWindowHint | WindowStaysOnTopHint | Tool
  - WA_TranslucentBackground — fully transparent background
  - WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT via win32gui
  - QPainterPath outlined text for readability on any background
  - QTimer for smooth opacity fade
"""

import logging
import sys
import time

from PySide6.QtCore import Qt, QTimer, QRect, Signal, Slot
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPainterPath, QFontMetrics
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

# ─── Constants ───────────────────────────────────────────

TEXT_COLOR = QColor(255, 255, 255)
OUTLINE_COLOR = QColor(0, 0, 0)
GRAB_FILL_COLOR = QColor(0, 0, 0, 1)

AUTO_HIDE_FADE_STEP = 0.05
TICK_INTERVAL_MS = 100

SIDE_PADDING = 14
LINE_SPACING_PX = 3
HEADER_GAP = 8
HEADER_FONT_SIZE = 12
CHAMP_FONT_SIZE = 12
TIP_FONT_SIZE = 11
MAX_TIP_LEN = 120
MAX_TIPS = 3
MAX_WRAP_PER_TIP = 4
PANEL_WIDTH = 440

DEFAULT_OPACITY = 0.85

NO_GAME_MSG = "Waiting for game..."
NO_DATA_MSG = "No notes — add in web dashboard"
NOT_DETECTED_MSG = "Not detected yet"

# Per-panel configuration: title, icon, accent color, screen position
PANEL_CONFIGS = {
    "vs_support": {
        "title": "VS ENEMY SUPPORT",
        "icon": "⚔",
        "color": QColor(212, 75, 90),
        "position": "top_left",
    },
    "with_adc": {
        "title": "WITH YOUR ADC",
        "icon": "🏹",
        "color": QColor(74, 158, 124),
        "position": "bottom_left",
    },
    "with_jungler": {
        "title": "WITH YOUR JUNGLER",
        "icon": "🌲",
        "color": QColor(200, 167, 90),
        "position": "top_right",
    },
}

# Maps panel key → team_comp key for champion lookup
COMP_KEY = {
    "vs_support": "enemy_support",
    "with_adc": "allied_adc",
    "with_jungler": "allied_jungler",
}


class LeagueOverlay(QWidget):
    """
    Single-panel transparent overlay for one strategy context.

    Instantiate with panel_key = 'vs_support' | 'with_adc' | 'with_jungler'.
    The overlay auto-positions at its designated screen corner and renders
    outlined text (no opaque background).
    """

    update_requested = Signal()

    def __init__(self, strategy_file: str, panel_key: str) -> None:
        super().__init__()

        from overlay.strategy_reader import StrategyReader
        self._strategy = StrategyReader(strategy_file)
        self._prefs = self._strategy.get_global_preferences()

        self._panel_key = panel_key
        self._config = PANEL_CONFIGS[panel_key]

        # ── State ──
        self._champion: str = ""
        self._lines: list[str] = []
        self._phase: str = "NO_GAME"
        self._show_until: float = 0.0
        self._target_opacity: float = 0.0
        self._was_visible: bool = False

        self._init_window()
        self._init_timer()
        logger.info("Overlay '%s' initialized at %s", panel_key, self._config["position"])

    # ─── Public API ──────────────────────────────────────────

    def on_game_data(self, phase: str, team_comp: dict) -> None:
        """Update this panel's data from team composition."""
        prev = self._phase
        self._phase = phase

        comp_key = COMP_KEY[self._panel_key]
        champ = team_comp.get(comp_key, "")
        self._champion = champ

        # Look up strategy for this champion in this context
        self._lines = []
        if champ:
            ctx = self._strategy.get_champion_context(champ, self._panel_key)
            if ctx:
                self._lines = self._extract_lines(ctx.get("block", {}))

        self._prefs = self._strategy.get_global_preferences()

        # Pre-wrap lines and resize window to fit content
        self._resize_for_content()

        # ── Visibility ──
        phase_changed = prev != phase
        always_visible = self._prefs.get("overlay_always_visible", True)
        opacity = self._prefs.get("overlay_opacity", DEFAULT_OPACITY)

        if phase in ("IN_GAME", "LOADING_SCREEN", "CHAMP_SELECT"):
            if always_visible:
                self._target_opacity = opacity
                self._show_until = 0.0
            else:
                duration = self._prefs.get("overlay_show_duration_seconds", 15)
                self._target_opacity = opacity
                self._show_until = time.monotonic() + duration
            if phase_changed:
                logger.info("[%s] phase %s — visible (always=%s)",
                           self._panel_key, phase, always_visible)
        else:
            self._target_opacity = 0.0
            self._show_until = 0.0

        self.update_requested.emit()

    def refresh_preferences(self) -> None:
        self._prefs = self._strategy.get_global_preferences()
        self._position_window()
        self.update()

    # ─── Strategy extraction ────────────────────────────────

    def _extract_lines(self, block: dict) -> list[str]:
        """Pull the most relevant tips from a context block."""
        lines: list[str] = []

        if self._panel_key == "vs_support":
            for tip in block.get("how_to_play", [])[:MAX_TIPS]:
                lines.append(tip)
            counters = block.get("counters", [])
            if counters and len(lines) < MAX_TIPS:
                lines.append("Counters: " + ", ".join(counters[:3]))
            if not lines and block.get("more_info"):
                lines.append(block["more_info"])

        elif self._panel_key == "with_adc":
            if block.get("gameplan"):
                lines.append(block["gameplan"])
            if block.get("adc_solo") and len(lines) < MAX_TIPS:
                lines.append("ADC solo: " + block["adc_solo"])
            if block.get("how_to_trade") and len(lines) < MAX_TIPS:
                lines.append("Trade: " + block["how_to_trade"])
            if block.get("when_to_roam") and len(lines) < MAX_TIPS:
                lines.append("Roam: " + block["when_to_roam"])

        elif self._panel_key == "with_jungler":
            if block.get("gameplan"):
                lines.append(block["gameplan"])
            if block.get("synergy") and len(lines) < MAX_TIPS:
                lines.append("Synergy: " + block["synergy"])
            if block.get("vision_level1") and len(lines) < MAX_TIPS:
                lines.append("Vision: " + block["vision_level1"])

        return lines

    # ─── Window setup ────────────────────────────────────────

    def _init_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._position_window()

    def _position_window(self) -> None:
        """Initial position — actual sizing happens in _resize_for_content."""
        self._apply_geometry(self._estimate_height())

    def _get_position(self, width: int, height: int) -> tuple[int, int]:
        """Return (x, y) for this panel's screen corner."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            sw, sh = geo.width(), geo.height()
        else:
            sw, sh = 1920, 1080
        pos = self._config["position"]
        margin = 20
        if pos == "top_left":
            return margin, 60
        elif pos == "bottom_left":
            return margin, sh - height - margin - 40
        elif pos == "top_right":
            return sw - width - margin, 60
        return margin, 60

    def _apply_geometry(self, height: int) -> None:
        """Set window geometry for the current panel width/height."""
        x, y = self._get_position(PANEL_WIDTH, height)
        self.setGeometry(x, y, PANEL_WIDTH, height)

    def _estimate_height(self) -> int:
        """Rough height estimate for initial sizing."""
        line_h = TIP_FONT_SIZE + LINE_SPACING_PX + 2
        return (HEADER_FONT_SIZE + HEADER_GAP) + (CHAMP_FONT_SIZE + 6) + \
               (MAX_TIPS * MAX_WRAP_PER_TIP * line_h) + SIDE_PADDING * 2

    def _wrap_text(self, text: str, fm, max_width: int) -> list[str]:
        """Word-wrap text to fit within max_width pixels."""
        words = text.split()
        if not words:
            return [text]
        lines = []
        current = ""
        for word in words:
            test = current + (" " if current else "") + word
            if fm.horizontalAdvance(test) > max_width and current:
                lines.append(current)
                current = word
            else:
                current = test
        if current:
            lines.append(current)
        return lines

    def _resize_for_content(self) -> None:
        """Pre-wrap tip lines and resize the window to fit all content."""
        font_family = self._prefs.get("overlay_font_family", "Segoe UI")
        tip_font = QFont(font_family, TIP_FONT_SIZE)
        fm_tip = QFontMetrics(tip_font)
        header_font = QFont(font_family, HEADER_FONT_SIZE, QFont.Weight.Bold)
        champ_font = QFont(font_family, CHAMP_FONT_SIZE, QFont.Weight.Bold)

        # Text area: from x=14+10=24 to right edge minus 14px margin
        text_width = PANEL_WIDTH - SIDE_PADDING * 2 - 16

        # Wrap each tip into visual lines
        self._wrapped_tips: list[list[str]] = []
        total_wrapped = 0
        for line in self._lines[:MAX_TIPS]:
            wrapped = self._wrap_text(line, fm_tip, text_width)[:MAX_WRAP_PER_TIP]
            self._wrapped_tips.append(wrapped)
            total_wrapped += len(wrapped)

        # Calculate needed height with generous bottom padding
        line_h = fm_tip.height() + LINE_SPACING_PX
        fm_header = QFontMetrics(header_font)
        fm_champ = QFontMetrics(champ_font)

        tip_lines = max(total_wrapped, 1)
        content_h = fm_header.height() + HEADER_GAP + fm_champ.height() + 4
        content_h += tip_lines * line_h
        # Generous bottom padding — 40px ensures no descender clipping
        height = content_h + SIDE_PADDING * 2 + 40

        self._apply_geometry(height)

    def _init_timer(self) -> None:
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(TICK_INTERVAL_MS)
        self._timer.start()
        self.update_requested.connect(self._on_update_requested)

    # ─── Win32 styles ────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_window_styles()

    def _apply_window_styles(self) -> None:
        if sys.platform != "win32":
            return
        try:
            import win32gui
            import win32con

            hwnd = int(self.winId())
            ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex |= win32con.WS_EX_LAYERED
            ex |= win32con.WS_EX_NOACTIVATE
            ex |= win32con.WS_EX_TRANSPARENT
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex)
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED,
            )
        except ImportError:
            logger.warning("pywin32 not available — styles not applied.")
        except Exception:
            logger.exception("Failed to apply window styles.")

    # ─── Paint ───────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Explicit clip to prevent text from bleeding past window edges
        p.setClipRect(self.rect())

        # Hit-testing fill
        p.fillRect(self.rect(), GRAB_FILL_COLOR)

        font_family = self._prefs.get("overlay_font_family", "Segoe UI")
        header_font = QFont(font_family, HEADER_FONT_SIZE, QFont.Weight.Bold)
        champ_font = QFont(font_family, CHAMP_FONT_SIZE, QFont.Weight.Bold)
        tip_font = QFont(font_family, TIP_FONT_SIZE)

        fm_header = QFontMetrics(header_font)
        fm_champ = QFontMetrics(champ_font)
        fm_tip = QFontMetrics(tip_font)

        # Use full window width for text area — no extra right margin needed
        usable_width = self.width() - SIDE_PADDING * 2
        x = SIDE_PADDING
        y = SIDE_PADDING

        # ── No game ──
        if self._phase in ("NO_GAME", "GAME_ENDED"):
            self._draw_text(p, x, y + fm_tip.ascent(), NO_GAME_MSG, 120, tip_font)
            p.end()
            return

        # ── Section header ──
        header = self._config["icon"] + " " + self._config["title"]
        # Truncate if header is wider than window
        header_elided = fm_header.elidedText(header, Qt.TextElideMode.ElideRight, usable_width)
        self._draw_text_colored(p, x, y + fm_header.ascent(), header_elided,
                                self._config["color"], header_font)
        y += fm_header.height() + HEADER_GAP

        # ── Champion name ──
        if self._champion:
            champ_text = "▸ " + self._champion
            champ_text = fm_champ.elidedText(champ_text, Qt.TextElideMode.ElideRight, usable_width - 8)
            self._draw_text(p, x + 4, y + fm_champ.ascent(),
                            champ_text, 220, champ_font)
            y += fm_champ.height() + 4
        else:
            self._draw_text(p, x + 4, y + fm_tip.ascent(), NOT_DETECTED_MSG, 140, tip_font)
            p.end()
            return

        # ── Tips ──
        wrapped_tips = getattr(self, '_wrapped_tips', None)
        if wrapped_tips:
            for tip_lines in wrapped_tips:
                for li, wl in enumerate(tip_lines):
                    prefix = "• " if li == 0 else "  "
                    text = prefix + wl
                    # Elide if still too wide for the window
                    text = fm_tip.elidedText(text, Qt.TextElideMode.ElideRight, usable_width - 16)
                    self._draw_text(p, x + 10, y + fm_tip.ascent(),
                                    text, 190, tip_font)
                    y += fm_tip.height() + LINE_SPACING_PX
        elif self._lines:
            for line in self._lines[:MAX_TIPS]:
                display = line[:MAX_TIP_LEN] + "..." if len(line) > MAX_TIP_LEN else line
                text = "• " + display
                text = fm_tip.elidedText(text, Qt.TextElideMode.ElideRight, usable_width - 16)
                self._draw_text(p, x + 10, y + fm_tip.ascent(),
                                text, 190, tip_font)
                y += fm_tip.height() + LINE_SPACING_PX
        else:
            self._draw_text(p, x + 10, y + fm_tip.ascent(),
                            "• " + NO_DATA_MSG, 140, tip_font)

        p.end()

    def _draw_text(self, painter, x: int, baseline: int, text: str,
                   alpha: int, font: QFont) -> None:
        """Outlined text — white fill with black stroke."""
        if not text:
            return
        path = QPainterPath()
        path.addText(x, baseline, font, text)

        outline = QColor(OUTLINE_COLOR)
        outline.setAlpha(min(alpha + 20, 255))
        pen = QPen(outline)
        pen.setWidthF(2.5)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        fill = QColor(TEXT_COLOR)
        fill.setAlpha(alpha)
        painter.setPen(QPen(fill))
        painter.setBrush(QBrush(fill))
        painter.drawPath(path)

    def _draw_text_colored(self, painter, x: int, baseline: int, text: str,
                           color: QColor, font: QFont) -> None:
        """Outlined text with a colored fill instead of white."""
        if not text:
            return
        path = QPainterPath()
        path.addText(x, baseline, font, text)

        outline = QColor(OUTLINE_COLOR)
        outline.setAlpha(230)
        pen = QPen(outline)
        pen.setWidthF(2.5)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        fill = QColor(color)
        painter.setPen(QPen(fill))
        painter.setBrush(QBrush(fill))
        painter.drawPath(path)

    # ─── Tick / fade ─────────────────────────────────────────

    @Slot()
    def _tick(self) -> None:
        now = time.monotonic()
        if self._show_until > 0 and now >= self._show_until:
            self._target_opacity = 0.0
            self._show_until = 0.0

        current = self.windowOpacity()
        if current < self._target_opacity:
            current = min(self._target_opacity, current + AUTO_HIDE_FADE_STEP)
            self.setWindowOpacity(current)
        elif current > self._target_opacity:
            current = max(self._target_opacity, current - AUTO_HIDE_FADE_STEP)
            self.setWindowOpacity(current)

        if current <= 0.01 and self.isVisible():
            self.hide()
            self._was_visible = False
        elif current > 0.01 and not self.isVisible():
            self.show()
            self._was_visible = True
        elif current > 0.01:
            self._was_visible = True

        self.update()

    @Slot()
    def _on_update_requested(self) -> None:
        self._prefs = self._strategy.get_global_preferences()
        self.update()
