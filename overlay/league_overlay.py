"""
LoL Stats - League Overlay Widget (Single-Panel, Karakal Design)
==================================================================
Dark panel with corner brackets, HUD grid, and JetBrains Mono text.
Matches the web dashboard's Karakal-inspired tactical aesthetic.

Three instances are created by main.py — each positioned at a different
screen corner and rendering a different strategy context.
"""

import logging
import sys
import time

from PySide6.QtCore import Qt, QTimer, QRect, Signal, Slot
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QFontMetrics
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

# ─── Karakal Design Tokens ──────────────────────────────────

BG_DEEP    = QColor(8, 9, 11, 200)       # #08090b ~78% opacity
SURFACE    = QColor(13, 15, 18)          # #0d0f12
ELEVATED   = QColor(18, 21, 25)          # #121519
BORDER     = QColor(35, 40, 48)          # #232830
BORDER_LIGHT = QColor(53, 60, 71)        # #353c47

GOLD       = QColor(204, 167, 79)        # #cca74f
GOLD_DIM   = QColor(124, 103, 49)        # #7c6731
GOLD_BRIGHT = QColor(242, 217, 143)      # #f2d98f

TEXT       = QColor(232, 234, 237)       # #e8eaed
TEXT_DIM   = QColor(197, 200, 204)       # #c5c8cc
MUTED      = QColor(139, 147, 160)       # #8b93a0
FAINT      = QColor(90, 97, 109)         # #5a616d

WIN_COLOR  = QColor(79, 209, 138)        # #4fd18a
LOSS_COLOR = QColor(236, 106, 94)        # #ec6a5e

GRAB_FILL_COLOR = QColor(0, 0, 0, 1)

AUTO_HIDE_FADE_STEP = 0.05
TICK_INTERVAL_MS = 100

SIDE_PADDING = 16
LINE_SPACING_PX = 4
HEADER_GAP = 10
HEADER_FONT_SIZE = 9
CHAMP_FONT_SIZE = 14
TIP_FONT_SIZE = 10
MAX_TIP_LEN = 120
MAX_TIPS = 3
MAX_WRAP_PER_TIP = 4
PANEL_WIDTH = 420
CORNER_SIZE = 12
CORNER_THICKNESS = 2
GRID_SIZE = 40
GRID_COLOR = QColor(140, 150, 165, 10)
PANEL_MARGIN = 2

DEFAULT_OPACITY = 0.88
FONT_FAMILY = "JetBrains Mono"
FONT_DISPLAY = "Martian Mono"

NO_GAME_MSG = "Waiting for game..."
NO_DATA_MSG = "No notes — add in web dashboard"
NOT_DETECTED_MSG = "Not detected yet"

# Per-panel configuration: title, accent color, screen position
PANEL_CONFIGS = {
    "vs_support": {
        "title": "VS ENEMY SUPPORT",
        "color": QColor(236, 106, 94),    # red
        "position": "top_left",
    },
    "with_adc": {
        "title": "WITH YOUR ADC",
        "color": QColor(79, 209, 138),    # green
        "position": "bottom_left",
    },
    "with_jungler": {
        "title": "WITH YOUR JUNGLER",
        "color": QColor(204, 167, 79),    # gold
        "position": "top_right",
    },
}

COMP_KEY = {
    "vs_support": "enemy_support",
    "with_adc": "allied_adc",
    "with_jungler": "allied_jungler",
}


class LeagueOverlay(QWidget):
    """
    Single-panel dark overlay for one strategy context.
    Renders a Karakal-style dark panel with corner brackets and HUD grid.
    """

    update_requested = Signal()

    def __init__(self, strategy_file: str, panel_key: str) -> None:
        super().__init__()

        from overlay.strategy_reader import StrategyReader
        self._strategy = StrategyReader(strategy_file)
        self._prefs = self._strategy.get_global_preferences()

        self._panel_key = panel_key
        self._config = PANEL_CONFIGS[panel_key]

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
        prev = self._phase
        self._phase = phase

        comp_key = COMP_KEY[self._panel_key]
        champ = team_comp.get(comp_key, "")
        self._champion = champ

        self._lines = []
        if champ:
            ctx = self._strategy.get_champion_context(champ, self._panel_key)
            if ctx:
                self._lines = self._extract_lines(ctx.get("block", {}))

        self._prefs = self._strategy.get_global_preferences()
        self._resize_for_content()

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

    # ─── Strategy extraction ────────────────────────────────

    def _extract_lines(self, block: dict) -> list[str]:
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
        self._apply_geometry(self._estimate_height())

    def _get_position(self, width: int, height: int) -> tuple[int, int]:
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
        x, y = self._get_position(PANEL_WIDTH, height)
        self.setGeometry(x, y, PANEL_WIDTH, height)

    def _estimate_height(self) -> int:
        line_h = TIP_FONT_SIZE + LINE_SPACING_PX + 2
        return (HEADER_FONT_SIZE + HEADER_GAP) + (CHAMP_FONT_SIZE + 6) + \
               (MAX_TIPS * MAX_WRAP_PER_TIP * line_h) + SIDE_PADDING * 2 + 20

    def _wrap_text(self, text: str, fm, max_width: int) -> list[str]:
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
        font_family = self._prefs.get("overlay_font_family", "JetBrains Mono")
        tip_font = QFont(font_family, TIP_FONT_SIZE)
        fm_tip = QFontMetrics(tip_font)
        header_font = QFont(FONT_DISPLAY, HEADER_FONT_SIZE, QFont.Weight.Bold)
        champ_font = QFont(FONT_DISPLAY, CHAMP_FONT_SIZE, QFont.Weight.Bold)

        text_width = PANEL_WIDTH - SIDE_PADDING * 2 - 20

        self._wrapped_tips: list[list[str]] = []
        total_wrapped = 0
        for line in self._lines[:MAX_TIPS]:
            wrapped = self._wrap_text(line, fm_tip, text_width)[:MAX_WRAP_PER_TIP]
            self._wrapped_tips.append(wrapped)
            total_wrapped += len(wrapped)

        line_h = fm_tip.height() + LINE_SPACING_PX
        fm_header = QFontMetrics(header_font)
        fm_champ = QFontMetrics(champ_font)

        tip_lines = max(total_wrapped, 1)
        content_h = fm_header.height() + HEADER_GAP + fm_champ.height() + 6
        content_h += tip_lines * line_h
        height = content_h + SIDE_PADDING * 2 + 16

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

    # ─── Paint (Karakal Design) ─────────────────────────────

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setClipRect(self.rect())

        # Hit-testing fill
        p.fillRect(self.rect(), GRAB_FILL_COLOR)

        # ── Dark panel background ──
        m = PANEL_MARGIN
        panel_rect = QRect(m, m, self.width() - m * 2, self.height() - m * 2)
        p.setBrush(QBrush(BG_DEEP))
        p.setPen(QPen(BORDER, 1))
        p.drawRoundedRect(panel_rect, 4, 4)

        # ── HUD grid pattern ──
        p.setPen(QPen(GRID_COLOR, 1))
        inner_left = m + 1
        inner_top = m + 1
        inner_right = self.width() - m - 1
        inner_bottom = self.height() - m - 1
        gx = inner_left + GRID_SIZE
        while gx < inner_right:
            p.drawLine(gx, inner_top, gx, inner_bottom)
            gx += GRID_SIZE
        gy = inner_top + GRID_SIZE
        while gy < inner_bottom:
            p.drawLine(inner_left, gy, inner_right, gy)
            gy += GRID_SIZE

        # ── Corner brackets (panel accent color) ──
        accent = self._config["color"]
        bracket_pen = QPen(accent, CORNER_THICKNESS)
        bracket_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(bracket_pen)
        cs = CORNER_SIZE

        # Top-left
        p.drawLine(m, m, m + cs, m)
        p.drawLine(m, m, m, m + cs)
        # Top-right
        p.drawLine(self.width() - m - cs, m, self.width() - m, m)
        p.drawLine(self.width() - m, m, self.width() - m, m + cs)
        # Bottom-left
        p.drawLine(m, self.height() - m, m + cs, self.height() - m)
        p.drawLine(m, self.height() - m - cs, m, self.height() - m)
        # Bottom-right
        p.drawLine(self.width() - m - cs, self.height() - m, self.width() - m, self.height() - m)
        p.drawLine(self.width() - m, self.height() - m - cs, self.width() - m, self.height() - m)

        # ── Text content ──
        font_family = self._prefs.get("overlay_font_family", "JetBrains Mono")
        header_font = QFont(FONT_DISPLAY, HEADER_FONT_SIZE, QFont.Weight.Bold)
        champ_font = QFont(FONT_DISPLAY, CHAMP_FONT_SIZE, QFont.Weight.Bold)
        tip_font = QFont(font_family, TIP_FONT_SIZE)

        fm_header = QFontMetrics(header_font)
        fm_champ = QFontMetrics(champ_font)
        fm_tip = QFontMetrics(tip_font)

        usable_width = self.width() - SIDE_PADDING * 2
        x = SIDE_PADDING
        y = SIDE_PADDING + 2

        # ── No game state ──
        if self._phase in ("NO_GAME", "GAME_ENDED"):
            p.setFont(tip_font)
            p.setPen(QPen(MUTED))
            p.drawText(QRect(x, y, usable_width, fm_tip.height()),
                       Qt.AlignmentFlag.AlignLeft, NO_GAME_MSG)
            p.end()
            return

        # ── Section header (accent colored, uppercase) ──
        p.setFont(header_font)
        p.setPen(QPen(accent))
        header_text = fm_header.elidedText(
            self._config["title"], Qt.TextElideMode.ElideRight, usable_width)
        p.drawText(QRect(x, y, usable_width, fm_header.height()),
                   Qt.AlignmentFlag.AlignLeft, header_text)
        y += fm_header.height() + HEADER_GAP

        # ── Champion name ──
        if self._champion:
            p.setFont(champ_font)
            p.setPen(QPen(TEXT))
            champ_text = fm_champ.elidedText(
                self._champion, Qt.TextElideMode.ElideRight, usable_width)
            p.drawText(QRect(x, y, usable_width, fm_champ.height()),
                       Qt.AlignmentFlag.AlignLeft, champ_text)
            y += fm_champ.height() + 6
        else:
            p.setFont(tip_font)
            p.setPen(QPen(MUTED))
            p.drawText(QRect(x, y, usable_width, fm_tip.height()),
                       Qt.AlignmentFlag.AlignLeft, NOT_DETECTED_MSG)
            p.end()
            return

        # ── Tips ──
        p.setFont(tip_font)
        wrapped_tips = getattr(self, '_wrapped_tips', None)
        if wrapped_tips:
            for tip_lines in wrapped_tips:
                for li, wl in enumerate(tip_lines):
                    prefix = "> " if li == 0 else "  "
                    text = prefix + wl
                    text = fm_tip.elidedText(
                        text, Qt.TextElideMode.ElideRight, usable_width - 4)
                    p.setPen(QPen(TEXT_DIM))
                    p.drawText(QRect(x, y, usable_width, fm_tip.height()),
                               Qt.AlignmentFlag.AlignLeft, text)
                    y += fm_tip.height() + LINE_SPACING_PX
        elif self._lines:
            for line in self._lines[:MAX_TIPS]:
                display = line[:MAX_TIP_LEN] + "..." if len(line) > MAX_TIP_LEN else line
                text = "> " + display
                text = fm_tip.elidedText(
                    text, Qt.TextElideMode.ElideRight, usable_width - 4)
                p.setPen(QPen(TEXT_DIM))
                p.drawText(QRect(x, y, usable_width, fm_tip.height()),
                           Qt.AlignmentFlag.AlignLeft, text)
                y += fm_tip.height() + LINE_SPACING_PX
        else:
            p.setPen(QPen(FAINT))
            p.drawText(QRect(x, y, usable_width, fm_tip.height()),
                       Qt.AlignmentFlag.AlignLeft, "> " + NO_DATA_MSG)

        p.end()

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
