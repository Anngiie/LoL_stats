"""
LoL Stats - Strategy Reader
=============================
Reads the shared strategy.json file and provides champion-specific
data to the overlay.

Watches the file's mtime (modification time) so the overlay picks up
changes made from the web dashboard without needing a restart.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class StrategyReader:
    """
    Reads strategy data from the shared JSON file.
    Periodically checks for file changes via mtime.
    """

    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)
        self._data: dict = {}
        self._last_mtime: float = 0.0
        self._global_prefs: dict = {}
        self.reload()

    # ── File I/O ───────────────────────────────────────────

    def reload(self) -> bool:
        """
        Reload strategy data from disk if the file has changed.
        Returns True if data was reloaded.
        """
        try:
            if not self._path.exists():
                logger.debug("Strategy file not found: %s", self._path)
                return False

            current_mtime = self._path.stat().st_mtime
            if current_mtime <= self._last_mtime:
                return False  # No change

            raw = self._path.read_text(encoding="utf-8")
            self._data = json.loads(raw)
            self._last_mtime = current_mtime
            self._global_prefs = self._data.get("global_preferences", {})
            logger.debug("Strategy data reloaded (%d champions).", len(self._data.get("champions", {})))
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to reload strategy: %s", e)
            return False

    # ── Champion queries ───────────────────────────────────

    def get_champion_strategy(self, champion_name: str) -> dict | None:
        """Get strategy for a specific champion, or None if not found."""
        self.reload()
        return self._data.get("champions", {}).get(champion_name)

    def get_champion_context(self, champion_name: str, context: str) -> dict | None:
        """
        Get a specific context block for a champion.

        Args:
            champion_name: Champion to look up (case-insensitive).
            context: One of 'vs_support', 'with_adc', 'with_jungler'.

        Returns:
            {champion, context_block, personal_notes, priority} or None.
        """
        self.reload()
        champions = self._data.get("champions", {})
        for champ_name, champ_data in champions.items():
            if champ_name.lower() == champion_name.lower():
                block = champ_data.get(context, {}) or {}
                return {
                    "champion": champ_name,
                    "block": block,
                    "personal_notes": champ_data.get("personal_notes", ""),
                    "priority": champ_data.get("overlay_priority", "normal"),
                }
        return None

    def get_enemy_team_tips(self, enemy_champions: list[str]) -> list[dict]:
        """
        Get strategy notes for a full enemy team.

        Returns a list of {champion, priority, tips} dicts,
        sorted by overlay_priority (high first), then alphabetically.
        """
        self.reload()
        results = []
        champions = self._data.get("champions", {})

        for name in enemy_champions:
            # Case-insensitive lookup
            entry = None
            for champ_name, champ_data in champions.items():
                if champ_name.lower() == name.lower():
                    entry = champ_data
                    name = champ_name  # Use correct casing
                    break

            if entry:
                # Strategy is now organized by context. For enemy champions we
                # use the "vs_support" block (how to play vs them).
                vs = entry.get("vs_support", {}) or {}
                results.append({
                    "champion": name,
                    "priority": entry.get("overlay_priority", "normal"),
                    "tips": vs.get("how_to_play", []),
                    "counters": vs.get("counters", []),
                    "personal_notes": entry.get("personal_notes", ""),
                })
            else:
                # No strategy for this champion — placeholder
                results.append({
                    "champion": name,
                    "priority": "normal",
                    "tips": [],
                    "counters": [],
                    "personal_notes": "",
                    "missing": True,
                })

        # Sort: high priority first, then alphabetically
        priority_order = {"high": 0, "normal": 1, "low": 2}
        results.sort(key=lambda r: (priority_order.get(r["priority"], 1), r["champion"]))
        return results

    def get_global_preferences(self) -> dict:
        """Get overlay settings from the strategy file."""
        self.reload()
        defaults = {
            "overlay_always_visible": True,
            "overlay_auto_show_loading_screen": True,
            "overlay_show_duration_seconds": 15,
            "overlay_opacity": 0.85,
            "overlay_font_size": 14,
            "overlay_font_family": "JetBrains Mono",
            "overlay_width": 420,
            "overlay_x": 20,
            "overlay_y": 60,
        }
        prefs = {**defaults, **self._global_prefs}
        return prefs
