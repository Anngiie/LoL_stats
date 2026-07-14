"""
LoL Stats - Strategy Manager
=============================
Reads and writes the shared strategy.json file.

Uses atomic writes (write to temp, then os.replace) to prevent
the overlay from reading a half-written file.
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class StrategyManager:
    """Manages the shared strategy.json file with atomic writes."""

    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)

    # ── Read operations ──

    def load(self) -> dict:
        """
        Load the full strategy data from disk.
        Returns default structure if file is missing or corrupt.
        Migrates legacy flat-schema entries to the 3-context model.
        """
        try:
            if self._path.exists():
                raw = self._path.read_text(encoding="utf-8")
                data = json.loads(raw)
                # Ensure minimum structure
                data.setdefault("version", 2)
                data.setdefault("champions", {})
                data.setdefault("global_preferences", self._default_prefs())
                self._migrate_champions(data.get("champions", {}))
                return data
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read strategy file: %s. Using defaults.", e)

        return {
            "version": 2,
            "last_updated": "",
            "champions": {},
            "global_preferences": self._default_prefs(),
        }

    @staticmethod
    def _migrate_champions(champions: dict) -> None:
        """Upgrade legacy flat entries ({enemy_tips, counters, ...}) to contexts,
        and prune entries that end up completely empty."""
        legacy_list_keys = ("enemy_tips", "ally_synergy", "counters")
        empty_names = []
        for name, entry in list(champions.items()):
            if not isinstance(entry, dict):
                empty_names.append(name)
                continue

            already_migrated = any(
                k in entry for k in ("vs_support", "with_jungler", "with_adc")
            )

            if not already_migrated:
                # Build a vs_support block from old fields (best-effort).
                vs = {}
                if entry.get("counters"):
                    vs["counters"] = entry["counters"]
                if entry.get("enemy_tips"):
                    vs["how_to_play"] = entry["enemy_tips"]
                if vs:
                    entry["vs_support"] = vs

                if entry.get("ally_synergy"):
                    entry.setdefault("with_adc", {})["best_supports"] = entry["ally_synergy"]

            for k in legacy_list_keys:
                entry.pop(k, None)

            # Ensure the 3 context keys + champ-level keys exist.
            entry.setdefault("vs_support", {})
            entry.setdefault("with_jungler", {})
            entry.setdefault("with_adc", {})
            entry.setdefault("personal_notes", entry.get("personal_notes", ""))
            entry.setdefault("overlay_priority", entry.get("overlay_priority", "normal"))

            # Prune only legacy entries that migrated to nothing. Freshly
            # created 3-context entries (the Add Champion flow) start empty and
            # must survive until the user fills them in.
            if (not already_migrated
                    and not entry["vs_support"] and not entry["with_jungler"]
                    and not entry["with_adc"]
                    and not entry.get("personal_notes")):
                empty_names.append(name)

        for name in empty_names:
            champions.pop(name, None)

    def get_champion(self, name: str) -> Optional[dict]:
        """Get strategy for a single champion, or None if not found."""
        data = self.load()
        return data.get("champions", {}).get(name)

    def get_all_champions(self) -> dict[str, dict]:
        """Get all champion strategies."""
        data = self.load()
        return data.get("champions", {})

    def get_global_preferences(self) -> dict:
        """Get global overlay preferences."""
        data = self.load()
        prefs = data.get("global_preferences", self._default_prefs())
        return {**self._default_prefs(), **prefs}

    # ── Write operations ──

    def update_champion(self, name: str, updates: dict) -> dict:
        """
        Create or update a champion's strategy entry.

        Supports the 3-context model. `updates` may contain:
          - vs_support, with_jungler, with_adc  (dicts → replace whole context)
          - personal_notes, overlay_priority   (scalars)
        Only provided keys are changed.
        """
        data = self.load()
        champions = data.setdefault("champions", {})

        if name not in champions:
            champions[name] = self._default_champion_entry()

        entry = champions[name]
        for key, value in updates.items():
            if key in ("vs_support", "with_jungler", "with_adc"):
                # Replace the context block wholesale when a dict is provided.
                if isinstance(value, dict):
                    entry[key] = value
            elif key in ("personal_notes", "overlay_priority"):
                entry[key] = value

        self._save(data)
        logger.info("Updated strategy for champion: %s", name)
        return entry

    def delete_champion(self, name: str) -> bool:
        """Delete a champion's strategy entry. Returns True if it existed."""
        data = self.load()
        champions = data.get("champions", {})
        if name not in champions:
            return False
        del champions[name]
        self._save(data)
        logger.info("Deleted strategy for champion: %s", name)
        return True

    def update_global_preferences(self, prefs: dict) -> dict:
        """Update global overlay preferences (partial update)."""
        data = self.load()
        existing = data.setdefault("global_preferences", self._default_prefs())
        existing.update(prefs)
        self._save(data)
        logger.info("Updated global preferences.")
        return existing

    def import_champions(self, entries: dict[str, dict]) -> dict:
        """
        Batch-import champion entries (e.g., from Excel).

        `entries` maps champion name → {context: {...}} where context is one of
        vs_support / with_jungler / with_adc. Each context block is written
        (Excel is treated as source of truth for the structured fields), while
        champ-level personal_notes and overlay_priority are preserved.

        Returns:
            {"imported": N, "skipped": M, "champions": [...]}
        """
        data = self.load()
        champions = data.setdefault("champions", {})
        imported = []
        skipped = []

        for name, entry in entries.items():
            if not name or not isinstance(entry, dict):
                skipped.append(str(name))
                continue

            champ = champions.setdefault(name, self._default_champion_entry())
            for context in ("vs_support", "with_jungler", "with_adc"):
                block = entry.get(context)
                if isinstance(block, dict) and block:
                    champ[context] = block

            imported.append(name)

        self._save(data)
        logger.info("Imported %d champions (%d skipped).", len(imported), len(skipped))
        return {
            "imported": len(imported),
            "skipped": len(skipped),
            "champions": imported,
        }

    # ── Internal ──

    def _save(self, data: dict) -> None:
        """Atomic write: write to temp file, then replace."""
        data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)

        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(self._path.parent),
            prefix=".strategy_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, str(self._path))
        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _default_champion_entry() -> dict:
        return {
            "vs_support": {},
            "with_jungler": {},
            "with_adc": {},
            "personal_notes": "",
            "overlay_priority": "normal",
        }

    @staticmethod
    def _default_prefs() -> dict:
        return {
            "overlay_always_visible": True,
            "overlay_auto_show_loading_screen": True,
            "overlay_show_duration_seconds": 15,
            "overlay_opacity": 0.85,
            "overlay_font_size": 14,
            "overlay_font_family": "Segoe UI",
            "overlay_width": 500,
            "overlay_x": 20,
            "overlay_y": 60,
        }
